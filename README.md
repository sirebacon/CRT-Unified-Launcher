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

## CRT Baseline Resolution

Default accuracy baseline for CRT play:

- Host/game output: `1280x960 @ 60` (4:3)
- Moonlight/client output: `1280x960 @ 60` (4:3) when available
- Goal: preserve original 4:3 geometry without stretch

Known behavior:

- `1280x800` (16:10) can hide a left-edge bar/cutoff in some states, but it is not aspect-accurate for 4:3 content.
- Prefer geometry/timing adjustments (OSSC/CRT position and scaling mode) over switching to `1280x800` for long-term setup.

## Troubleshooting

- If restore fails, use:
  - `docs/runbooks/session-restore-recovery.md`
- If line/edge artifacts appear, use:
  - `docs/video-stack/line-artifact-suspicions.md`
  - per-core RetroArch overrides

## Resident Evil Stack Automation

You can automate GOG RE launches (RE1/RE2/RE3) with the existing wrapper profiles:

```powershell
python launch_resident_evil_stack.py start --game re1
python launch_resident_evil_stack.py start --game re2
python launch_resident_evil_stack.py start --game re3
python launch_resident_evil_stack.py inspect
```

Restore/reverse helper:

```powershell
python launch_resident_evil_stack.py restore
```

Auto-restore behavior:
- `start --game reX` now auto-runs restore when the game process exits, crashes, or you press `Ctrl+C`.
- Manual `restore` remains available as a recovery command.

RE start preflight requirements:
- Moonlight must be running from `D:\Emulators\MoonlightPortable-x64-6.1.0` (script auto-starts it if needed).
- Required display set must be present or launch is aborted:
  - internal display (`Internal Display` or `Intel(R) UHD Graphics`)
  - CRT display (`CP-1262HE` or `NVIDIA GeForce RTX 4090 Laptop GPU`)
  - virtual display (`SudoMaker Virtual Display`)
- Moonlight window is moved to CRT usable rect from `crt_config.json` (`launcher_integration.x/y/w/h`) before RE launch.

Resident Evil mode system state behavior:
- On `start`: attempts to set primary display to token `SudoMaker Virtual Display`
- On `start`: attempts to set default playback audio to token `CP-1262HE (NVIDIA High Definition Audio)`
- On `restore`: attempts to set primary display back to token `Internal Display`
- On `restore`: attempts to set default playback audio back to token `Speakers (Realtek(R) Audio)`

This restore command:
- stops active generic-wrapper enforcement for RE stack launches
- runs default config restore from latest backup files (same behavior as Tools restore)

Audio switching note:
- Automatic audio switching uses `AudioDeviceCmdlets` (preferred) or `nircmd.exe` if available.
- If neither is installed, the script logs a warning and continues.

You can also run these via `python crt_master.py`:
- Option `5` launches Resident Evil stack
- Option `7` runs Resident Evil stack recovery restore

## Documentation Index

- `docs/README.md` - full docs index
- `docs/current-state.md` - what is implemented and known gaps
- `docs/configuration.md` - config and profile details
- `docs/usage.md` - menu options and workflow
- `docs/architecture.md` - session lifecycle and components
- `docs/TODO.md` - active prioritized work list
