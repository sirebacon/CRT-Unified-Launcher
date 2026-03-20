# VLC Live TV Automation Plan (Private M3U URL)

## Goal

Add a Live TV launch path that:

1. Opens VLC with your M3U live TV source.
2. Keeps private playlist URLs out of git.
3. Reuses current CRT launcher behavior (single command from menu, predictable window behavior).
4. Auto-moves/resizes VLC to CRT and supports returning the window to the main internal screen.

## Secret Handling (Required)

Do not commit private URLs in `crt_config.json`.

Use local override config only:

- `crt_config.json`: public defaults only (empty URL).
- `crt_config.local.json`: private values (gitignored).

`crt_config.local.json` is already gitignored in this repo.

## Config Shape

Add public defaults in `crt_config.json`:

```json
{
  "live_tv_enabled": true,
  "live_tv_vlc_path": "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe",
  "live_tv_playlist_url": "",
  "live_tv_network_caching_ms": 1500,
  "live_tv_fullscreen": true,
  "live_tv_rect": { "x": -1211, "y": 43, "w": 1057, "h": 835 },
  "live_tv_main_rect": { "x": 100, "y": 100, "w": 1280, "h": 720 },
  "live_tv_window_find_timeout_sec": 20.0,
  "live_tv_restore_main_on_exit": true
}
```

Put your real URL only in `crt_config.local.json`:

```json
{
  "live_tv_playlist_url": "REPLACE_WITH_PRIVATE_URL"
}
```

## Launch Flow

1. User picks `Live TV` from menu.
2. Launcher loads merged config (`crt_config.json` + `crt_config.local.json`).
3. Validate:
   - VLC path exists.
   - `live_tv_playlist_url` is present.
4. Build VLC command:
   - `vlc.exe "<playlist_url>" --fullscreen --network-caching=1500`
5. Start VLC process.
6. Find VLC window by launched PID and force move/resize to `live_tv_rect`.
7. Keep a lightweight loop active:
   - `R`: re-anchor to CRT rect.
   - `M`: move/resize to `live_tv_main_rect` (return to internal display).
   - `Q`: terminate VLC and return to CRT Station menu.
8. Return to menu when VLC exits.

## Window Control Requirements

- Do not rely on VLC remembering geometry.
- Always enforce rect with `session/window_utils.move_window(...)` after window discovery.
- Use PID-first window matching to avoid touching unrelated VLC windows.
- Keep controls modular so this path behaves like other app launchers.

## Privacy/Safety Rules

- Never print full playlist URL to terminal logs.
- Redact query params/tokens if URL must be logged.
- Do not store URL in runtime history files.
- Keep all private values in `crt_config.local.json` only.

## Implementation Files

- `crt_station.py`
  - Add menu item: `Launch Live TV (VLC)`.
  - Route selection to a new launcher module.
- `launch_live_tv.py` (new)
  - Read config, validate, spawn VLC, window-manage lifecycle (CRT/main/re-anchor/quit).
- `session/window_utils.py` (reuse)
  - `find_window(...)`, `move_window(...)`, `get_rect(...)` for placement control.
- `crt_config.json`
  - Add non-secret defaults.
- `crt_config.local.json.example`
  - Add `live_tv_playlist_url` key with empty string.
- `docs/runbooks/media-setup.md`
  - Add short usage section pointing to this runbook.

## Test Checklist

1. `crt_config.local.json` contains private URL, not committed.
2. Launch from menu opens VLC directly to live stream playlist.
3. VLC window is auto-positioned on CRT at launch.
4. `M` returns VLC to main/internal screen rect.
5. `R` re-anchors VLC back to CRT rect.
6. URL is not printed in logs.
7. `git status` shows no secret file changes to commit.
8. Failure path is clear when URL/path is missing.

## Optional Next Step

If provider requires headers/auth beyond URL tokens, add:

- `live_tv_http_referrer`
- `live_tv_http_user_agent`

and pass them to VLC as command flags, still from local config only.
