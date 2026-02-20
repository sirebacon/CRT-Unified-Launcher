# Generic LaunchBox Wrapper Guide

This document explains `integrations/launchbox/wrapper/launchbox_generic_wrapper.py`, what it does, and how to use it from LaunchBox/BigBox.

## What It Does

The generic wrapper is a configurable startup wrapper for emulators that:

- launches an emulator from `crt_config.json` or a profile file
- forwards LaunchBox game arguments to that emulator
- finds the emulator window during startup
- repeatedly snaps that window to your CRT target rectangle
- stops enforcing after a lock timeout, or when a stop flag is set

It is designed to replace per-emulator one-off logic with one script and per-emulator arguments.

## Two Modes

### Profile mode (recommended for new integrations)

Pass `--profile-file` pointing to a JSON file under `integrations/launchbox/wrapper/profiles/`. The profile holds the exe path, optional rect, process filters, and timing overrides for that specific game.

### Config-key mode (legacy, still fully supported)

Pass `--config-key` to look up the emulator exe and rect directly from `crt_config.json`. This is how Dolphin, PPSSPP, and PCSX2 are currently wired.

These two modes are mutually exclusive — use one or the other, not both.

## Runtime Flow

1. Parse wrapper arguments.
2. Load `crt_config.json`.
3. If `--profile-file`: load profile, merge into resolved config (CLI > profile > crt_config.json defaults).
4. If `--config-key`: resolve exe and rect from `crt_config.json` directly.
5. Resolve timing defaults for any values not explicitly set.
6. Build launch command:
   - emulator exe
   - repeated `--set KEY=VALUE` converted into `-C KEY=VALUE`
   - repeated `--arg-pre` values
   - LaunchBox passthrough args (ROM path, platform args, etc.)
7. Launch the process.
8. During lock window (`--max-lock-seconds`):
   - get process tree PIDs (if `psutil` is available)
   - find best matching top-level visible window by PID/filters
   - move it to target rect when it drifts
9. Exit with emulator exit code.

## Profile File Format

Profile files live in `integrations/launchbox/wrapper/profiles/`. See `template.json` for
a full example. All keys except `path` are optional.

Required fields:

- `path` — absolute path to the emulator or game exe

Optional fields:

- `dir` — working directory for launch (defaults to folder containing `path`)
- `profile_version` — currently `1`; include for forward compatibility
- `base` — filename or path of a base profile to inherit from (single level, shallow merge)
- `x`, `y`, `w`, `h` — target CRT rect; falls back to `launcher_integration` then `retroarch` in `crt_config.json`
- `process_name` — list of lowercase exe names for window matching
- `class_contains` — list of window class substrings
- `title_contains` — list of window title substrings
- `arg_pre` — list of arguments prepended before passthrough args
- `set_values` — list of `KEY=VALUE` strings emitted as `-C KEY=VALUE`
- `max_lock_seconds` — default from `profiles/defaults.json`, then `120.0`
- `fast_seconds` — default from `profiles/defaults.json`, then `8.0`
- `poll_fast` — default from `profiles/defaults.json`, then `0.1`
- `poll_slow` — default from `profiles/defaults.json`, then `0.4`
- `position_only` — if `true`, only enforce x,y position; do not fight window size

Keys starting with `_` (e.g. `_notes`, `_window_sequence`) are metadata and are ignored
by the wrapper.

### Precedence

For all values: **CLI args > profile > `profiles/defaults.json` > `crt_config.json` > hardcoded defaults**.

For list values (`process_name`, `class_contains`, `title_contains`, `arg_pre`, `set_values`):
profile provides the base list, CLI args are appended on top.

### Variable expansion

The following variables are expanded in string and list-of-string values, after inheritance
merge and before validation:

- `%PROJECT_ROOT%` — absolute path to the CRT Unified Launcher project root
- `%GAME_DIR%` — value of the profile's `dir` field

### Profile inheritance

Add a `"base"` key pointing to another profile file. The base is loaded first and the
current profile's keys override it. Single level only — the base profile itself cannot
have a `base`.

```json
{
  "base": "gog-defaults.json",
  "path": "D:\\GOG Galaxy\\Games\\MyGame\\game.exe",
  "process_name": ["game.exe"]
}
```

### Shared timing defaults

`profiles/defaults.json` holds timing values that apply to all profiles unless overridden.
Edit it to change the global defaults without touching individual profiles.

### Path quoting rules

