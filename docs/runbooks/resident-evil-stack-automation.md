# Runbook: Resident Evil Stack Automation

Date: 2026-02-21

## Purpose

Automate a repeatable Resident Evil launch mode for CRT use, then cleanly restore system state afterward.

Script:

- `launch_resident_evil_stack.py`

Menu integration:

- `crt_master.py` option `5` -> start Resident Evil stack
- `crt_master.py` option `7` -> restore Resident Evil stack

## Commands

Direct commands from project root:

```powershell
python launch_resident_evil_stack.py inspect
python launch_resident_evil_stack.py start --game re1
python launch_resident_evil_stack.py start --game re2
python launch_resident_evil_stack.py start --game re3
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
5. Current audio name tokens configured in script.

Use this first when changing display/audio names.

## What `start --game reX` Does

Order of operations:

1. Clears stale wrapper stop flag:
   - `wrapper_stop_enforce.flag` (if present)
2. Ensures Moonlight is running from:
   - `D:\Emulators\MoonlightPortable-x64-6.1.0\Moonlight.exe`
   - If not running, script attempts to launch it and waits for process detection.
3. Ensures required displays are present before continuing:
   - Internal display (`Internal Display` or `Intel(R) UHD Graphics`)
   - CRT display (`CP-1262HE` or `NVIDIA GeForce RTX 4090 Laptop GPU`)
   - Moonlight display (`SudoMaker Virtual Display`)
4. Moves Moonlight window to CRT usable rect.
   - Rect source: `crt_config.json` -> `launcher_integration` `x/y/w/h`
5. Captures current primary display device name and writes to:
   - `runtime/re_stack_state.json`
6. Sets primary display to Moonlight virtual display (`SudoMaker Virtual Display`):
   - Forces Resident Evil to render on the Moonlight virtual display.
   - Moonlight client streams the output to the CRT.
7. Attempts to set default playback device to token:
   - `CP-1262HE (NVIDIA High Definition Audio)`
8. Launches game via:
   - `integrations/launchbox/wrapper/launchbox_generic_wrapper.py`
   - profile file selected by `--game`:
     - `re1` -> `integrations/launchbox/wrapper/profiles/re1-gog.json`
     - `re2` -> `integrations/launchbox/wrapper/profiles/re2-gog.json`
     - `re3` -> `integrations/launchbox/wrapper/profiles/re3-gog.json`
9. Automatically runs full restore flow when the launched process ends, crashes, or `Ctrl+C` is pressed.

Important behavior:

- Primary-display switch to Moonlight virtual display is required. If it fails, launch aborts.
- Moonlight running requirement is required. If it fails, launch aborts.
- Required display set check is required. If it fails, launch aborts.
- Moonlight window placement to CRT usable rect is required. If it fails, launch aborts.
- Audio switch is best-effort. If it fails, launch continues with warning.
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
6. Attempts to set default playback device to token:
   - `Speakers (Realtek(R) Audio)`

Important behavior:

- Display restore is required for success exit code.
- Audio restore is best-effort with warning if unavailable.

When this is used manually:

- `restore` is still available as a manual recovery command if a previous session was interrupted unexpectedly.

## Where To Adjust Settings

All adjustable constants are in `launch_resident_evil_stack.py`:

- `RE_PRIMARY_DISPLAY_TOKEN`
- `RE_AUDIO_DEVICE_TOKEN`
- `CRT_DISPLAY_TOKEN` — display token used for CRT refresh enforcement (must match DISPLAY5)
- `CRT_TARGET_REFRESH_HZ`
- `RESTORE_PRIMARY_DISPLAY_TOKEN`
- `RESTORE_AUDIO_DEVICE_TOKEN`
- `GAME_PROFILES`
- `REQUIRED_DISPLAY_GROUPS`

If display names or audio labels change, update these constants first.

## State File

State snapshot path:

- `runtime/re_stack_state.json`

Current key used:

- `previous_primary_device_name`

This is used to restore the exact previous primary display after RE mode.

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
