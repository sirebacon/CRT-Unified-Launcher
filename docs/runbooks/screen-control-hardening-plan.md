# Screen Control Hardening Plan (Reduce "Finicky" Behavior)

Date: 2026-02-22
Updated: 2026-02-22 (post code review)

Status: Proposal

---

## Why It Feels Finicky

The current RE/Moonlight CRT flow depends on multiple unstable operations happening in sequence:

1. Virtual display (VDD) attach timing
2. Primary display switch (sometimes via `ChangeDisplaySettingsEx`, sometimes `SetDisplayConfig`)
3. Windows desktop coordinate re-rooting after topology changes
4. Absolute Moonlight window placement (`x/y/w/h`) that assumes coordinates stay stable
5. Refresh correction (`59` vs `60`) after topology/mode changes

Each step can succeed independently while the final visual result is still wrong.

### Specific Failure Modes Observed in Code

The following concrete gaps were found during code review of the session modules:

**A. `move_window()` is fire-and-forget (most impactful)**
`window_utils.py:move_window` calls `SetWindowPos` and returns immediately with no read-back.
Neither `move_moonlight_to_crt` nor `move_moonlight_to_internal` verify the window's actual
position after the call. A "successful" move means only that the Win32 call did not raise — not
that the window landed where expected. Silent misplacement is common after topology changes.

**B. Absolute `crt_rect` breaks after primary switch shifts the virtual desktop origin**
`re_stack_config.json → moonlight.crt_rect` is stored as an absolute desktop rect. When the
SudoMaker VDD becomes primary, all desktop coordinates shift. The stored rect now points to the
wrong region of the virtual desktop. The `x: 1170, y: -80` rect in the current config was
calibrated for one coordinate space and may be wrong in another.

**C. Post-primary-switch settle is a fixed 2-second sleep**
`launch_resident_evil_stack.py:start_stack` sleeps 2s after `set_primary_display_verified` before
calling `move_moonlight_to_crt`. The NVIDIA hybrid-GPU driver needs up to 4s (per the backoff
retry in `apply_restore_system_state`) before it fully accepts display mode changes. The 2s sleep
may not be enough; the 30-iteration window-find loop in `move_moonlight_to_crt` implicitly covers
the extra time, but the two mechanisms are not coordinated.

**D. `set_display_refresh_best_effort` early-exit cannot detect sub-integer drift**
The function reads `DisplayFrequency` as integer Hz and short-circuits if it equals `target_hz`.
If the display was previously set to 60.02 Hz (e.g. via `CDS_UPDATEREGISTRY`), the integer
read returns 60, so the enforcement loop thinks no correction is needed and skips it. The 60.02
Hz mode persists silently through the whole session.

**E. `move_moonlight_to_internal` retry window is shorter than `move_moonlight_to_crt`**
The CRT move retries 30× at 0.5s each (15s total). The internal/restore move retries only 6×
(3s total). At restore time Moonlight may be minimized or hidden — the shorter window means
restore can silently fail to reposition Moonlight.

**F. `apply_restore_system_state` does not verify final state before returning**
The retry loop breaks on first success, but if all four backoff attempts fail there is no explicit
summary log before the function returns False. The caller (`restore_stack`) only prints a generic
"WARNING: restore reported errors" without detail about which step failed.

**G. No window overlap verification against CRT bounds**
After Moonlight is moved, there is no check that the window rect actually overlaps the CRT display
region by a meaningful threshold. The window could land partially or fully off the CRT (e.g. on
the Intel UHD display) and the session continues as if placement succeeded.

---

## Main Goal

Make screen control deterministic enough that:

- A topology change does not break Moonlight CRT placement
- A successful move means the same visible result
- Failures are detected and recovered automatically
- Manual tuning is only needed for calibration, not every session

---

## What To Change (Recommended)

### 1) Replace Absolute CRT Window Rect With Relative Calibration

**Current problem:**

`moonlight.crt_rect` is stored as an absolute desktop rect. Desktop origin shifts after primary
display changes; the stored coordinates become invalid.

**Recommended model:**

