# CRT Unified Launcher

Windows-based launcher and window-lock system for RetroArch, Plex, and LaunchBox/BigBox CRT workflows.

## Documentation

The project documentation is now modularized under `docs/`.

Start here:

- `docs/README.md`
- `docs/current-state.md`
- `docs/setup-and-requirements.md`
- `docs/configuration.md`
- `docs/usage.md`
- `docs/architecture.md`
- `docs/launchbox/overview.md`
- `docs/launchbox/generic-wrapper.md`

Planning and runbooks:

- `docs/roadmaps/generic-wrapper-scaling-todo.md`
- `docs/runbooks/ai-git-access.md`

## Quick Start

Install dependencies:

```powershell
pip install pywin32 keyboard pygetwindow psutil
```

Run launcher:

```powershell
python crt_master.py
```
