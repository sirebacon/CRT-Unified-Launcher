# Runbook: Resident Evil Stack Automation

Date: 2026-02-22

## Purpose

Document the Resident Evil stack workflow and recovery commands for CRT use.

Status (current):

- Supported workflow: `manual --game re1|re2|re3` (guided manual mode)
- Automatic mode (`start`) is on hold due to inconsistent behavior across display topology changes

Script:

- `launch_resident_evil_stack.py` — thin orchestrator; all implementation lives in `session/` modules (see below)

Menu integration:

- `crt_master.py` option `5` -> Resident Evil (Manual Mode)
- `crt_master.py` option `6` -> Tools submenu (includes RE recovery restore)

## Code Organization

The stack is split across five files plus a config file:

| File | Responsibility |
|---|---|
| `launch_resident_evil_stack.py` | CLI, constants, start/restore/inspect orchestration |
| `re_stack_config.json` | All adjustable tokens, paths, and timeouts (loaded at startup) |
| `session/display_api.py` | Display enumeration, primary switching (`ChangeDisplaySettingsEx` + `SetDisplayConfig` fallback), refresh rate, CRT rect detection |
| `session/vdd.py` | Moonlight virtual display attach check + recovery re-attach |
| `session/audio.py` | Audio device switching via `AudioDeviceCmdlets` or `nircmd` |
| `session/moonlight.py` | Moonlight process management, window finding, window placement, gameplay window detection |

All adjustable constants (tokens, paths, timeouts) are in `re_stack_config.json`. The orchestrator loads them at startup with built-in defaults as fallback.

## Commands

Direct commands from project root:

```powershell
python launch_resident_evil_stack.py inspect
python launch_resident_evil_stack.py manual --game re1
python launch_resident_evil_stack.py manual --game re2
python launch_resident_evil_stack.py manual --game re3
python launch_resident_evil_stack.py restore
```

## Resident Evil EXE Paths

Current profile mappings use these executables:

- RE1: `D:\GOG Galaxy\Games\Resident Evil\Biohazard.exe`
- RE2: `D:\GOG Galaxy\Games\Resident Evil 2\Resident Evil 2.exe`
- RE3: `D:\GOG Galaxy\Games\Resident Evil 3\bio3 Uncensored.EXE`

## What `inspect` Does

`inspect` is read-only. It does not change system state.

It reports:

1. Attached displays (`\\.\DISPLAY*`) and current positions.
2. Which display matches the RE primary token (Moonlight virtual display).
3. Which display matches the restore primary token (internal display).
4. Audio switching backend availability:
   - `AudioDeviceCmdlets`
   - `nircmd`
   - `none`
5. Current audio name tokens configured.

Use this first when changing display/audio names.

## What `manual --game reX` Does (Supported)

Guided manual mode (current workflow):

1. Ensures Moonlight is running.
2. Opens the selected RE folder and Windows Display Settings.
3. Prompts you to manually set resolutions and primary display.
4. Verifies internal + CRT + Moonlight displays are attached (3-display check).
5. Moves Moonlight to the CRT and switches audio to the CRT device.
6. Waits for you to launch the game manually.
7. On game exit or `Ctrl+C`, restores Moonlight position and audio (you restore primary display manually).

## What `start --game reX` Does (Legacy / On Hold)

Order of operations:

1. Aborts if a RE game process is already running (checked against `process_name` fields in all profiles).
2. Clears stale wrapper stop flag:
   - `wrapper_stop_enforce.flag` (if present)
3. Ensures Moonlight is running from:
   - `D:\Emulators\MoonlightPortable-x64-6.1.0\Moonlight.exe`
   - If not running, script attempts to launch it and waits for process detection.
