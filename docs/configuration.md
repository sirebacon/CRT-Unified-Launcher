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
