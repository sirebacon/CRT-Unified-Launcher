# CRT Unified Launcher

Windows-based launcher and window-lock system for running **RetroArch** (gaming) and **Plex** (cinema) on a CRT setup with fixed coordinates.

The project keeps app windows snapped to calibrated CRT bounds, and returns them to a primary monitor when you stop the script with `Ctrl+C`.

## Features

- Unified menu launcher (`crt_master.py`) for RetroArch or Plex
- Per-app launchers:
- `launch_ra.py` for RetroArch
- `launch_plex.py` for Plex
- Shared JSON config (`crt_config.json`) for paths and target window geometry
- Utility tools in `tools/` for calibration, inspection, and older standalone workflows

## Requirements

- Windows
- Python 3.10+ (recommended)
- Installed apps:
- RetroArch
- Plex Desktop
- Python packages:
- `pywin32`
- `keyboard` (for live calibration script)
- `pygetwindow` (for inspector script)

Install dependencies:

```powershell
pip install pywin32 keyboard pygetwindow
```

## Project Structure

- `crt_master.py`: main text menu that launches `launch_ra.py` or `launch_plex.py`
- `launch_ra.py`: launches/locks RetroArch window using `crt_config.json`
- `launch_plex.py`: launches/locks Plex window using `crt_config.json` and removes borders while locked
- `crt_config.json`: shared coordinates + executable paths
- `tools/retro.py`: older standalone RetroArch locker with hardcoded values
- `tools/plex.py`: older standalone Plex locker + INI sync with hardcoded values
- `tools/multi.py`: older all-in-one launcher with hardcoded profiles
- `tools/plex_callibrate.py`: interactive live Plex calibration (arrow keys/WASD)
- `tools/inspectRetro.py`: live position/size inspector (currently searches title `plex`)

## Configuration

Edit `crt_config.json`:

```json
{
  "retroarch": {
    "x": -1211,
    "y": 43,
    "w": 1057,
    "h": 835,
    "path": "D:\\RetroArch-Win64\\retroarch.exe",
    "dir": "D:\\RetroArch-Win64"
  },
  "plex": {
    "x": -1883,
    "y": 130,
    "w": 1720,
    "h": 1184,
    "path": "C:\\Program Files\\Plex\\Plex\\Plex.exe",
    "dir": "C:\\Program Files\\Plex\\Plex"
  }
}
```

Notes:
- Negative `x`/`y` values are expected when the CRT is positioned left/up of the primary monitor in Windows display layout.
- `path` must point to the executable.
- `dir` should be the executable working directory.

## Usage

Run the unified launcher:

```powershell
python crt_master.py
```

Menu options:
- `1`: launch/lock RetroArch
- `2`: launch/lock Plex
- `3`: exit menu

Or run directly:

```powershell
python launch_ra.py
python launch_plex.py
```

While active, each launcher re-checks the app window every second and snaps it back if it drifts or resizes.  
Press `Ctrl+C` to stop and return the window to a primary monitor position.

## Calibration Tools

- Live Plex calibration:

```powershell
python tools\plex_callibrate.py
```

Controls:
- Arrow keys move window
- `W/A/S/D` resize window
- Hold `Shift` for 1px precision
- `Ctrl+C` prints final coordinates

- Inspector:

```powershell
python tools\inspectRetro.py
```

Displays live position/size and a copy-paste config snippet.

## Notes

- The `tools/` scripts are mostly legacy/hardcoded variants; `crt_master.py` + `launch_*.py` + `crt_config.json` are the current config-driven path.
- `launch_plex.py` sets DPI awareness and strips title bar while locked for more reliable placement.

