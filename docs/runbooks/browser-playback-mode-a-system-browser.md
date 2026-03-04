# Mode A - System Browser (Multi-Site)

## Inherits

This mode inherits all shared contracts from:

- `docs/runbooks/browser-playback-core.md`

## Status

Implemented. Isolated launch + CRT placement + four safety safeguards + dry-run flag.

Note: an earlier stub used `os.startfile` for generic (non-Tier 3) launch. That path is
**not part of this design**. Tier 3 providers must use the isolated launch sequence below.

## Purpose

Launch browser content on the CRT with deterministic window placement and sizing, using an
isolated Chrome instance that cannot interfere with the user's personal Chrome session on the
internal monitor.

Opening a URL in the default browser (os.startfile) is explicitly **not sufficient** for this
mode. The required outcome is:

1. A separate isolated Chrome process (not a tab in the existing session)
2. That window moved and sized to the CRT rect
3. Terminal blocked until that process exits
4. Personal Chrome on the internal monitor untouched at every step

---

## Isolation Policy

The isolation guarantee is `--user-data-dir`. When Chrome is launched with a `--user-data-dir`
path that differs from the user's normal profile (`%LOCALAPPDATA%\Google\Chrome\User Data`),
Chrome is forced to spawn a completely new OS process. The two processes share no memory,
cookies, extensions, or window handles.

This is expected Chrome behavior. Edge cases (e.g. enterprise policy overrides, very old
Chrome versions) could affect it, but it is the standard behavior for all modern Chrome
releases and is the basis for this design.

Consequences:

- Chrome data and tabs in the personal session cannot be affected
- The isolated process has its own PID, which is used to gate all window management
- `os.startfile` fallback is **not used** for Tier 3 providers — it cannot guarantee
  a new process and defeats the isolation policy

---

## Config Schema

New keys under `browser_playback` in `crt_config.json`:

```json
"browser_playback": {
  "default_mode": "browser",
  "browser_path": "",
  "browser_rect": {"x": 0, "y": 0, "w": 1920, "h": 1080},
  "isolated_profile_dir": "runtime/browser_isolated",
  "isolated_profile_mode": "persistent",
  "window_find_timeout_sec": 15,
  "profiles": {
    "kisscartoon": {
      "mode_override": "browser",
      "browser_args": [
        "--no-restore-last-session",
        "--disable-session-crashed-bubble"
      ],
      "reanchor_hotkey": "ctrl+alt+m",
      "playwright_wait_until": "domcontentloaded",
      "playwright_fullscreen_js": true,
      "keymap": {
        "toggle_pause": "Space",
        "seek_back": "ArrowLeft",
        "seek_forward": "ArrowRight",
        "fullscreen": "f",
        "mute": "m"
      }
    }
  }
}
```

### Key decisions

**`browser_rect` is separate from `x/y/w/h`** (the mpv rect). The browser fills the full CRT
display area; mpv uses a configured crop rect. User must set `browser_rect` to match their
CRT's virtual desktop position and resolution.

**`isolated_profile_dir`** is relative to project root. Resolved to an absolute path at
runtime. Per-profile subdirectory is appended automatically:
`runtime/browser_isolated/<profile_id>/`

**`isolated_profile_mode`**:
- `"persistent"` — profile dir is kept between sessions. User stays logged in, site
  preferences are saved. Recommended for sites that require login/session continuity.
- `"ephemeral"` — profile dir is wiped in a `finally` block on clean exit. If the process
  crashes and cleanup is skipped, the dir is wiped at the next launch start.

**`--incognito` must not be in `browser_args` when using `persistent` mode.** Incognito
prevents cookies from persisting, defeating the purpose of a persistent profile. Remove it.
With `--user-data-dir` isolation already in place, incognito provides no additional safety.

**`browser_path` must be set.** An empty `browser_path` triggers an error for Tier 3
providers. `os.startfile` is not used because it cannot guarantee a new process.

---

## Launch Sequence

```
1. Validate browser_path exists on disk
   → if missing: log error, return 1 (no os.startfile fallback)

2. Resolve isolated profile dir
   → runtime/browser_isolated/<profile_id>/
   → if isolated_profile_mode == "ephemeral" and dir exists from a previous crash: wipe it now

3. Snapshot pre-existing Chrome window handles (protected set)
   → EnumWindows → collect all visible hwnds with class Chrome_WidgetWin_1
   → stored as _protected_hwnds; no window in this set will ever be moved

4. Build command:
   [browser_path,
    --user-data-dir=<abs_isolated_profile_dir>,
    --new-window,
    --no-restore-last-session,
    --window-position=X,Y,
    --window-size=W,H]
   + profile browser_args
   + [url]
   (--window-position and --window-size set from browser_rect as initial placement hint)

5. Popen → record PID

6. Poll for window by PID (timeout = window_find_timeout_sec)
   → EnumWindows every 0.3s
   → match: IsWindowVisible AND non-empty title AND GetWindowThreadProcessId == our PID
   → if process exits during poll: return its exit code immediately
   → if timeout reached without finding window: log warning, skip placement, proceed to step 8

7. Safety checks before SetWindowPos:
   a. assert hwnd not in _protected_hwnds
      → if in set: log safety abort, skip placement (do not move)
   b. re-verify PID immediately before move:
      → GetWindowThreadProcessId(hwnd) must still equal our PID
      → if mismatch: log safety abort, skip placement

8. SetWindowPos(hwnd, browser_rect x/y/w/h, SWP_NOZORDER)

9. proc.wait() — block until isolated Chrome process exits

10. Cleanup:
    → if isolated_profile_mode == "ephemeral": rmtree(isolated_profile_dir)
    → log exit code
    → return exit code
```