Store calibration as offsets/deltas relative to the live CRT display bounds, computed each run.

Example config shape (add to `re_stack_config.json → moonlight`):

```json
{
  "moonlight": {
    "crt_calibration": {
      "mode": "relative_to_crt",
      "x_offset": -110,
      "y_offset": -80,
      "w_delta": 130,
      "h_delta": 150
    }
  }
}
```

Runtime behavior in `move_moonlight_to_crt`:

1. Detect live CRT display rect via `get_crt_display_rect(crt_tokens)` → `(cx, cy, cw, ch)`
2. Compute target: `x = cx + x_offset`, `y = cy + y_offset`, `w = cw + w_delta`, `h = ch + h_delta`
3. Move window
4. Read back actual rect via `get_rect(hwnd)` and verify overlap with CRT bounds

**Resolution order in `move_moonlight_to_crt` (updated):**

1. `moonlight.crt_calibration` (new — compute from live CRT + offsets)
2. `moonlight.crt_rect` (existing absolute override — kept for backward compat)
3. Live CRT bounds via display enumeration (raw, no offset)
4. `crt_config.json → launcher_integration` (legacy fallback)
5. Hardcoded default `(-1211, 43, 1057, 835)`

**Calibration tooling (`moonlight_adjuster.py`):**

The existing `adjust-moonlight` command and `adjust_moonlight()` / `write_moonlight_rect()`
functions already exist. They need to be extended:

- After the user presses `c` to save, compute the current Moonlight rect as offsets relative to
  the live CRT bounds and save as `crt_calibration` instead of absolute `crt_rect`.
- This makes the saved calibration reusable across topology states.
- Keep `crt_rect` write path as a legacy escape hatch (`--abs` flag or separate `set-crt-pos`
  command).

**Why this helps:**

- Survives desktop origin changes caused by VDD or primary switching
- Preserves overscan/edge tuning across sessions
- Makes the stored values human-readable ("+130px width" vs magic absolute coords)

---

### 2) Add Post-Move Window Rect Verification

This is the highest-value low-effort change (addresses failure mode A and G).

**In `window_utils.py`:**

Add a `get_rect` read-back in `move_window` or expose a `move_window_verified` variant:

```python
def move_window_verified(hwnd, x, y, w, h, strip_caption=False, tolerance=20) -> bool:
    move_window(hwnd, x, y, w, h, strip_caption=strip_caption)
    time.sleep(0.05)  # allow compositor to settle
    ax, ay, aw, ah = get_rect(hwnd)
    ok = (abs(ax - x) <= tolerance and abs(ay - y) <= tolerance
          and abs(aw - w) <= tolerance and abs(ah - h) <= tolerance)
    return ok
```

**In `move_moonlight_to_crt`:**

After a successful move, verify the Moonlight window intersects the CRT display region by at
least a configurable threshold (e.g. 50% overlap). Log the actual rect and whether it passed.

Overlap check logic:

```python
def _rect_overlap_ratio(win_rect, crt_rect):
    # win_rect, crt_rect = (x, y, w, h)
    wx, wy, ww, wh = win_rect
    cx, cy, cw, ch = crt_rect
    ix = max(0, min(wx+ww, cx+cw) - max(wx, cx))
    iy = max(0, min(wy+wh, cy+ch) - max(wy, cy))
    win_area = ww * wh
    return (ix * iy) / win_area if win_area > 0 else 0.0
```

If overlap ratio is below threshold (configurable, default 0.5), log a warning and optionally
retry the move.

---

### 3) Replace Fixed Settle Sleep With Condition-Gated Wait

**Current problem (failure mode C):**

`time.sleep(2.0)` after `set_primary_display_verified` is a guess. The NVIDIA driver settling
period is variable (documented: up to 4s in the restore path).

**Recommended:**

Replace the sleep with a brief polling loop that waits until the CRT display is queryable via
`EnumDisplaySettings` before proceeding to move Moonlight:

```python
# After set_primary_display_verified — wait until driver is ready
for _ in range(20):  # up to 10s
    try:
        dm = win32api.EnumDisplaySettings(crt_dev_name, ENUM_CURRENT_SETTINGS)
        if dm and dm.PelsWidth > 0:
            break
    except Exception:
        pass
    time.sleep(0.5)
```