- Profile `path` and `dir` values: use double backslashes (`\\`) in JSON strings.
  - Correct: `"D:\\GOG Galaxy\\Games\\RE1\\Biohazard.exe"`
  - Wrong: `"D:\GOG Galaxy\Games\RE1\Biohazard.exe"` (backslash is an escape character in JSON)
- Paths with spaces in `--profile-file` or `--fallback-exe` CLI arguments: wrap in quotes.
  - PowerShell: `--profile-file "path with spaces\re1-gog.json"`
  - Batch: `--profile-file "%SCRIPT_DIR%profiles\re1-gog.json"` (use `%VAR%` expansion)

## Important Concepts

### Argument pass-through

Wrapper-only arguments are removed before launching the emulator. Everything else is forwarded.

### Window selection

The wrapper picks the largest visible non-minimized window that matches:

- tracked process tree PIDs
- optional class filter (`--class-contains` or profile `class_contains`)
- optional title filter (`--title-contains` or profile `title_contains`)
- optional process-name filter (`--process-name` or profile `process_name`)

### Stop flag

If `wrapper_stop_enforce.flag` exists in project root, startup enforcement is disabled.

### Primary monitor handoff

If the tracked window lands on `launcher_integration.primary_on_exit`, enforcement stops. This prevents fighting with your watcher/session cleanup.

## CLI Reference

Mode (required, mutually exclusive):

- `--profile-file <path>`: path to a profile JSON file
- `--config-key <key>`: key under `crt_config.json` (examples: `dolphin`, `ppsspp`, `pcsx2`)

Path and launch options:

- `--fallback-exe <path>` (repeatable)
- `--arg-pre <value>` (repeatable)
- `--set <KEY=VALUE>` (repeatable, emitted as `-C KEY=VALUE`)

Timing (all optional; profile or hardcoded defaults apply if omitted):

- `--max-lock-seconds <float>`
- `--fast-seconds <float>`
- `--poll-fast <float>`
- `--poll-slow <float>`

Window filters:

- `--class-contains <text>` (repeatable)
- `--title-contains <text>` (repeatable)
- `--process-name <exe-name>` (repeatable)

Behavior flags:

- `--position-only` — only enforce x,y position; do not fight window size
- `--validate-only` — validate profile and resolved exe, then exit without launching
- `--dry-run` — print resolved config and launch command, then exit without launching

Debug:

- `--debug`
- `--debug-log <path>`

## Usage Examples

### Profile mode — RE1 via GOG

```powershell
python integrations\launchbox\wrapper\launchbox_generic_wrapper.py `
  --profile-file integrations\launchbox\wrapper\profiles\re1-gog.json `
  --debug
```

LaunchBox provides the ROM/game path automatically as a passthrough arg.

### Profile mode — override timing at the command line

```powershell
python integrations\launchbox\wrapper\launchbox_generic_wrapper.py `
  --profile-file integrations\launchbox\wrapper\profiles\re2-gog.json `
  --max-lock-seconds 60 `
  --debug
```

### Config-key mode — Dolphin

```powershell
python integrations\launchbox\wrapper\launchbox_generic_wrapper.py `
  --config-key dolphin `
  --set Dolphin.Display.Fullscreen=False `
  --process-name dolphin.exe `
  --class-contains dolphin `
  --debug `
  -- "D:\Roms\Game.iso"
```

### Config-key mode — PPSSPP with fallbacks

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

### Profile mode (new games)

Point the LaunchBox emulator `ApplicationPath` to a `.bat` that calls the wrapper with `--profile-file`:

```bat
@echo off
setlocal
set SCRIPT_DIR=%~dp0

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT_DIR%launchbox_generic_wrapper.py" --profile-file "%SCRIPT_DIR%profiles\re1-gog.json" %*
  exit /b %errorlevel%
)

py -3 "%SCRIPT_DIR%launchbox_generic_wrapper.py" --profile-file "%SCRIPT_DIR%profiles\re1-gog.json" %*
exit /b %errorlevel%
```

### Config-key mode (existing emulators)

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
- inspect `<slug>_wrapper_debug.log` in repo root (slug = config key or profile filename without extension)
- add `process_name` to the profile when the emulator spawns a child process
- add `class_contains` or `title_contains` if multiple windows exist

Window jumps back during startup:

- increase `max_lock_seconds` in the profile
- increase `fast_seconds` in the profile

Wrong monitor/position:

- set `x`, `y`, `w`, `h` explicitly in the profile
- verify `launcher_integration.primary_on_exit` is correct for your main display

Executable not found:

- verify `path` and `dir` in the profile
- provide one or more `--fallback-exe` values on the command line
