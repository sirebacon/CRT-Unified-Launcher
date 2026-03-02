# CRT Unified Launcher

Windows-based launcher and window-lock system for:

- RetroArch standalone
- LaunchBox/BigBox multi-emulator sessions
- Plex CRT workflows
- YouTube on CRT via mpv + yt-dlp

## 1. Requirements

- Windows
- Python 3.10+
- Installed apps you plan to use:
  - LaunchBox/BigBox
  - RetroArch
  - Optional emulators (Dolphin, PPSSPP, PCSX2)
  - Plex (if using cinema mode)
  - mpv + yt-dlp (if using YouTube mode)

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
  - `mpv_path`, `yt_dlp_path` (if using YouTube mode)
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
- `profiles/mpv-session.json` (YouTube on CRT window rect)

## 3. Validate Before Live Run

Run dry-run validation from repo root:

```powershell
python validate_session.py --manifest profiles/gaming-manifest.json
```

This validates manifest/profile/patch paths and performs backup -> patch -> restore without leaving permanent changes.

## 4. Start the Launcher

```powershell
python crt_station.py
```

Recommended paths:

- Choose `3` for LaunchBox Session mode.
- Choose `4` for YouTube on CRT mode.

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

## Resident Evil Stack (Manual Mode - Supported)

Resident Evil mode is currently run in guided manual mode (recommended/supported).
Automatic RE mode (`start`) is still in the codebase but is on hold because it has been too finicky/inconsistent.

Use:

```powershell
python launch_resident_evil_stack.py manual --game re1
python launch_resident_evil_stack.py manual --game re2
python launch_resident_evil_stack.py manual --game re3
python launch_resident_evil_stack.py inspect
```

Restore/reverse helper:

```powershell
python launch_resident_evil_stack.py restore
```

Manual-mode behavior:
- `manual --game reX` guides display setup, moves Moonlight to CRT after your setup confirmation, switches audio to CRT, and returns Moonlight/audio on game exit or `Ctrl+C`.
- Manual `restore` remains available as a recovery command (mainly for interrupted older/automatic sessions).

RE manual-mode preflight requirements:
- Moonlight must be running from `D:\Emulators\MoonlightPortable-x64-6.1.0` (script auto-starts it if needed).
- Required display set must be present or launch is aborted:
  - internal display (`Internal Display` or `Intel(R) UHD Graphics`)
  - CRT display (`CP-1262HE` or `NVIDIA GeForce RTX 4090 Laptop GPU`)
  - virtual display (`SudoMaker Virtual Display`)
- Moonlight window is moved to the configured RE CRT rect after manual display setup is completed.

Resident Evil manual-mode behavior:
- You set the primary display manually during setup.
- On manual mode CRT move: script attempts to set default playback audio to token `CP-1262HE (NVIDIA High Definition Audio)`.
- On game exit / `Ctrl+C`: script moves Moonlight back to its captured pre-move rect and restores default playback audio to token `Speakers (Realtek(R) Audio)`.
- You set the primary display back manually after the session.

This restore command:
- stops active generic-wrapper enforcement for RE stack launches
- runs default config restore from latest backup files (same behavior as Tools restore)

Audio switching note:
- Automatic audio switching uses `AudioDeviceCmdlets` (preferred) or `nircmd.exe` if available.
- If neither is installed, the script logs a warning and continues.

You can also run these via `python crt_station.py`:
- Option `5` launches Resident Evil (Manual Mode)
- Option `6` opens CRT Tools
- Option `8` runs RE stack recovery restore

## YouTube on CRT

YouTube mode launches `mpv` with `yt-dlp`, moves the player window to the CRT
rect from `profiles/mpv-session.json`, and provides keyboard playback controls
from the terminal.

Use:

```powershell
python launch_youtube.py --url "https://www.youtube.com/watch?v=..."
```

Or from menu:
- `python crt_station.py` -> option `4` `[CINEMA] Launch YouTube`

Required setup:
- `crt_config.json` must include valid `mpv_path` and `yt_dlp_path`
- `profiles/mpv-session.json` must have the correct CRT `x/y/w/h`
- `runtime/youtube.log` is written for troubleshooting

Controls while playing:
- `[Space]` pause/resume
- `[Left/Right]` seek -10s/+10s
- `[Up/Down]` volume +5/-5
- `[M]` mute
- `[Z]` cycle zoom presets (`Off` -> `default` -> ...)
- `[A]` adjust window mode (move/resize/save/snap/fill)
- In adjust mode, use `[P]` to save current zoom/pan as a named preset
- `[Q]` quit

## Documentation Index

- `docs/README.md` - full docs index
- `docs/current-state.md` - what is implemented and known gaps
- `docs/configuration.md` - config and profile details
- `docs/usage.md` - menu options and workflow
- `docs/architecture.md` - session lifecycle and components
- `docs/TODO.md` - active prioritized work list