This is more robust than a fixed sleep and self-corrects if the driver is faster or slower on a
given run.

---

### 4) Treat Refresh as a Full Mode Apply, Not a Refresh-Only Nudge

**Current limitation (failure mode D):**

`set_display_refresh_best_effort` uses `int(DisplayFrequency)` for the early-exit check.
This means 60.02 Hz reads as 60 and is silently skipped. The enforcement loop cannot catch it.

**Recommended behavior:**

- Use `QueryDisplayConfig` (CCD API) to read the true rational refresh rate (`Numerator/Denominator`)
  instead of `EnumDisplaySettings` integer.
- Enumerate available modes for the target resolution and prefer applying a full mode tuple
  (`width`, `height`, `refresh`) rather than only changing `DM_DISPLAYFREQUENCY`.
- Log available Hz values when correction fails (for diagnostics).
- If the rational refresh rate differs from target even when integer comparison matches, still
  apply the correction.

This also fixes "it said success but still wrong" cases where the driver remaps modes after topology
changes.

---

### 5) Increase `move_moonlight_to_internal` Retry Window

**Current problem (failure mode E):**

CRT move: 30 retries × 0.5s = 15s window.
Internal/restore move: 6 retries × 0.5s = 3s window.

At restore time, Moonlight is more likely to be in a transitional state (minimized, rearranged).
The shorter retry window means restore can silently fail.

**Fix:** Use 20 retries (10s) for the restore move, matching a proportionate window for the
likelihood of Moonlight being temporarily hidden.

---

### 6) Improve `apply_restore_system_state` End-State Logging

**Current gap (failure mode F):**

If all four backoff retry attempts fail, the loop exits and `ok` is False, but there is no
log line that says "all restore attempts exhausted." The caller logs a generic warning.

**Fix:**

```python
if not ok:
    print("[re-stack] All CRT mode restore attempts failed. Manual intervention required.")
    print(f"[re-stack] Target was: {saved_crt}")
    # Log current state for diagnosis
    actual = get_display_mode(CRT_DISPLAY_TOKEN)
    print(f"[re-stack] Current mode: {actual}")
```

Also add a final verification read at the end of `apply_restore_system_state` before returning,
to confirm primary and mode are what was intended.

---

### 7) Split "Topology Control" From "Window Placement" (Architecture)

Right now these concerns are mixed in one flow. They should be treated as separate phases with
verification between them:

**Phase A — Topology:**

1. VDD attach + display presence check
2. Audio switch
3. CRT refresh/mode correction
4. *(deferred until gameplay confirmed)* Primary switch + refresh re-correction

**Phase B — Placement:**

1. Settle wait (condition-gated, not fixed sleep)
2. Move Moonlight to CRT (relative calibration)
3. Verify placement (overlap check)
4. Optional fine-adjustment prompt

**Verification gates between phases:**

- After primary switch: confirm `current_primary_device_name()` equals expected device
- After mode set: confirm exact mode via `QueryDisplayConfig` rational refresh
- After window move: confirm window rect overlap with CRT bounds ≥ threshold

If a gate fails: retry phase (bounded), then abort with a clear recovery message. Avoid "continue
anyway" when verification fails — the current code does `moonlight_game_detected_since = None`
on CRT move failure (good), but the primary switch result is not checked before proceeding to
the settle sleep.

---

### 8) Prefer Stable Display Topologies (Profiles) — Optional Long-Term

The most robust model is not "compute everything ad hoc each run," but "switch between
known-good layouts."

**Recommended (Phase 4 effort):**

- Save two display profiles: `idle_topology` and `re_gameplay_topology`
- Apply them using `SetDisplayConfig` as a full topology transition
- Minimize dynamic coordinate math during runtime

This is more work but significantly less fragile than dynamic repositioning.

---

## External Tools Worth Considering

Using external tools is reasonable here if they improve determinism more than custom Win32 code.

### 1) NirSoft MultiMonitorTool (highly practical)

