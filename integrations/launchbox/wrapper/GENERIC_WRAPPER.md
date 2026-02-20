# Generic LaunchBox Wrapper Guide

This document explains `integrations/launchbox/wrapper/launchbox_generic_wrapper.py`, what it does, and how to use it from LaunchBox/BigBox.

## What It Does

The generic wrapper is a configurable startup wrapper for emulators that:

- launches an emulator from `crt_config.json`
- forwards LaunchBox game arguments to that emulator
- finds the emulator window during startup
- repeatedly snaps that window to your CRT target rectangle
- stops enforcing after a lock timeout, or when a stop flag is set

It is designed to replace per-emulator one-off logic with one script and per-emulator arguments.

## Runtime Flow

1. Parse wrapper arguments (`--config-key`, timing options, window filters, debug options).
2. Load `crt_config.json`.
3. Resolve executable path from `<config-key>.path`, or from `--fallback-exe`.
4. Resolve target rectangle using this fallback order:
   - `<config-key>.x/y/w/h`
   - `launcher_integration.x/y/w/h`
   - `retroarch.x/y/w/h`
5. Build launch command:
   - emulator exe
   - repeated `--set KEY=VALUE` converted into `-C KEY=VALUE`
   - repeated `--arg-pre` values
   - LaunchBox passthrough args (ROM path, platform args, etc.)
6. Launch the process.
7. During lock window (`--max-lock-seconds`):
   - get process tree PIDs (if `psutil` is available)
   - find best matching top-level visible window by PID/filters
   - move it to target rect when it drifts
8. Exit with emulator exit code.

## Important Concepts

### Argument pass-through

Wrapper-only arguments are removed before launching the emulator. Everything else is forwarded.

### Window selection

The wrapper picks the largest visible non-minimized window that matches:

- tracked process tree PIDs
- optional class filter (`--class-contains`)
- optional title filter (`--title-contains`)
- optional process-name filter (`--process-name`)

### Stop flag

If `wrapper_stop_enforce.flag` exists in project root, startup enforcement is disabled.

### Primary monitor handoff

If the tracked window lands on `launcher_integration.primary_on_exit`, enforcement stops. This prevents fighting with your watcher/session cleanup.

## CLI Reference

Required:

- `--config-key <key>`: key under `crt_config.json` (examples: `dolphin`, `ppsspp`, `pcsx2`)

Path and launch options:

- `--fallback-exe <path>` (repeatable)
- `--arg-pre <value>` (repeatable)
- `--set <KEY=VALUE>` (repeatable, emitted as `-C KEY=VALUE`)

Timing:

- `--max-lock-seconds <float>` default `120.0`
- `--fast-seconds <float>` default `8.0`
- `--poll-fast <float>` default `0.1`
- `--poll-slow <float>` default `0.4`

Window filters:

- `--class-contains <text>` (repeatable)
- `--title-contains <text>` (repeatable)
- `--process-name <exe-name>` (repeatable)

Debug:

- `--debug`
- `--debug-log <path>`

## Usage Examples

Direct PowerShell use:

```powershell
python integrations\launchbox\wrapper\launchbox_generic_wrapper.py `
  --config-key dolphin `
  --set Dolphin.Display.Fullscreen=False `
  --process-name dolphin.exe `
  --class-contains dolphin `
  --debug `
  -- "D:\Roms\Game.iso"
```

PPSSPP with fallbacks:

```powershell
python integrations\launchbox\wrapper\launchbox_generic_wrapper.py `
  --config-key ppsspp `
  --fallback-exe D:\Emulators\PPSSPPWindowsGold\PPSSPPWindows64.exe `
  --fallback-exe D:\Emulators\PPSSPPWindowsGold\PPSSPPWindows.exe `
  --process-name ppssppwindows64.exe `
  --process-name ppssppwindows.exe `
  --debug `
  -- "D:\Roms\PSP\Game.cso"
```

Notes:

- `--` is optional for this script, but useful for readability when separating wrapper args from ROM/path args.
- LaunchBox usually provides passthrough args automatically.

## LaunchBox Integration Pattern

Point LaunchBox emulator `ApplicationPath` to a `.bat` wrapper that calls the generic script with your chosen wrapper options.

Minimal batch template:

```bat
@echo off
setlocal
set SCRIPT_DIR=%~dp0

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT_DIR%launchbox_generic_wrapper.py" --config-key dolphin --process-name dolphin.exe %*
  exit /b %errorlevel%
)

py -3 "%SCRIPT_DIR%launchbox_generic_wrapper.py" --config-key dolphin --process-name dolphin.exe %*
exit /b %errorlevel%
```

Then remove always-fullscreen platform args from LaunchBox for that emulator, so the wrapper can consistently place windows.

## Troubleshooting

No window gets moved:

- run with `--debug`
- inspect `<config-key>_wrapper_debug.log` in repo root
- add `--process-name` filters when emulator spawns a child process
- add `--class-contains` or `--title-contains` if multiple windows exist

Window jumps back during startup:

- increase `--max-lock-seconds`
- increase `--fast-seconds`

Wrong monitor/position:

- verify `<config-key>.x/y/w/h` in `crt_config.json`
- verify `launcher_integration.primary_on_exit` is correct for your main display

Executable not found:

- set `<config-key>.path` in `crt_config.json`
- provide one or more `--fallback-exe` values
