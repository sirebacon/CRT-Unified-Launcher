# CRT Unified Launcher

Windows-based launcher and window-lock system for RetroArch, LaunchBox/BigBox, and Plex CRT workflows.

## Quick Start

Install dependencies:

```powershell
pip install pywin32 keyboard pygetwindow psutil
```

Run the launcher:

```powershell
python crt_master.py
```

Pick **option 3** for a LaunchBox gaming session: patches emulator configs, opens LaunchBox on the main screen, and moves emulator windows to the CRT as you play. Ctrl+C to soft-stop (emulators back to main screen, session stays alive). Ctrl+C twice to end and restore everything.

## Documentation

- `docs/current-state.md` — what works, recommended workflow, known gaps
- `docs/usage.md` — all menu options explained
- `docs/configuration.md` — config files and session profiles
- `docs/architecture.md` — component overview and session lifecycle
- `docs/launchbox/overview.md` — LaunchBox integration model
- `docs/launchbox/generic-wrapper.md` — per-game wrapper profiles and CLI reference
- `docs/` — runbooks and other reference docs