4. Waits for the Moonlight virtual display (`SudoMaker Virtual Display`) to be attached:
   - The SudoMaker VDD is an IddCx driver managed by Apollo. It cannot be force-attached via standard Windows APIs — we wait for Apollo to have it ready.
   - If detached (e.g. from a previous manual `unplug_vdd` call), attempts recovery by enumerating driver-supported modes and re-enabling via `ChangeDisplaySettingsEx`.
   - Polls up to `VDD_ATTACH_TIMEOUT_SECONDS` (default 15 s).
5. Ensures required displays are present before continuing:
   - Internal display (`Internal Display` or `Intel(R) UHD Graphics`)
   - CRT display (`CP-1262HE` or `NVIDIA GeForce RTX 4090 Laptop GPU`)
   - Moonlight display (`SudoMaker Virtual Display`)
6. Captures current primary display device name and writes to:
   - `runtime/re_stack_state.json`
7. Sets primary display to Moonlight virtual display (`SudoMaker Virtual Display`):
   - Forces Resident Evil to render on the Moonlight virtual display.
   - Moonlight client streams the output to the CRT.
   - Uses `ChangeDisplaySettingsEx` with three position variants; falls back to `SetDisplayConfig` source-mode repositioning for virtual display drivers that reject `CDS_SET_PRIMARY`.
8. Immediately moves Moonlight window to the internal (physical) display after primary switch:
   - The primary switch shifts the Windows virtual desktop coordinate space; Moonlight's window drifts into virtual display space without this correction.
   - This keeps config/setup screens physically visible on the laptop screen.
9. Attempts to set default playback device to token:
   - `CP-1262HE (NVIDIA High Definition Audio)`
10. Launches game via:
    - `integrations/launchbox/wrapper/launchbox_generic_wrapper.py`
    - profile file selected by `--game`:
      - `re1` -> `integrations/launchbox/wrapper/profiles/re1-gog.json`
      - `re2` -> `integrations/launchbox/wrapper/profiles/re2-gog.json`
      - `re3` -> `integrations/launchbox/wrapper/profiles/re3-gog.json`
11. Enforcement loop (every ~1 s while game runs):
    - Re-applies primary display if it drifts away from Moonlight VDD.
    - Re-checks CRT refresh every ~5 s and corrects if drifted.
    - Monitors for the game's gameplay window title to appear (e.g. `RESIDENT EVIL`, `RESIDENT EVIL 2`, `NEMISIS` for RE3).
    - Once the gameplay title is detected continuously for `fullscreen_confirm_seconds` (default 2 s), moves Moonlight window to the CRT display bounds.
12. Automatically runs full restore flow when the launched process ends, crashes, or `Ctrl+C` is pressed.

Important behavior:

- Moonlight running requirement is required. If it fails, launch aborts.
- VDD presence check is required. If it times out, launch aborts.
- Required display set check is required. If it fails, launch aborts.
- Primary-display switch to Moonlight virtual display is required. If it fails, launch aborts.
- Moonlight window is NOT moved to CRT at launch — it stays on the internal monitor so config screens are visible. It moves to CRT automatically when the gameplay window is detected.
- Audio switch is best-effort. If it fails, launch continues with warning.
- If no `gameplay_title` is in the profile, falls back to `is_moonlight_fullscreen` (WS_CAPTION check) — less reliable.
- Menu-based restore is no longer required for normal RE sessions because auto-restore runs at session end.

## What `restore` Does

Order of operations:

1. Creates `wrapper_stop_enforce.flag` to stop enforcement loops.
2. Finds and terminates active `launchbox_generic_wrapper.py` processes.
3. Runs default backup restore flow:
   - `restore_defaults_from_backup()` from `default_restore.py`
4. Removes `wrapper_stop_enforce.flag`.
5. Restores primary display:
   - First choice: previously captured `previous_primary_device_name` from `runtime/re_stack_state.json`
   - Fallback: token `Intel(R) UHD Graphics`
6. Re-applies CRT refresh to 60 Hz.
7. Attempts to set default playback device to token:
   - `Speakers (Realtek(R) Audio)`
