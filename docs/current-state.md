# Current State

Last updated: 2026-02-20

## Project Scope

CRT Unified Launcher is a Windows-focused launcher and window-placement system for:

- RetroArch gaming workflows
- Plex cinema workflows
- LaunchBox/BigBox game launch flows

Core objective: keep target app windows on calibrated CRT coordinates and restore to primary monitor coordinates on stop/exit workflows.

## What Is Implemented

- Unified launcher menu in `crt_master.py`
- Per-app launchers:
  - `launch_ra.py`
  - `launch_plex.py`
- LaunchBox support:
  - watcher-based flow in `launchbox_crt_watcher.py`
  - session patch flow in `launchbox_session_mode.py`
  - per-emulator wrappers under `integrations/launchbox/wrapper/`
  - configurable generic wrapper in `integrations/launchbox/wrapper/launchbox_generic_wrapper.py`
- Shared config in `crt_config.json`
- Installer/patch helper for LaunchBox emulator wrappers in `scripts/install_launchbox_wrapper.py`

## Documentation State

- Root docs are now modularized under `docs/`.
- Legacy document locations are retained as pointer files for compatibility.

## Known Scaling Pressure

- `crt_config.json` is currently used for both global and per-emulator values.
- As more game-specific entries are added, central config complexity increases.
- The roadmap in `docs/roadmaps/generic-wrapper-scaling-todo.md` tracks migration toward profile-based wrapper config.

## Recommended Current Workflow

1. Keep global monitor/layout behavior in `crt_config.json`.
2. Use LaunchBox wrapper scripts for emulator startup stability.
3. Prefer generic wrapper for new integrations where possible.
4. Use debug logs when tuning window filters/timings.