---

## Window Selection When Multiple Windows Exist

Since isolation is PID-based, multiple personal Chrome windows are irrelevant — they will
have different PIDs and will be filtered out before any window operation.

If multiple windows match our PID (e.g. Chrome opened a popup):
- Prefer the window with a non-empty title that contains the URL hostname
- Otherwise prefer the first visible window found in EnumWindows order
- Never act on more than one window

---

## Safeguards Summary

Four layered safeguards protect personal Chrome from any window operation:

| Safeguard | Where | What it prevents |
|-----------|-------|-----------------|
| `--user-data-dir` isolation | Chrome flag | Shared process / data corruption |
| Protected set pre-launch snapshot | Before Popen | Moving a pre-existing window |
| PID match at find time | Window enumeration | Finding wrong window |
| PID double-check before SetWindowPos | Immediately before move | Race condition between find and move |

If any safeguard fails, the window operation is skipped entirely. The session continues and
blocks on `proc.wait()` without placement. Failure is logged with the specific safeguard that
tripped.

---

## Fullscreen Policy

**Recommendation: move/resize only (no fullscreen flags).**

`--start-fullscreen` risk: Chrome chooses which monitor to fullscreen based on the window's
center point at the moment the flag activates. If the window appears briefly on the main
monitor before placement, fullscreen lands on the wrong monitor.

`--kiosk` risk: no browser UI access. Cannot handle CAPTCHA, login prompts, or ad skips
without `Alt+F4`.

**Adopted policy**: launch with `--window-position` and `--window-size` as a placement hint,
then `SetWindowPos` to the CRT rect after the window appears. The user hits the site's own
fullscreen button inside the player. This is deterministic and monitor-safe.

Note: `--window-position` is ignored by Chrome on subsequent launches once it has saved
window geometry to the profile. `SetWindowPos` is always called regardless — do not rely
on Chrome flags for placement.

---

## Failure Modes and Fallbacks

| Failure | Behavior |
|---------|----------|
| `browser_path` empty or not found | Log error, return 1. No os.startfile fallback. |
| Profile dir creation fails | Log error with path, return 1. |
| Window not found within timeout | Log warning, skip placement, block on proc.wait(). |
| Process exits before window found | Return process exit code immediately. |
| hwnd in protected set (safeguard 1) | Log safety abort, skip placement, continue session. |
| PID mismatch before move (safeguard 2) | Log safety abort, skip placement, continue session. |
| SetWindowPos fails | Log warning, retry once after 0.5s. Do not fail session. |
| Ephemeral cleanup fails on exit | Log warning. Stale dir wiped at next launch start. |

**Never fall through to title-based window matching as a fallback.** If PID-based find
fails, skip placement. Title matching could target a personal Chrome window.

---

## Dry-Run Mode

A `--browser-dry-run` flag on the launcher runs the full flow but skips `SetWindowPos`.
Logs show exactly which hwnd would be targeted, its current rect, its PID, and whether it
would pass the safety checks. Use this to verify behavior before the first real session.

---

## Phase 1 vs Phase 2

**Phase 1 (this document — to implement):**
- Isolated launch with all four safeguards
- Single SetWindowPos placement at launch
- proc.wait() blocking (no key loop during browser session)
- No re-anchor hotkey (requires threading — Phase 2)
- Dry-run flag

**Phase 2 (future):**
- Background thread on proc.wait(); main thread runs lightweight key poll loop
- Re-anchor hotkey: on keypress, re-run SafeSetWindowPos to snap back to CRT rect
- Window drift enforcement loop (periodic re-anchor)

---

## Test Plan: "Personal Chrome Remains Untouched"

1. Open personal Chrome on main monitor, navigate to any page, note exact window
   position and size.
2. Open Task Manager — note existing Chrome process PIDs.
3. Run launcher with a Tier 3 provider URL.
4. Verify: a new Chrome process appears in Task Manager with a different PID.
5. Verify: personal Chrome window position and size are unchanged.
6. Verify: new Chrome window appears on the CRT at the expected rect.
7. Close the launcher's Chrome window.
8. Verify: only the launcher's process exits; personal Chrome still running.
9. Verify: `runtime/browser_isolated/<profile_id>/` exists (persistent) or is gone
   (ephemeral).
10. Run with `--browser-dry-run`: verify log output describes correct hwnd/PID without
    actually moving anything.

---

## Acceptance Criteria

1. Tier 3 provider URL opens in isolated Chrome on the CRT, not in a personal Chrome tab.
2. Personal Chrome window position and size are identical before and after the session.
3. No mpv process is spawned.
4. Window placement uses `browser_rect`, not the mpv `x/y/w/h` rect.
5. `browser_path` missing → error with actionable message, no silent fallback.
6. Ephemeral mode wipes the profile dir on clean exit.
7. Dry-run mode logs placement intent without executing SetWindowPos.
8. All four safeguards are logged when tripped.