8. Moves Moonlight window back to the internal display (best-effort).

Note: The Moonlight virtual display (SudoMaker VDD) is **not** unplugged on restore. It stays attached between sessions as a secondary display. Apollo manages its attachment state. Unplugging it via Windows APIs produces a detached state that cannot be recovered without restarting Apollo.

Important behavior:

- Display restore is required for success exit code.
- Audio restore is best-effort with warning if unavailable.
- Moonlight window move to internal is best-effort.

When this is used manually:

- `restore` is still available as a manual recovery command if a previous session was interrupted unexpectedly.

## Where To Adjust Settings

Primary config file: `re_stack_config.json` (project root).

| Key | Purpose |
|---|---|
| `moonlight_dir` | Path to Moonlight portable directory |
| `vdd_attach_timeout_seconds` | How long to wait for VDD to appear at start |
| `fullscreen_confirm_seconds` | How long gameplay window must be visible before moving Moonlight to CRT |
| `display.re_primary_token` | Token for Moonlight virtual display (set as primary during RE) |
| `display.crt_token` | Token for CRT display (refresh enforcement + rect detection) |
| `display.crt_target_refresh_hz` | Target CRT refresh rate |
| `display.restore_primary_token` | Token for internal display (restored after RE) |
| `display.required_groups` | Token lists for internal, CRT, and Moonlight display validation |
| `audio.re_device_token` | Audio device token for RE session |
| `audio.restore_device_token` | Audio device token restored after session |
| `game_profiles` | Map of game key → profile JSON path |

Per-game `gameplay_title` field: set in each profile JSON (e.g. `re1-gog.json`). This is the window title substring that distinguishes the gameplay window from the config screen. Used as the CRT-move trigger. See "Gameplay Window Detection" in `resident-evil-stack-code-flow.md`.

To change internal behavior (not just tokens), the relevant session module is:

- Display switching logic: `session/display_api.py`
- VDD attach logic: `session/vdd.py`
- Audio switching logic: `session/audio.py`
- Moonlight process and window logic: `session/moonlight.py`

## State File

State snapshot path:

- `runtime/re_stack_state.json`

Current key used:

- `previous_primary_device_name`

This is used to restore the exact previous primary display after RE mode. Always written at session start (even if empty string) to prevent stale data from a previous session being used.

## Audio Switching Backends

Preferred:

- PowerShell module `AudioDeviceCmdlets`

Fallback:

- `nircmd.exe` (if present in `PATH`)

If neither is available:

- Script logs warning and continues.
- Display switching and launch/restore still run.

## Troubleshooting

1. `start` fails before launching:
   - Run `python launch_resident_evil_stack.py inspect`
   - Confirm Moonlight display token resolves to the expected `SudoMaker Virtual Display`.
2. `restore` sends primary to wrong display:
   - Check `runtime/re_stack_state.json` contents.
   - Confirm fallback token matches intended internal display.
3. Audio does not switch automatically:
   - Install `AudioDeviceCmdlets` or provide `nircmd.exe`.
   - Re-run `inspect` and check `Audio switch tool`.
4. Wrapper keeps enforcing after restore:
   - Re-run `python launch_resident_evil_stack.py restore`
   - Confirm no lingering `launchbox_generic_wrapper.py` processes.
5. VDD did not attach within timeout:
   - The SudoMaker VDD is managed by Apollo. Confirm Apollo is running.
   - Check the diagnostic output: `VDD diag:` lines show all adapters and their `attached` state.
   - If all SudoMaker entries show `attached=False`: restart Apollo. The script will attempt recovery via mode enumeration, but Apollo must be running for the VDD to function.
6. Moonlight window did not move to CRT when game started:
   - Confirm the profile has a `gameplay_title` field.
   - The title must be a substring of the actual gameplay window title and must NOT appear in the config/launcher screen titles.
   - Fallback (no `gameplay_title`): WS_CAPTION absence check — less reliable for Moonlight.
