# Current State

Last updated: 2026-02-20

## Project Scope

CRT Unified Launcher is a Windows-focused launcher and window-placement system for:

- RetroArch standalone gaming
- LaunchBox/BigBox multi-emulator gaming sessions
- Plex cinema workflows

Core objective: keep emulator windows on calibrated CRT coordinates and restore everything to primary-monitor coordinates when the session ends.

## What Is Implemented

### Unified Launcher

- `crt_master.py` — interactive menu with 6 options:
  1. RetroArch standalone launch and window lock
  2. LaunchBox CRT Watcher (legacy mode, still functional)
  3. LaunchBox Gaming Session (current recommended mode)
  4. Plex launch and window lock
  5. Restore Default Settings
  6. Exit

### Gaming Session (Option 3) — Primary Workflow

- `launch_session.py` — orchestrator: loads manifest, patches configs, launches LaunchBox, runs watcher, restores configs on exit
- `session/` package:
  - `session/manifest.py` — loads and validates `gaming-manifest.json`
  - `session/patcher.py` — dispatches patch handlers, backs up before patching, restores on exit
  - `session/watcher.py` — multi-target poll loop; locks emulator windows to CRT; supports soft stop and reattach
  - `session/backup.py` — numbered backup files with JSON manifest, per-file restore failure logging
  - `session/window_utils.py` — shared Win32 helpers (find window, move window, enumerate PIDs)
  - `session/patches/retroarch.py` — patches `retroarch.cfg` key/value pairs
  - `session/patches/launchbox.py` — patches `Emulators.xml`, `BigBoxSettings.xml`, `Settings.xml`
- `validate_session.py` — dry-run tool: backs up, patches, and restores without permanent changes
- `profiles/gaming-manifest.json` — session configuration (what to patch, what to watch)
- `profiles/launchbox-session.json`, `retroarch-session.json`, `dolphin-session.json`, `ppsspp-session.json`, `pcsx2-session.json` — per-app window tracking profiles

### LaunchBox Wrappers

- `integrations/launchbox/wrapper/launchbox_generic_wrapper.py` — configurable per-game startup wrapper
- Per-emulator wrapper batch files under `integrations/launchbox/wrapper/`
- Per-game profiles under `integrations/launchbox/wrapper/profiles/`

### Other

- `launch_plex.py` — Plex launch and window lock loop
- `launch_generic.py` — standalone single-profile window locker (used by option 1 / RetroArch mode)
- `default_restore.py` — restores default settings from backup
- `scripts/` — helper utilities (generate LaunchBox commands, check drift, installer)
- `tools/` — calibration and inspector utilities

## Recommended Workflow

1. Run `python crt_master.py`.
2. Choose **option 3** to start a gaming session:
   - LaunchBox/BigBox opens on the main screen.
   - Emulator configs are patched automatically.
   - Any emulator launched from BigBox is moved to the CRT.
   - Ctrl+C once: moves emulators to main screen, session stays alive (swap games).
   - Ctrl+C twice within 8 seconds: ends session and restores all configs.
3. If LaunchBox is already open, option 3 reattaches the watcher and still patches emulator configs.

## Known Gaps

- Steam/GOG games that run under a different process name than what is in their watch profile are not tracked. This is an accepted limitation for v1.
- Two instances of the same emulator: only the first (by PID order) is tracked. The second floats uncontrolled.
- `launchbox_settings` patches (BigBoxSettings.xml, Settings.xml) have no effect in reattach mode since LaunchBox already loaded them at startup.

