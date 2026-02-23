# TODO: Generic Guided Stack For Problem Games

Date: 2026-02-22
Updated: 2026-02-22

**Scope: Manual mode only. Auto mode (`re_auto_mode.py`, `launch_resident_evil_stack.py → start_stack`) is in deep sleep — do not build toward it here.**

---

## Goal

Create a reusable, profile-driven guided workflow for games that are restrictive about:

- which display they render on
- primary monitor requirements
- window sizing/placement quirks
- launcher/config screens before gameplay
- audio output routing

This should generalize the current Resident Evil manual mode.

---

## Why

The RE manual mode proved a useful pattern:

- open the game folder and relevant windows up front
- guide the user through display setup with a checklist
- verify the environment before continuing
- move Moonlight/windows to the right place automatically
- monitor for game exit and restore on exit or `Ctrl+C`

Instead of building a new one-off script for each future problem game, build a generic framework
around this pattern.

---

## What Already Exists (Do Not Rebuild)

| Module | Status |
|--------|--------|
| `session/display_api.py` | Fully generic — display enumeration, mode set/restore |
| `session/window_utils.py` | Fully generic — window find, move, rect helpers |
| `session/audio.py` | Fully generic — default audio device switching |
| `session/vdd.py` | VDD-specific, clean interface |
| `session/moonlight.py` | Moonlight window placement and process helpers |
| `session/re_preflight.py` | Generic preflight logic, RE-named module |
| `session/re_manual_mode.py` | Active manual mode — the template for the generic engine |
| `session/re_auto_mode.py` | **Sleeping — do not touch** |
| `session/moonlight_adjuster.py` | Interactive CRT calibration tool |

The action layer is largely done. The missing piece is the engine contract and profile schema.

---

## Manual Mode Flow (The Pattern To Generalize)

The current `re_manual_mode.py → manual_stack()` does this:

1. Check the game is not already running
2. Ensure Moonlight is running
3. Capture Moonlight's current rect (for restore)
4. Open the game folder in Explorer; move the folder window to the internal display
5. Plug/wait for the VDD
6. Open Windows Display Settings
7. Reposition the folder window to internal display again (Settings may have moved it)
8. Print a step-by-step checklist; wait for user to press Enter
9. Verify attached display count and required display tokens
10. Move Moonlight to CRT
11. Switch audio to CRT device
12. Check if the folder window is already on the Moonlight display; inform user
13. Prompt user to move folder to Moonlight display and launch the game manually
14. Wait for game process to appear, then monitor for exit
15. On exit (or Ctrl+C): move Moonlight back, restore audio

The generic engine should implement exactly this sequence, driven by profile data.

---

## Proposed Architecture

### 1) Engine Layer (Generic)

One module — `session/guided_engine.py` — that runs the lifecycle above without any game-specific
strings or paths. The profile provides all the data; the engine provides all the logic.

Lifecycle phases:

```
preflight      → ensure_running, capture_rects
setup          → open_folder, open_display_settings, show_checklist, wait_for_enter
verify         → display_count, required_display_tokens
placement      → move_moonlight_to_crt, switch_audio, check_folder_placement
user_launch    → prompt, wait_for_process_start
monitoring     → poll game process
restore        → move_moonlight_back, restore_audio  (always in finally)
```

The engine should not know about Resident Evil, Moonlight tokens, or CRT tokens by name.
Those come from the profile.

### 2) Action Layer (Already Mostly Exists)

The generic engine calls these; no significant new action code is needed for most games.

Reusable actions:

- `ensure_moonlight_running(exe, dir)` — `session/moonlight.py`
- `plug_vdd_and_wait(token, timeout)` — `session/vdd.py`
- `ensure_required_displays(groups)` — `session/re_preflight.py`
- `attached_display_count()` — `session/re_preflight.py`
- `open_windows_display_settings()` — `session/re_preflight.py`
- `move_moonlight_to_crt(tokens, dir, crt_rect)` — `session/moonlight.py`
- `move_moonlight_to_internal(tokens, dir, idle_rect)` — `session/moonlight.py`
- `set_default_audio_best_effort(token)` — `session/audio.py`
- `find_window / get_rect / move_window` — `session/window_utils.py`
- `is_re_game_running()` → needs generalization (see below)

**One action that needs a rename:** `is_re_game_running()` is generic logic with an RE-specific
name. It should accept a list of process names from the profile rather than loading them from
`GAME_PROFILES`. Rename to `is_any_process_running(names)` or similar.

**One helper to move:** `_rect_overlap_ratio()` in `re_manual_mode.py` is private but useful
globally. It is the same overlap check the hardening plan calls for in `move_moonlight_to_crt`
verification. Move it to `session/window_utils.py` so both the engine and the placement helpers
can use it without importing from a mode module.

### 3) Profile Layer (Per-Game Data)

Profiles describe behavior; the engine reads them.

**Proposed guided-stack profile schema:**