Use for:

- Monitor enable/disable
- Set primary monitor
- Move windows to a monitor
- Save/load monitor config

Why:

- Mature Windows utility
- Scriptable from CLI
- Often more stable than hand-rolled calls across driver quirks

Tradeoff:

- Adds external dependency
- Needs careful device matching and test coverage with VDD

### 2) AutoHotkey v2 (good for window control/verification glue)

Use for:

- Robust Moonlight window detection
- Move/restore/retry logic
- Activation/focus quirks
- Fallback automation when Python `pywin32` behavior is inconsistent

Why:

- Excellent for Windows window automation
- Easy to add retries and title/class matching rules

Tradeoff:

- Another runtime dependency
- Can become hard to maintain if used for display topology itself

### 3) QRes / ChangeScreenResolution.exe / Display Changer II (for mode switching)

Use for:

- Forcing display mode (`width x height x Hz`) via a stable CLI

Why:

- Simple and scriptable
- Can be used as a fallback path when the API call says success but result is wrong

Tradeoff:

- Tool quality varies
- Some tools are old and may behave poorly with virtual displays / modern hybrid GPU paths

### 4) devcon / pnputil (limited use, mostly diagnostics)

Use for:

- Driver/device state inspection
- Scripted disable/enable only if absolutely necessary

Tradeoff:

- Too blunt for normal runtime use
- Can make the system less stable if overused

### Recommended External-Tool Strategy (If We Add Any)

Keep Python as the orchestrator, but add fallback providers:

- `display_topology_provider = native | multimonitortool`
- `mode_switch_provider = native | qres_like_tool`
- `window_move_provider = native | ahk`

This keeps the codebase flexible and lets you test one subsystem at a time.

---

## Reliability Features To Add

### 1) Post-Action Verification Everywhere

Every action should be followed by a read-back:

- After VDD attach: confirm target display exists via `find_display_by_token`
- After primary switch: confirm `current_primary_device_name()` equals expected device
- After mode set: confirm exact mode via `QueryDisplayConfig` rational refresh (not integer)
- After window move: confirm window rect within tolerance of target AND overlaps CRT bounds

### 2) Structured Logging (Machine-Friendly)

Current logs are readable but hard to analyze automatically. The existing `runtime/re_stack.log`
is append-only plain text (good), but has no structured events.

Add a JSONL debug log (`runtime/re_stack_events.jsonl`) in addition to human-readable logs:

```json
{"ts": 1740000000.0, "event": "primary_switch_attempt", "target": "\\\\.\\ DISPLAY10"}
{"ts": 1740000001.2, "event": "primary_switch_result", "success": true, "actual": "\\\\.\\ DISPLAY10"}
{"ts": 1740000001.5, "event": "moonlight_move", "target": {"x":1170,"y":-80,"w":1410,"h":1110}}
{"ts": 1740000001.6, "event": "moonlight_verify", "actual": {"x":1168,"y":-82,"w":1410,"h":1110}, "overlap": 0.99, "ok": true}
```

Events to capture:

- `display_attach` / `display_attach_timeout`
- `primary_switch_attempt` / `primary_switch_result`
- `mode_set_attempt` / `mode_set_result`
- `moonlight_move` / `moonlight_verify`
- `restore_start` / `restore_complete`

This makes regressions much easier to diagnose across runs.

### 3) Recovery Paths

When a step fails, choose a recovery plan explicitly:

- Retry same method (bounded)
- Try alternate provider/tool
- Re-apply topology profile
- Abort and restore idle state

Avoid "continue anyway" when verification fails.

### 4) Calibration Tooling (Update Existing)

The existing `adjust-moonlight` command (`moonlight_adjuster.py`) already provides interactive
window positioning. Extend it to:

- Detect live CRT bounds when saving
- Compute and save offsets relative to CRT (not absolute desktop coords)
- Display both the absolute rect and the relative calibration for confirmation

This should become the only way the CRT gameplay placement is stored going forward. The existing
`set-crt-pos` / `crt_rect` path should remain as a legacy escape hatch.

---

## Suggested Implementation Plan (Phased)

