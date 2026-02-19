# CRT Unified Launcher

Windows-based launcher and window-lock system for running **RetroArch** (gaming) and **Plex** (cinema) on a CRT setup with fixed coordinates.

The project keeps app windows snapped to calibrated CRT bounds, and returns them to a primary monitor when you stop the script with `Ctrl+C`.

## Features

- Unified menu launcher (`crt_master.py`) for RetroArch or Plex
- Per-app launchers:
- `launch_ra.py` for RetroArch
- `launch_plex.py` for Plex
- `launchbox_crt_watcher.py` for LaunchBox/BigBox game launches
- LaunchBox RetroArch wrapper in `integrations/launchbox/wrapper/`
- LaunchBox PPSSPP wrapper in `integrations/launchbox/wrapper/`
- LaunchBox Dolphin wrapper in `integrations/launchbox/wrapper/`
- LaunchBox PCSX2 wrapper in `integrations/launchbox/wrapper/`
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
- `psutil` (for LaunchBox/BigBox watcher process detection)

Install dependencies:

```powershell
pip install pywin32 keyboard pygetwindow psutil
```

## Project Structure

- `crt_master.py`: main text menu that launches `launch_ra.py` or `launch_plex.py`
- `launch_ra.py`: launches/locks RetroArch window using `crt_config.json`
- `launch_plex.py`: launches/locks Plex window using `crt_config.json` and removes borders while locked
- `launchbox_crt_watcher.py`: keeps LaunchBox/BigBox on primary while moving matching game windows to CRT
- `launchbox_session_mode.py`: applies temporary CRT session patches for option `2`, then restores defaults
- `integrations/launchbox/wrapper/launchbox_retroarch_wrapper.py`: wrapper for stable LaunchBox RetroArch startup behavior
- `integrations/launchbox/wrapper/launchbox_retroarch_wrapper.bat`: LaunchBox entry point for wrapper
- `integrations/launchbox/wrapper/launchbox_ppsspp_wrapper.py`: wrapper for stable LaunchBox PPSSPP startup behavior
- `integrations/launchbox/wrapper/launchbox_ppsspp_wrapper.bat`: LaunchBox entry point for PPSSPP wrapper
- `integrations/launchbox/wrapper/launchbox_dolphin_wrapper.py`: wrapper for stable LaunchBox Dolphin startup behavior
- `integrations/launchbox/wrapper/launchbox_dolphin_wrapper.bat`: LaunchBox entry point for Dolphin wrapper
- `integrations/launchbox/wrapper/launchbox_pcsx2_wrapper.py`: wrapper for stable LaunchBox PCSX2 startup behavior
- `integrations/launchbox/wrapper/launchbox_pcsx2_wrapper.bat`: LaunchBox entry point for PCSX2 wrapper
- `scripts/install_launchbox_wrapper.py`: backup + patch helper to wire LaunchBox RetroArch/PPSSPP/Dolphin/PCSX2 to wrappers
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
  },
  "ppsspp": {
    "path": "D:\\PPSSPPWindowsGold\\PPSSPPWindows64.exe",
    "dir": "D:\\PPSSPPWindowsGold"
  },
  "dolphin": {
    "path": "D:\\Dolphin-x64\\Dolphin.exe",
    "dir": "D:\\Dolphin-x64"
  },
  "pcsx2": {
    "path": "D:\\Pcsx2\\pcsx2-qt.exe",
    "dir": "D:\\Pcsx2"
  },
  "launcher_integration": {
    "enabled": true,
    "x": -1211,
    "y": 43,
    "w": 1057,
    "h": 835,
    "poll_seconds": 0.5,
    "target_processes": [
      "retroarch.exe",
      "dolphin.exe",
      "ppssppwindows64.exe",
      "ppssppwindows.exe"
    ],
    "target_parent_processes": [
      "steam.exe",
      "galaxyclient.exe",
      "goggalaxy.exe"
    ],
    "ignore_processes": [
      "launchbox.exe",
      "bigbox.exe"
    ],
    "primary_on_exit": {
      "x": 100,
      "y": 100,
      "w": 1280,
      "h": 720
    }
  }
}
```

Notes:
- Negative `x`/`y` values are expected when the CRT is positioned left/up of the primary monitor in Windows display layout.
- `path` must point to the executable.
- `dir` should be the executable working directory.
- For Steam/GOG titles, add known game executable names to `launcher_integration.target_processes` if parent-process detection misses a title.

## Usage

Run the unified launcher:

```powershell
python crt_master.py
```

Menu options:
- `1`: launch/lock RetroArch
- `2`: LaunchBox session mode (temporary CRT profile + watcher)
- `3`: launch/lock Plex
- `4`: exit menu

Or run directly:

```powershell
python launch_ra.py
python launch_plex.py
python launchbox_crt_watcher.py
```

While active, each launcher re-checks the app window every second and snaps it back if it drifts or resizes.  
Press `Ctrl+C` to stop and return the window to a primary monitor position.

## LaunchBox / BigBox Integration

1. Keep using LaunchBox/BigBox on your main display.
2. Start the watcher before launching games:

```powershell
python launchbox_crt_watcher.py
```

3. Launch games normally from LaunchBox/BigBox.
4. Matching game windows are moved to CRT bounds from `launcher_integration`.

Current detection:
- Direct executable match via `target_processes` (best for RetroArch, Dolphin, PPSSPP, specific Steam/GOG game EXEs)
- Parent-process match via `target_parent_processes` (`steam.exe`, `galaxyclient.exe`, `goggalaxy.exe`)

Recommended tuning:
- Add exact game EXE names to `target_processes` for Steam/GOG titles that do not inherit expected parents.
- Keep `launchbox.exe` and `bigbox.exe` in `ignore_processes` so frontends stay on the main screen.

### Install Wrapper (From Scratch)

If you need to re-wire LaunchBox to the RetroArch wrapper manually:

```powershell
python scripts\install_launchbox_wrapper.py
```

This script:
- default mode is session-only-safe: validates wrapper files and makes no global LaunchBox changes
- to force global patching, run:

```powershell
python scripts\install_launchbox_wrapper.py --global
```

Global mode will:
- create a timestamped backup of `D:\LaunchBox\Data\Emulators.xml`
- set RetroArch emulator `ApplicationPath` to:
`..\CRT Unified Launcher\integrations\launchbox\wrapper\launchbox_retroarch_wrapper.bat`
- set PPSSPP emulator `ApplicationPath` to:
`..\CRT Unified Launcher\integrations\launchbox\wrapper\launchbox_ppsspp_wrapper.bat`
- set Dolphin emulator `ApplicationPath` to:
`..\CRT Unified Launcher\integrations\launchbox\wrapper\launchbox_dolphin_wrapper.bat`
- set PCSX2 emulator `ApplicationPath` to:
`..\CRT Unified Launcher\integrations\launchbox\wrapper\launchbox_pcsx2_wrapper.bat`
- remove `-f` from RetroArch associated platform command lines
- remove `--fullscreen` from PPSSPP associated platform command lines
- remove `-C Dolphin.Display.Fullscreen=True` from Dolphin associated platform command lines
- remove `-fullscreen` from PCSX2 associated platform command lines

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
