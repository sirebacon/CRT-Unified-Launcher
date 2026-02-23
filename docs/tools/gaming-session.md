# Gaming Session Tools

Module: existing scripts | No `crt_tools.py` subcommand (these are standalone scripts)

These tools support the LaunchBox gaming session workflow (option 3 from `crt_station.py`). They
are not part of the `crt_tools.py` framework -- they are independent scripts used for session
validation and single-profile debugging.

---

## validate_session.py

```
python validate_session.py --manifest profiles/gaming-manifest.json
python validate_session.py --manifest profiles/gaming-manifest.json --keep-backup
```

Dry-run validation for a session manifest. Does everything a live session does at startup, then
immediately undoes it -- no permanent changes.

**What it does:**

1. Loads and validates `gaming-manifest.json` (schema + file-existence checks)
2. Backs up all config files that would be patched (`retroarch.cfg`, `Emulators.xml`, etc.)
3. Applies all patches from the manifest
4. Immediately restores all files from backup

After the script exits, every patched file is byte-identical to its state before the script ran.

**When to use:**

- After editing `gaming-manifest.json` or any patch profile
- After adding a new emulator profile
- On a new machine, to confirm all referenced files exist and are writable
- Before the first live session

**`--keep-backup`:** keeps the backup directory so you can inspect the patched versions of
the files without running a live session. Useful for debugging patch logic.

**Sample output:**

```
[validate] Loading manifest: profiles/gaming-manifest.json
[validate] Manifest OK -- 4 patch(es), 3 watch profile(s).
[validate] Backing up patch targets and applying patches...
[validate] Patches applied. Backup at: backups/2026-02-22_141032
[validate] Restoring all files to original state...
[validate] PASS -- all files restored to original state.
```

**Fail output:**

```
[validate] FAILED during patch apply: retroarch.cfg: key 'video_fullscreen_x' not found
```

---

## launch_generic.py

```
python launch_generic.py --profile-file profiles/retroarch-session.json
python launch_generic.py --profile-file profiles/retroarch-session.json --debug
```

Single-profile launcher and window locker. Loads a profile, launches the application (or
attaches to an already-running instance), finds the window, and locks it to the configured
CRT rect indefinitely. `Ctrl+C` moves the window to the primary monitor and exits.

This is the stripped-down single-session equivalent of the full gaming session watcher. Use it
to:

- Debug a new profile without running the full session
- Test rect calibration for a single emulator
- Run a standalone session for an emulator not in `gaming-manifest.json`

**`--debug`:** prints detailed window-find and move output on every poll iteration.

**Sample output:**

```
[generic] Profile: profiles/retroarch-session.json
[generic] Process: retroarch.exe  (not running -- will launch)
[generic] Launching: D:\Emulators\RetroArch-Win64\retroarch.exe
[generic] Window found: 'RetroArch'  x=-1211  y=43  w=1057  h=835
[generic] Locked to CRT rect: x=-1920  y=0  w=1920  h=1080
```

**Profile format:** same session profile JSON used by `gaming-manifest.json` watch targets
(`profiles/retroarch-session.json`, `dolphin-session.json`, etc.)

---

## tools/inspectRetro.py

```
python tools\inspectRetro.py
```

Legacy window inspector, hardcoded to look for the Dolphin emulator window. Enumerates windows
and prints class name, title, PID, rect, and style flags for the Dolphin window.

**Status:** Exists. Not planned for removal. Use `crt_tools.py window list` (once implemented)
for generalized window inspection of any process.

**Use for:** quick Dolphin-specific window details when `window list` is not yet available.

---

## tools/plex_callibrate.py

```
python tools\plex_callibrate.py
```

Interactive live calibration tool for the Plex window. Moves the Plex window in real time
and saves the resulting rect to `crt_config.json`.

**Status:** Exists. Covers Plex-specific calibration only. For Moonlight calibration use
`crt_tools.py calibrate adjust`.

---

## Related: Gaming Session Profiles

Session watch profiles live in `profiles/`:

| File | Used for |
|------|---------|
| `gaming-manifest.json` | Master manifest -- lists primary profile, watch targets, patches |
| `launchbox-session.json` | LaunchBox/BigBox process + CRT rect |
| `retroarch-session.json` | RetroArch window tracking |
| `dolphin-session.json` | Dolphin window tracking |
| `ppsspp-session.json` | PPSSPP window tracking |
| `pcsx2-session.json` | PCSX2 window tracking |

See `docs/configuration.md` for profile field reference and how to add a new emulator.

