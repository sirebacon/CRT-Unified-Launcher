# Usage

## Unified Launcher

Run:

```powershell
python crt_master.py
```

Menu:

1. RetroArch launch/lock
2. LaunchBox session mode (temporary profile + watcher)
3. Plex launch/lock
4. Exit

## Direct Commands

```powershell
python launch_ra.py
python launch_plex.py
python launchbox_crt_watcher.py
```

## LaunchBox / BigBox Baseline

1. Keep LaunchBox/BigBox on primary display.
2. Start watcher:

```powershell
python launchbox_crt_watcher.py
```

3. Launch games normally from LaunchBox/BigBox.
4. Matching game windows are moved to CRT target bounds.

More details: `docs/launchbox/overview.md`

## Wrapper Installer Helper

Validate wrapper availability:

```powershell
python scripts\install_launchbox_wrapper.py
```

Apply global LaunchBox emulator patching:

```powershell
python scripts\install_launchbox_wrapper.py --global
```

## Calibration Utilities

Live Plex calibration:

```powershell
python tools\plex_callibrate.py
```

Inspector:

```powershell
python tools\inspectRetro.py
```
