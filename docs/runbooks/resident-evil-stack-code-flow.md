# Runbook: Resident Evil Stack Code Flow

Date: 2026-02-22

## Purpose

Explain the runtime flow of the Resident Evil stack implementation so it can be adjusted safely.

Primary entrypoint:

- `launch_resident_evil_stack.py`

Supporting modules:

- `session/display_api.py`
- `session/moonlight.py`
- `session/audio.py`
- `session/vdd.py`

## High-Level Design

The stack is an orchestrator around four concerns:

1. Moonlight process + window placement
2. Virtual display (VDD) presence check
3. Windows display topology / primary monitor switching / refresh enforcement
4. Audio output switching

Resident Evil itself is launched through the existing generic wrapper:

- `integrations/launchbox/wrapper/launchbox_generic_wrapper.py`

The RE stack does not patch the game binary. It prepares system state, launches the wrapper, enforces drift correction, then restores state.

## File Responsibilities

- `launch_resident_evil_stack.py`
  - CLI (`start`, `restore`, `inspect`)
  - constants/tokens/paths (loaded from `re_stack_config.json`)
  - preflight sequence
  - session enforcement loop (primary drift, refresh drift, gameplay window detection)
  - auto-restore on exit/crash/Ctrl+C
  - persistent log file tee (`runtime/re_stack.log`)
- `session/display_api.py`
  - enumerate displays (attached only via `DISPLAY_DEVICE_ATTACHED_TO_DESKTOP`)
  - match displays by token / device name
  - detect current primary
  - set primary (`ChangeDisplaySettingsEx`, fallback `SetDisplayConfig`)
  - set CRT refresh
  - detect CRT display bounds from live display enumeration
- `session/moonlight.py`
  - detect running Moonlight process
  - launch Moonlight if missing
  - find Moonlight window
  - move Moonlight window to CRT display bounds
  - move Moonlight window to internal display
  - detect gameplay window visibility by title fragment (`is_gameplay_window_visible`)
- `session/audio.py`
  - detect audio backend availability (`AudioDeviceCmdlets` / `nircmd`)
  - best-effort default playback device switching
- `session/vdd.py`
  - wait for Moonlight virtual display to appear (managed by Apollo)
  - recovery re-attach via mode index enumeration (if VDD was soft-disconnected)
  - `unplug_vdd()` available for manual use (not called from restore)

## Logging Flow

`launch_resident_evil_stack.py` enables persistent logging at process start:

- Output file: `runtime/re_stack.log`
- Mechanism: stdout/stderr tee (`_TeeWriter`)

This happens before argument parsing, so all command output (`inspect`, `start`, `restore`) is captured.

## CLI Flow (`launch_resident_evil_stack.py`)

### `main()`

1. Calls `_enable_persistent_logging()`
2. Parses args (`start`, `restore`, `inspect`)
3. Dispatches to:
   - `start_stack()`
   - `restore_stack()`
   - `inspect_state()`

### `parse_args()`

Subcommands:

- `start --game re1|re2|re3 [--debug] [passthrough...]`
- `restore`
- `inspect`

`--debug` is passed through to the generic wrapper (wrapper file logging), not just the RE stack.

## `inspect` Flow

Function: `inspect_state()`

Purpose: read-only diagnostics.

Steps:

1. Calls `enumerate_attached_displays()` to list active desktop displays.
2. Prints current primary display (`current_primary_display()`).
3. Resolves:
   - RE primary token (`RE_PRIMARY_DISPLAY_TOKEN`)
   - restore primary token (`RESTORE_PRIMARY_DISPLAY_TOKEN`)
4. Prints audio backend status (`audio_tool_status()`).
5. Prints configured audio tokens.

Use this when display names/tokens drift or hardware changes.

## `start` Flow (Core Session)

Function: `start_stack(game, debug, passthrough)`

### Phase 1: Validate Inputs / Setup

1. Resolve selected game profile from `GAME_PROFILES`.
2. Verify:
   - wrapper exists (`WRAPPER_PATH`)
   - selected RE profile exists
3. Remove stale `wrapper_stop_enforce.flag` if present.

### Phase 2: Preflight (Game Check + Moonlight + Displays)

All wrapped in a `try/except/finally` block. If `Ctrl+C` fires here, restore still runs.

1. `_is_re_game_running()`
   - Loads `process_name` fields from all profile JSONs.
   - If any RE game process is already running, abort immediately.
2. `ensure_moonlight_running(MOONLIGHT_EXE, MOONLIGHT_DIR)`
   - If Moonlight is already running, continue.
   - Otherwise launches `Moonlight.exe` and waits for process detection.
