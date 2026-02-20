# Setup and Requirements

## Platform

- Windows
- Python 3.10+ recommended

## Required Python Packages

- `pywin32`
- `keyboard` (live calibration script)
- `pygetwindow` (inspector script)
- `psutil` (process-tree detection for watcher/wrapper flows)

Install:

```powershell
pip install pywin32 keyboard pygetwindow psutil
```

## Required Apps (Typical)

- RetroArch
- Plex Desktop
- Optional emulator installs used by LaunchBox wrappers (Dolphin, PPSSPP, PCSX2, etc.)

## First-Time Validation

1. Confirm `crt_config.json` has valid executable `path` and `dir` values.
2. Run a direct launcher once:
   - `python launch_ra.py`
   - `python launch_plex.py`
3. If using LaunchBox wrappers, verify wrapper batch paths exist under:
   - `integrations/launchbox/wrapper/`
