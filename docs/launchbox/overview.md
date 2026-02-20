# LaunchBox / BigBox Integration Overview

## Purpose

Run LaunchBox/BigBox on the primary display while moving launched game windows to CRT coordinates.

## Integration Modes

### Watcher Mode

- Script: `launchbox_crt_watcher.py`
- Behavior:
  - monitors running processes/windows
  - matches target games via process names and parent-process heuristics
  - repositions matching windows to CRT bounds

### Wrapper Mode

- Scripts under `integrations/launchbox/wrapper/`
- Behavior:
  - LaunchBox emulator `ApplicationPath` points to wrapper `.bat`
  - wrapper launches emulator/game and stabilizes startup window placement

## Wrapper Installer Script

Script: `scripts/install_launchbox_wrapper.py`

- default run validates wrapper files
- `--global` can patch `D:\LaunchBox\Data\Emulators.xml` for RetroArch/PPSSPP/Dolphin/PCSX2 wrapper paths
- script also removes fullscreen-forcing arguments where those conflict with wrapper placement behavior

## Recommended Current Pattern

1. Use wrapper mode for emulator startup stability.
2. Use watcher mode when dealing with non-wrapper titles or parent-process launches.
3. Keep LaunchBox and BigBox process names in ignore lists.
4. Tune process name filters first before increasing polling complexity.

## Generic Wrapper

Use `docs/launchbox/generic-wrapper.md` for:

- CLI options
- launch examples
- filter/timing tuning
- troubleshooting