```json
{
  "game_key": "re1",
  "game_label": "Resident Evil (GOG)",

  "process_names": ["biohazard.exe"],

  "requires_moonlight": true,
  "requires_vdd": true,

  "game_exe": "D:\\GOG Galaxy\\Games\\Resident Evil\\Biohazard.exe",
  "game_dir": "D:\\GOG Galaxy\\Games\\Resident Evil",
  "open_game_folder_on_start": true,

  "display_count_expected": 3,
  "required_display_groups": {
    "internal_display": ["Internal Display", "Intel(R) UHD Graphics"],
    "crt_display": ["CP-1262HE", "NVIDIA GeForce RTX 4090 Laptop GPU"],
    "moonlight_display": ["SudoMaker Virtual Display"]
  },

  "crt_target_refresh_hz": 60,

  "crt_calibration": {
    "mode": "relative_to_crt",
    "x_offset": -110,
    "y_offset": -80,
    "w_delta": 130,
    "h_delta": 150
  },

  "audio_device_on_start": "CP-1262HE (NVIDIA High Definition Audio)",
  "audio_device_on_restore": "Speakers (Realtek(R) Audio)",

  "manual_checklist": [
    "Set/verify resolutions for Internal, CRT, and SudoMaker in Display Settings.",
    "Set the PRIMARY display manually.",
    "Press Enter when ready."
  ]
}
```

Notes on field decisions:

- `requires_moonlight` / `requires_vdd` — not every future problem game needs both
- `open_game_folder_on_start` — governs the Explorer-folder-open + window-move behavior
- `crt_calibration` — relative-to-CRT offsets from the hardening plan; preferred over absolute rects
- `manual_checklist` — free-form step list the engine prints before the Enter prompt; game-specific
- No `topology_mode` field — this framework is manual-only

---

## What Manual Mode Currently Does That Must Be Preserved

These behaviors are easy to drop during a refactor:

1. **Captures Moonlight rect before moving** — `_capture_moonlight_rect_for_manual_restore()`
   saves where Moonlight was before the session so restore returns it to exactly that position,
   not just the configured `idle_rect`. The generic engine must do the same.

2. **Opens game folder + moves it to internal display** — before the display setup checklist,
   the folder window is opened and positioned on the physical display so the user can see it
   while following the steps. This is `open_game_folder_on_start` in the profile.

3. **Re-moves the folder window after Display Settings opens** — opening Display Settings can
   shift window positions. The folder window is moved a second time after that.

4. **Folder window placement check on Moonlight display** — after moving Moonlight to CRT,
   the engine checks whether the game folder Explorer window is already on the Moonlight display
   and reports that to the user before the final prompt.

5. **Three-tier Moonlight restore** — on exit: (a) captured pre-session rect, (b) live internal
   display bounds, (c) configured `idle_rect`. The cascade matters — if (a) fails for any reason,
   (b) uses live data rather than a stale config value.

---

## Hardening Plan Integration

The generic engine should apply the hardening improvements to manual mode from the start.
Relevant items (see `screen-control-hardening-plan.md`):

- **Relative CRT calibration** (`crt_calibration` profile field) instead of absolute `crt_rect`
- **Post-move overlap verification** after `move_moonlight_to_crt` — uses `_rect_overlap_ratio()`
  (move from `re_manual_mode.py` to `window_utils.py` in Phase 1)
- **Increased `move_moonlight_to_internal` retries** — 20 instead of 6 for the restore move
- **End-state log on restore failure** — explicit log when all restore attempts are exhausted

The condition-gated primary switch settle and `QueryDisplayConfig` refresh fixes are auto-mode
concerns — leave them for whenever auto mode wakes up.

---

## Implementation Plan (TODO)

### Phase 1 — Cleanup and Schema Design (No Behavior Change)

1. Move `_rect_overlap_ratio()` from `re_manual_mode.py` to `session/window_utils.py`
2. Generalize `is_re_game_running()` → `is_any_process_running(names: list)` in `session/re_game.py`
3. Design and document the final guided-stack profile JSON schema (validate all fields against RE1/RE2/RE3)
4. Decide on file location for guided-stack profiles (separate from LaunchBox wrapper profiles)

No behavior changes. This is groundwork only.

### Phase 2 — Build the Generic Engine

1. Add `session/guided_engine.py` implementing the lifecycle phases above
2. Port `re_manual_mode.py → manual_stack()` logic into the engine, profile-driven
3. Apply hardening improvements in scope for manual mode (overlap check, increased restore retries, failure logging)
4. Ensure Ctrl+C and game-exit both call the same restore path via `finally`

### Phase 3 — Convert RE to Generic Profiles

1. Create guided-stack profile files for `re1`, `re2`, `re3`
2. Update `launch_resident_evil_stack.py` to load the profile and call the generic engine for the `manual` command
3. Keep the existing CLI working as-is — no user-visible change
4. `re_manual_mode.py` can then be retired (or kept as a reference until the engine is proven)

### Phase 4 — Future Problem Games

When another restrictive game appears:

1. Create a profile file
2. Reuse the engine + existing actions
3. Only write new action code if the game requires something the engine cannot express via profile fields

---

## Design Rules

- User controls all display topology — the engine guides and verifies, never auto-switches primary
- Verify before proceeding: display count, display tokens, process state
- Ctrl+C and game exit must both reach the same restore path; restore runs in `finally`
- Profiles are data, not code — adding a game should not require touching the engine
- When a new game needs something not in the profile schema, add a field first; only extend the engine if the field alone is not enough
- Keep RE behavior identical to today after the refactor — the engine is a refactor, not a rewrite

---

## Success Criteria

This is successful when:

1. Adding another restrictive game means writing one profile file and zero engine code
2. RE manual mode behavior (folder opening, checklist, Moonlight placement, restore) is identical to current `re_manual_mode.py` behavior
3. Restore (Ctrl+C or game exit) works cleanly every run
4. Hardening improvements (overlap verification, relative calibration, better restore logging) are present and working for RE without extra per-game configuration
