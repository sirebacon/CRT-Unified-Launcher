# Architecture

## Core Components

- `crt_master.py`
  - user-facing menu entrypoint
  - dispatches to RetroArch/Plex/session flows
- `launch_ra.py`
  - RetroArch-specific launch + window lock loop
- `launch_plex.py`
  - Plex launch + window lock loop with border/style handling
- `launchbox_crt_watcher.py`
  - process/window watcher for LaunchBox/BigBox-launched games
- `launchbox_session_mode.py`
  - temporary config/session orchestration for LaunchBox flow

## LaunchBox Wrappers

Folder: `integrations/launchbox/wrapper/`

- per-emulator wrappers:
  - RetroArch, PPSSPP, Dolphin, PCSX2
- generic wrapper:
  - `launchbox_generic_wrapper.py` (parameterized behavior)

## Shared Configuration

- `crt_config.json` is the primary runtime configuration source.
- Wrappers and launchers resolve executable paths and geometry from this file.

## Generic Wrapper Runtime Model

1. Parse wrapper args.
2. Resolve executable and launch arguments.
3. Launch emulator process.
4. Enumerate windows and select best candidate for tracked PID/process criteria.
5. Enforce target rectangle during startup lock period.
6. Stop enforcement on timeout, stop-flag, or primary-monitor handoff.
7. Return child process exit code.

Full wrapper details: `docs/launchbox/generic-wrapper.md`

## Operational Notes

- Some workflows create runtime artifacts in repo root (for example debug logs and `wrapper_stop_enforce.flag`).
- Keep these artifacts out of commits unless intentionally documenting/debugging behavior.
