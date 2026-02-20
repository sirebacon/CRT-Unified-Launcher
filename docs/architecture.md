# Architecture

## Entry Point

`crt_master.py` — interactive menu that dispatches to one of six modes.

## Gaming Session (Option 3)

The primary gaming workflow. All components live under `session/`.

```
launch_session.py
  └── session/manifest.py       load + validate gaming-manifest.json
  └── session/patcher.py        backup → patch → restore on exit
        └── session/patches/retroarch.py    retroarch.cfg key/value patching
        └── session/patches/launchbox.py    Emulators.xml, BigBoxSettings.xml, Settings.xml patching
  └── session/backup.py         numbered backup files, per-file restore failure logging
  └── session/watcher.py        multi-target poll loop
        └── session/window_utils.py   shared Win32 helpers
```

### Session Lifecycle

1. Load `crt_config.json` and `gaming-manifest.json`.
2. Check if primary (LaunchBox/BigBox) is already running:
   - **Fresh start**: apply patches, launch LaunchBox, run watcher.
   - **Reattach**: apply patches, skip launch (`proc=None`), run watcher.
3. Watcher poll loop (every ~0.5 s):
   - Check if LaunchBox/BigBox is still alive — exit if not.
   - Handle Ctrl+C (see below).
   - For each emulator watch target: find its window and snap it to its CRT rect.
4. On exit: restore all patched configs, remove lockfile.

### Ctrl+C Behaviour

- **Single Ctrl+C**: soft stop — moves all active emulator windows to the main screen and pauses tracking. Session stays alive; BigBox remains open for the next game launch.
- **Second Ctrl+C within 5 seconds**: full shutdown — ends watcher, restores all configs.
- A paused emulator auto-resumes tracking when its process exits (game closed).

### Data Files

- `profiles/gaming-manifest.json` — lists primary profile, watch profiles, and patches to apply
- `profiles/launchbox-session.json` — primary process names and CRT rect (not tracked by watcher, stays on main screen)
- `profiles/retroarch-session.json`, `dolphin-session.json`, `ppsspp-session.json`, `pcsx2-session.json` — emulator window tracking targets

### Single-Session Guard

A lockfile at `.session.lock` (project root) prevents concurrent sessions. Always removed in `finally`. Contains the session PID for diagnostics.

### Validation

`validate_session.py --manifest profiles/gaming-manifest.json` — dry run: backs up, patches, and immediately restores. No permanent changes.

---

## LaunchBox Generic Wrapper

`integrations/launchbox/wrapper/launchbox_generic_wrapper.py`

Runs as a LaunchBox emulator `ApplicationPath` target. Launches the emulator, finds its window during startup, and snaps it to the CRT rect for a configurable lock period.

Runtime flow:
1. Parse arguments (profile mode or config-key mode).
2. Load `crt_config.json` and optional profile file.
3. Build launch command (emulator exe + args + ROM path from LaunchBox passthrough).
4. Launch process.
5. During lock window: find window, move to rect when it drifts.
6. Exit with emulator exit code.

Stop conditions: lock timeout expires, `wrapper_stop_enforce.flag` written by session watcher, or window lands on primary-monitor restore rect.

See `docs/launchbox/generic-wrapper.md` for full CLI reference.

---

## LaunchBox Legacy Watcher (Option 2)

`launchbox_crt_watcher.py` — older single-script watcher. Still functional but not the recommended path. Uses hardcoded process logic rather than profiles.

---

## Plex (Option 4)

`launch_plex.py` — launches Plex Desktop, locks its window to the CRT rect, restores on Ctrl+C or exit.

---

## Shared Utilities

- `session/window_utils.py` — all Win32 window operations used across the codebase
- `crt_config.json` — global coordinates, executable paths, polling cadence, restore rect
- `wrapper_stop_enforce.flag` — written by session watcher on soft stop or shutdown to signal wrapper scripts to disengage