3. `plug_vdd_and_wait(...)`
   - If VDD already attached: continue immediately.
   - If not: attempts recovery re-attach (see VDD Internals), then polls up to `VDD_ATTACH_TIMEOUT_SECONDS`.
4. `_ensure_required_displays()`
   - Verifies required display groups by token:
     - internal display
     - CRT display
     - Moonlight virtual display

If any required preflight step fails, `start` aborts before modifying system state.

### Phase 3: Apply RE System State

Function: `_apply_re_mode_system_state()`

Sets `state_applied = True` on success. Restore only runs if `state_applied` is True or the wrapper process was started.

Steps:

1. Capture current primary display (`current_primary_display()`)
2. Save state to `runtime/re_stack_state.json`:
   - `previous_primary_device_name` — always written, even if empty, to prevent stale data
3. Attempt to force CRT display refresh to `CRT_TARGET_REFRESH_HZ` (60) before topology change
4. Set Moonlight virtual display as primary (`set_primary_display_verified(RE_PRIMARY_DISPLAY_TOKEN)`)
5. Force CRT refresh to 60 Hz again after primary switch
6. Best-effort switch audio to RE token (`CP-1262HE ...`)

Only the primary-display change is treated as required for success. Audio is best-effort.

### Phase 3b: Move Moonlight to Internal Display

Immediately after the primary switch, calls:

```
move_moonlight_to_internal(internal_tokens, moonlight_dir)
```

Why: switching the primary to `SudoMaker Virtual Display` (at virtual coordinates 0,0) shifts the entire Windows virtual desktop coordinate space. Moonlight's window, previously on the internal display, drifts into virtual display space and becomes invisible on any physical screen. This call corrects that, keeping Moonlight visible on the laptop screen for the game's config screens.

### Phase 4: Launch RE Wrapper

1. Load `gameplay_title` from the selected profile JSON (used in Phase 5).
2. Build command:
   - `python launchbox_generic_wrapper.py --profile-file <reX-gog.json>`
   - add `--debug` if requested
   - append passthrough args (after stripping leading `--`)
3. Start wrapper via `subprocess.Popen(...)`

The wrapper then launches the actual game executable and performs its own window enforcement logic.

### Phase 5: Session Enforcement Loop (While Game Runs)

Loop runs once per second until wrapper process exits.

It enforces three things:

1. **Primary display drift correction**
   - Re-check current primary via `current_primary_device_name()`
   - If not Moonlight VDD, log drift and re-apply `set_primary_display_verified(..., retries=1)`

2. **CRT refresh drift correction**
   - Every ~5 seconds, call `set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, 60)`
   - Only logs if correction is needed (no spam when already at target)

3. **Gameplay window detection → CRT move** (only until Moonlight is moved)
   - If profile has `gameplay_title`: calls `is_gameplay_window_visible(gameplay_title)` — scans all visible top-level windows for a title containing the fragment.
   - If no `gameplay_title`: falls back to `is_moonlight_fullscreen()` (WS_CAPTION / monitor coverage check — less reliable).
   - Once detected continuously for `FULLSCREEN_CONFIRM_SECONDS` (2 s), calls `move_moonlight_to_crt(...)`.
   - After successful CRT move, this check is disabled for the rest of the session.

Why the confirmation timer: brief loading screens or transitions can momentarily show the gameplay title. The 2-second hold prevents a false early CRT move.

### Phase 6: Exit / Crash / Ctrl+C Auto-Restore

`start_stack()` wraps execution in `try / except KeyboardInterrupt / finally`.

- On normal wrapper exit: restore runs in `finally`
- On crash / non-zero exit: restore runs in `finally`
- On Ctrl+C:
  - stack attempts to terminate wrapper process
  - restore runs in `finally`
  - returns code `130`

Restore only runs if `state_applied` is True or the wrapper process was started. This prevents restore from running when preflight fails early (e.g. Moonlight not found).

This is why menu option 7 is recovery-only now.

## `restore` Flow (Manual Recovery or Auto-Restore Backend)

Function: `restore_stack()`

### Phase 1: Stop Wrapper Enforcement

1. Write `wrapper_stop_enforce.flag`
2. Find running `launchbox_generic_wrapper.py` processes (`_find_wrapper_pids()`)
3. Terminate them (then kill if terminate fails)

### Phase 2: Restore Patched Config Files

Calls:

- `restore_defaults_from_backup()` from `default_restore.py`

This restores LaunchBox/BigBox/RetroArch files from the latest backup set.

### Phase 3: Cleanup Stop Flag

Removes `wrapper_stop_enforce.flag`

### Phase 4: Restore System State

Function: `_apply_restore_system_state()`

Steps:

1. Read `runtime/re_stack_state.json`
2. If `previous_primary_device_name` is present:
   - attempt exact restore via `find_display_by_device_name()` + `set_primary_display_entry()`
