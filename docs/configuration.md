# Configuration

## crt_config.json

Global runtime config. Used by all launchers and wrappers for executable paths, CRT geometry, and polling cadence.

### Structure

```json
{
  "retroarch": { "path": "...", "dir": "..." },
  "plex":      { "path": "...", "dir": "..." },
  "dolphin":   { "path": "...", "dir": "..." },
  "ppsspp":    { "path": "...", "dir": "..." },
  "pcsx2":     { "path": "...", "dir": "..." },
  "launcher_integration": {
    "primary_on_exit": { "x": 100, "y": 100, "w": 1280, "h": 720 },
    "poll_seconds": 0.5
  }
}
```

- `primary_on_exit` — the restore rect used when sessions end. Windows are moved here on shutdown.
- `poll_seconds` — how often the session watcher checks and repositions windows.
- Negative `x` or `y` values are expected when the CRT is positioned left of or above the primary monitor in Windows display layout.

---

## profiles/ — Session Profiles

Session mode uses JSON profiles instead of hardcoded process lists.

### gaming-manifest.json

The top-level session config. Points to all other profiles and lists what to patch.

```json
{
  "schema_version": 1,
  "primary": { "profile": "profiles/launchbox-session.json" },
  "watch": [
    { "profile": "profiles/retroarch-session.json" },
    { "profile": "profiles/dolphin-session.json" },
    { "profile": "profiles/ppsspp-session.json" },
    { "profile": "profiles/pcsx2-session.json" }
  ],
  "patches": [ ... ]
}
```

### Session profile fields (e.g. retroarch-session.json)

```json
{
  "profile_version": 1,
  "path": "D:\\Emulators\\RetroArch-Win64\\retroarch.exe",
  "dir":  "D:\\Emulators\\RetroArch-Win64",
  "process_name":   ["retroarch.exe"],
  "class_contains": ["sdl_app", "retroarch"],
  "title_contains": [],
  "x": -1211, "y": 43, "w": 1057, "h": 835,
  "poll_slow": 0.4
}
```

- `process_name` — list of exe names to match (case-insensitive).
- `class_contains` — window class substrings (empty = skip class filter).
- `title_contains` — window title substrings (empty = skip title filter).
- `x`, `y`, `w`, `h` — target CRT rect for this emulator.
- `poll_slow` — seconds between window checks for this target.

The primary profile (launchbox-session.json) is loaded for exit detection only — LaunchBox/BigBox stays on the main screen and is not moved by the watcher.

### Patch types in gaming-manifest.json

**retroarch_cfg** — sets key/value pairs in `retroarch.cfg`:
```json
{
  "type": "retroarch_cfg",
  "path": "D:\\Emulators\\RetroArch-Win64\\retroarch.cfg",
  "set_values": { "video_fullscreen": "false", ... }
}
```

**launchbox_emulator** — patches `Emulators.xml` to use wrapper scripts and strip fullscreen args:
```json
{
  "type": "launchbox_emulator",
  "path": "D:\\Emulators\\LaunchBox\\Data\\Emulators.xml",
  "emulators": [
    {
      "title": "RetroArch",
      "wrapper_bat": "...",
      "strip_args": ["-f"],
      "xml_fields": { "UseStartupScreen": "false", ... }
    }
  ]
}
```

**launchbox_settings** — patches `BigBoxSettings.xml` and `Settings.xml` (monitor index, splash screens):
```json
{
  "type": "launchbox_settings",
  "bigbox_path": "D:\\Emulators\\LaunchBox\\Data\\BigBoxSettings.xml",
  "settings_path": "D:\\Emulators\\LaunchBox\\Data\\Settings.xml",
  "monitor_index": 0,
  "disable_splash_screens": true
}
```

All patched files are backed up before any changes are made. Configs are restored automatically when the session ends.

---

## integrations/launchbox/wrapper/profiles/ — Wrapper Profiles

Per-game profiles for the generic wrapper. Used when LaunchBox launches individual games.

See `docs/launchbox/generic-wrapper.md` for the full profile format and CLI reference.

---

## Updating Already Profiled Applications

When an emulator/game is already profiled and you need to retune behavior, update the right file for the right type of change.

### What to edit

- Change emulator/game executable path or working directory:
  - edit the target profile in `profiles/*.json` (session mode), or
  - edit `integrations/launchbox/wrapper/profiles/*.json` (wrapper mode)

- Change CRT position/size for one profiled app:
  - edit that app profile `x`, `y`, `w`, `h`

- Change matching reliability (wrong window, no window, multiple windows):
  - edit `process_name`, `class_contains`, `title_contains` in that app profile

- Change patch behavior for LaunchBox session mode:
  - edit `profiles/gaming-manifest.json` under `patches`

- Change global monitor/restore behavior:
  - edit `crt_config.json` (`launcher_integration.primary_on_exit`, polling defaults)

### Session mode change checklist (option 3)

1. Edit profile/manifest JSON.
2. Validate patch pipeline:
   - `python validate_session.py --manifest profiles/gaming-manifest.json`
3. If matching changed, run direct debug test:
   - `python launch_generic.py --profile-file profiles/<app>-session.json --debug`
4. Restart option 3 session to apply runtime changes.

Important:
- If LaunchBox is already running in reattach mode, settings in `BigBoxSettings.xml` and `Settings.xml` will not re-read until LaunchBox restarts.
- `Emulators.xml` and `retroarch.cfg` patches still apply during session start, but UI-level LaunchBox settings are loaded at LaunchBox startup.

### Wrapper profile change checklist

1. Edit wrapper profile:
   - `integrations/launchbox/wrapper/profiles/<slug>.json`
2. Validate:
   - `python integrations/launchbox/wrapper/launchbox_generic_wrapper.py --profile-file integrations/launchbox/wrapper/profiles/<slug>.json --validate-only`
3. Optional dry run:
   - `python integrations/launchbox/wrapper/launchbox_generic_wrapper.py --profile-file integrations/launchbox/wrapper/profiles/<slug>.json --dry-run`
4. Relaunch game from LaunchBox.

### Common tuning order

Use this order to minimize guesswork:
1. Confirm `path` and `dir`.
2. Confirm `process_name`.
3. Add `class_contains` only if needed.
4. Add `title_contains` only if needed.
5. Tune geometry (`x`, `y`, `w`, `h`).
6. Tune polling/timing last.

### Geometry reference (`x`, `y`, `w`, `h`)

- `x`: left edge position (horizontal)
- `y`: top edge position (vertical)
- `w`: window width
- `h`: window height

For layouts where CRT is left of the primary monitor, `x` is typically negative.

### RetroArch geometry — single source of truth

Edit only `profiles/retroarch-session.json`. Both the session watcher and the legacy wrapper (`launchbox_retroarch_wrapper.py`) read their rect from this file.

`crt_config.json["retroarch"]` still holds the executable path and config path, but no longer holds the rect.

Recommended workflow:
1. Adjust `x` first and test.
2. Adjust `w` second if you need extra coverage.