### Phase 1 — Small, High Value (do first)

1. **Add `move_window_verified`** in `window_utils.py` — read-back actual rect after `SetWindowPos`,
   return a bool indicating whether placement landed within tolerance. (addresses failure mode A)

2. **Add overlap verification** in `move_moonlight_to_crt` — after the move, check the Moonlight
   window rect overlaps the live CRT bounds by ≥ 50%. Log actual vs expected. Warn if below threshold.
   (addresses failure mode G)

3. **Add relative CRT calibration config** (`crt_calibration` in `re_stack_config.json`) and
   update `move_moonlight_to_crt` to compute placement from live CRT rect + offsets.
   Keep `crt_rect` as backward-compat fallback. (addresses failure mode B)

4. **Update `moonlight_adjuster.py`** to compute and save relative calibration offsets instead of
   absolute coords when pressing `c`. Keep absolute save as `crt_rect` for backward compat
   or via a separate key press.

5. **Fix `apply_restore_system_state` end-state logging** — add explicit "all attempts exhausted"
   log and a final state read-back before returning. (addresses failure mode F)

6. **Increase `move_moonlight_to_internal` retries** from 6 to 20. (addresses failure mode E)

Expected outcome:

- Silent misplacement is detected and logged instead of silently succeeding
- Fewer placement breaks when desktop origin changes
- Better diagnostics when restore fails

### Phase 2 — Stability

1. **Replace fixed 2s settle sleep** with condition-gated wait polling CRT display queryability.
   (addresses failure mode C)

2. **Fix refresh detection** — use `QueryDisplayConfig` rational refresh instead of integer
   `DisplayFrequency` for both early-exit check and post-apply verification.
   (addresses failure mode D)

3. **Add JSONL structured event logging** alongside existing plain-text log.

4. **Separate topology phase and placement phase** with explicit verification gates and
   bounded retry policies per phase.

5. **Add `inspect` dry-run improvements** — show planned actions and delta from current state
   (what would change if `start` were run now).

Expected outcome:

- Easier debugging via structured logs
- Fewer "looks successful but isn't" runs
- Refresh drift is detected and corrected reliably

### Phase 3 — Optional External Tool Integration

1. Integrate `MultiMonitorTool` as an alternate topology provider
2. Integrate an external mode switch tool as fallback for `ChangeDisplaySettingsEx`
3. Optionally use AutoHotkey for Moonlight window handling edge cases

Expected outcome:

- Better resilience against driver/API quirks on this specific machine

### Phase 4 — Most Robust

1. Capture and apply known-good display topology profiles (`idle`, `gameplay`) using `SetDisplayConfig`
2. Minimize dynamic coordinate math during runtime
3. Use fullscreen gameplay placement whenever possible (control geometry at the Apollo/host level
   rather than post-hoc window nudging)

Expected outcome:

- Least fragile behavior overall; fewest moving parts per session

---

## Acceptance Criteria (What "Less Finicky" Means)

A change should count as a real improvement only if:

1. 10 consecutive RE stack runs complete without manual Moonlight repositioning
2. Moonlight lands within expected CRT placement tolerance (overlap ≥ 95%) each run
3. Primary display verification succeeds every run (logged and confirmed by read-back)
4. CRT mode verifies as exact target mode (`1280x960@60`) or failure is explicit and actionable
5. Restore returns to idle state cleanly every run (primary back to Intel UHD, Moonlight repositioned)
6. No silent failures — every step that fails produces a log line that names the step and what was expected vs actual

---

## Recommended Next Step

**Implement Phase 1 items 1–3** (post-move verification + relative calibration) before anything else.

These are the highest cost/benefit changes:

- Item 1 (`move_window_verified`) is ~20 lines in `window_utils.py` and catches the most common
  silent failure mode.
- Item 2 (overlap check in `move_moonlight_to_crt`) is ~15 lines and gives immediate diagnostic
  value.
- Item 3 (relative calibration) eliminates the root cause of coordinate fragility across topology
  changes.

All three are self-contained, do not require architecture changes, and are backward compatible
with the existing config.