3. If exact restore fails/unavailable:
   - fallback token restore (`RESTORE_PRIMARY_DISPLAY_TOKEN`)
4. Re-apply CRT refresh to 60 Hz
5. Best-effort audio restore to `Speakers (Realtek(R) Audio)`
6. Move Moonlight window back to internal display (best-effort, `move_moonlight_to_internal`)

The SudoMaker VDD is NOT unplugged on restore. See "VDD Lifecycle" section.

Return code behavior:

- success (`0`) requires:
  - config restore success
  - display restore success
- audio and Moonlight window move are best-effort (warnings may occur while restore still returns success)

## Display Switching Internals (`session/display_api.py`)

### Enumeration and Matching

- `enumerate_attached_displays()`
  - lists displays with `DISPLAY_DEVICE_ATTACHED_TO_DESKTOP` flag set
  - returns `device_name`, `device_string`, monitor strings, position, flags
  - does NOT include detached or disabled adapters
- `find_display_by_token()`
  - substring match against device_name, device_string, and monitor strings
- `current_primary_display()`
  - inspects `DISPLAY_DEVICE_PRIMARY_DEVICE` flag

### Primary Switching Strategy

`set_primary_display_verified()` is the public enforcement entrypoint:

1. Resolve target by token
2. Call `set_primary_display()`
3. Verify primary actually changed
4. Retry if needed

`set_primary_display()` resolves token and delegates to `set_primary_display_entry()`.

`set_primary_display_entry()` strategy:

1. Fast path: if target already primary -> success
2. Try `ChangeDisplaySettingsEx(..., CDS_SET_PRIMARY)` with several devmode variants:
   - keep current position
   - force `(0,0)`
   - no position field mutation
3. If all fail:
   - fallback to `set_primary_via_setdisplayconfig()`

`set_primary_via_setdisplayconfig()`:

- Queries active display paths/modes
- Finds target source by GDI device name (`\\.\DISPLAYx`)
- Repositions all source modes so target source lands at `(0,0)`
- Applies via `SetDisplayConfig(...)`

This fallback exists because virtual display drivers may reject `CDS_SET_PRIMARY`.

### Refresh Enforcement

`set_display_refresh_best_effort()`:

- reads current display frequency from current mode
- if not target Hz, attempts `ChangeDisplaySettingsEx` with `DM_DISPLAYFREQUENCY`
- early-exits silently if already at target (no log spam)
- logs with before/after Hz only when a correction is made

## Moonlight Handling Internals (`session/moonlight.py`)

### Process Detection / Launch

- `is_moonlight_running()` / `moonlight_pids()`
  - detect Moonlight processes by name/cmdline and executable directory
- `ensure_moonlight_running()`
  - launches `Moonlight.exe` if needed
  - waits up to ~15 s for process detection

### Window Placement

- `find_moonlight_window()`
  - searches windows for each Moonlight PID
  - first tries title contains `moonlight`, then any top-level visible window
- `move_moonlight_to_crt(crt_tokens, moonlight_dir, crt_config_path=None)`
  - gets CRT rect from live display enumeration (`get_crt_display_rect`)
  - falls back to `crt_config.json` rect if enumeration fails
  - moves Moonlight window; polls up to 15 s for window to appear
- `move_moonlight_to_internal(internal_tokens, moonlight_dir)`
  - gets internal display rect from live enumeration
  - no fallback rect — if internal display not found, logs and returns False
  - polls up to 3 s for window to appear

### Gameplay Window Detection

- `is_gameplay_window_visible(title_fragment: str) -> bool`
  - scans all visible top-level windows system-wide (no PID filter)
  - case-insensitive substring match on window title
  - returns True if any window title contains `title_fragment`

This is used in the enforcement loop to determine when the actual game window (e.g. `"RESIDENT EVIL ® PC"`) has replaced the config/launcher window (`"CONFIGURATION"`). It is more reliable than `is_moonlight_fullscreen()` because Moonlight itself stays windowed even when the game content is fullscreen.

### Gameplay Title Per Profile

Each profile JSON contains a `gameplay_title` field:

| Profile | `gameplay_title` | Gameplay window | Config window |
|---|---|---|---|
| `re1-gog.json` | `"RESIDENT EVIL"` | `RESIDENT EVIL ® PC` | `CONFIGURATION` |
| `re2-gog.json` | `"RESIDENT EVIL 2"` | `RESIDENT EVIL 2 ® PC` | `CONFIGURATION` |
| `re3-gog.json` | `"NEMISIS"` | `RESIDENT EVIL ™ 3 NEMISIS PC` | `CONFIGURATION` |

