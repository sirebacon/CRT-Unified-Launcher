# CRT Unified Launcher

Windows-based launcher and window-lock system for:

- RetroArch standalone
- LaunchBox/BigBox multi-emulator sessions
- Plex CRT workflows

## 1. Requirements

- Windows
- Python 3.10+
- Installed apps you plan to use:
  - LaunchBox/BigBox
  - RetroArch
  - Optional emulators (Dolphin, PPSSPP, PCSX2)
  - Plex (if using cinema mode)

Install Python dependencies:

```powershell
pip install pywin32 keyboard pygetwindow psutil
```

## 2. Configure Paths and Rects

Update `crt_config.json` to match your machine:

- Executable paths/dirs
  - `retroarch.path`, `retroarch.dir`
  - `dolphin.path`, `ppsspp.path`, `pcsx2.path` (if used)
  - `plex.path`, `plex.dir` (if used)
- Session defaults
  - `launcher_integration.x/y/w/h`
  - `launcher_integration.primary_on_exit`

If you use session mode (recommended), verify profiles in `profiles/`:

- `profiles/gaming-manifest.json`
- `profiles/launchbox-session.json`
- `profiles/retroarch-session.json`
- `profiles/dolphin-session.json`
- `profiles/ppsspp-session.json`
- `profiles/pcsx2-session.json`

## 3. Validate Before Live Run

Run dry-run validation from repo root:

```powershell
python validate_session.py --manifest profiles/gaming-manifest.json
```

This validates manifest/profile/patch paths and performs backup -> patch -> restore without leaving permanent changes.

## 4. Start the Launcher

```powershell
python crt_master.py
```

Recommended path:

- Choose `3` for LaunchBox Session mode.

Session behavior:

- 1x `Ctrl+C`: soft stop (move emulator windows to main screen, session stays active)
- 2x `Ctrl+C` within 8 seconds: full shutdown + restore configs

## 5. First Live Test Checklist

1. Start option 3 and confirm LaunchBox opens.
2. Launch one game per emulator you use.
3. Confirm each emulator window moves to CRT.
4. Soft stop with one `Ctrl+C`.
5. Full stop with second `Ctrl+C` within 8 seconds.
6. Confirm configs restore cleanly.

## Troubleshooting

- If restore fails, use:
  - `docs/runbooks/session-restore-recovery.md`
- If line/edge artifacts appear, use:
  - `docs/video-stack/line-artifact-suspicions.md`
  - per-core RetroArch overrides

## Documentation Index

- `docs/README.md` - full docs index
- `docs/current-state.md` - what is implemented and known gaps
- `docs/configuration.md` - config and profile details
- `docs/usage.md` - menu options and workflow
- `docs/architecture.md` - session lifecycle and components
- `docs/TODO.md` - active prioritized work list