RE3 uses `"NEMISIS"` rather than `"RESIDENT EVIL"` to avoid the `™` unicode character in matching and to be more specific.

### Fullscreen Fallback

- `is_moonlight_fullscreen(moonlight_dir)`
  - checks WS_CAPTION absence or window rect matching monitor bounds
  - only used if profile has no `gameplay_title`
  - less reliable: Moonlight stays windowed even when game is fullscreen inside the stream

## Audio Handling Internals (`session/audio.py`)

`set_default_audio_best_effort()` tries:

1. `AudioDeviceCmdlets`
   - `Get-AudioDevice -List`
   - playback device name token match
   - `Set-AudioDevice -Index`
2. `nircmd.exe`
   - set default device for roles 0/1/2

If neither backend is available, it logs a warning and returns `False`.

## VDD Handling Internals (`session/vdd.py`)

### Why the SudoMaker VDD Cannot Be Force-Attached

SudoMaker Virtual Display Adapter is an IddCx-based virtual display driver. IddCx drivers:

- Appear in `EnumDisplayDevices` even when not attached to the desktop.
- Are managed by their host service (Apollo). Apollo controls when the VDD is active.
- Do NOT respond to `SetDisplayConfig(SDC_TOPOLOGY_EXTEND)` for re-attachment after a soft disconnect.
- Return `DISP_CHANGE_BADMODE (-2)` from `ChangeDisplaySettingsEx` when the registry settings were zeroed by a null-devmode disconnect (which is what `unplug_vdd` does).
- `SDC_ALLOW_CHANGES` combined with `SDC_TOPOLOGY_EXTEND` causes `ERROR_INVALID_PARAMETER (87)` — these flags are not compatible. `SDC_ALLOW_CHANGES` is only valid with `SDC_USE_SUPPLIED_DISPLAY_CONFIG`.

### Plug (Wait for Desktop Attachment)

`plug_vdd_and_wait()`:

1. If VDD already attached (via `find_display_by_token`) → success immediately.
2. Recovery attempt (if VDD is soft-disconnected):
   - `_find_vdd_device_name()`: scans all adapters including detached ones via `EnumDisplayDevices`.
   - Enumerates driver-supported modes by index (0, 1, 2...) using `EnumDisplaySettings(dev, iModeNum)`.
   - Passes the first valid mode to `ChangeDisplaySettingsEx(dev, dm, CDS_UPDATEREGISTRY|CDS_NORESET)` + commit.
   - This bypasses the zeroed registry settings from `unplug_vdd` and queries the driver directly.
3. Polls for up to `VDD_ATTACH_TIMEOUT_SECONDS` for the display to appear.
4. On timeout: logs all adapters (attached and detached) via `_log_all_display_adapters()` and advises restarting Apollo.

### Unplug

`unplug_vdd()` is available but is NOT called from `restore_stack()`.

It uses `ChangeDisplaySettingsEx(dev, None, CDS_UPDATEREGISTRY|CDS_NORESET)` which:

- removes the display from the Windows desktop topology
- zeroes the registry DEVMODE for the adapter
- makes recovery difficult (requires Apollo restart or mode enumeration recovery)

The SudoMaker VDD is left attached between sessions. It appears as a secondary display in Display Settings but does not affect normal use.

### VDD Lifecycle (Current Design)

- **On `start`**: wait for VDD to be attached (Apollo should have it ready). Recovery if soft-disconnected.
- **On `restore`**: primary display and audio are restored; VDD is left attached.
- The VDD stays attached persistently as long as Apollo is running.

## Failure Points To Watch

- Moonlight process not detected (`ensure_moonlight_running`)
- VDD not attaching within timeout — restart Apollo if all SudoMaker entries show `attached=False`
- Token mismatch after hardware/driver rename (`_ensure_required_displays`) — run `inspect` to see actual device strings
- Moonlight window not found (`move_moonlight_to_crt`)
- Primary switch blocked for virtual display (`set_primary_display_verified`)
- CRT mode refusing 60 Hz (`set_display_refresh_best_effort`)
- Audio backend missing or device token mismatch (`set_default_audio_best_effort`)
- Gameplay window not detected (wrong `gameplay_title` fragment or config screen title contains the fragment)

## Safe Adjustment Order

When behavior changes, adjust in this order:

1. Tokens and paths in `re_stack_config.json`
2. `inspect` output validation
3. `gameplay_title` values in profile JSONs if CRT move timing is wrong
4. Module behavior in `session/*.py` if tokens are correct but actions fail
5. Wrapper/game profile tuning only after system-state flow is stable

## Related Docs

- `docs/runbooks/resident-evil-stack-automation.md` (operations runbook)
- `docs/architecture.md` (project architecture + RE stack overview)
