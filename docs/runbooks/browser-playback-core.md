# Browser Playback - Core Contract (Multi-Site)

## Status

Design only. Not implemented yet in launcher/provider code.

## Goal

Define shared, modular contracts used by browser playback modes across multiple sites.
This core is inherited by Mode A (system browser) and Mode B (Playwright).

## Why Browser Mode Exists

Some sites rely on browser-only media delivery behavior (token binding, protected CDNs,
media-element fetch paths). Direct mpv/Python stream fetch may be unreliable or blocked.

## Shared Provider Contract

A browser-only provider `resolve_target()` returns a browser-launch directive:

```python
{
  "target_url": str,
  "is_playlist": False,
  "subtitle_urls": [],
  "extra_headers": {},
  "requires_mpv": False,
  "launch_mode": "browser" | "playwright",
  "browser_profile": str            # profile id
}
```

Required behavior:

- `requires_mpv=False` means launcher must skip mpv path.
- `launch_mode` selects the adapter implementation.
- `browser_profile` selects site-specific behavior profile.
- provider remains responsible only for URL matching/validation + directive payload.

## Shared Launcher Dispatch

Launcher dispatch must be mode-agnostic:

1. Get provider directive from `resolve_target()`.
2. If `requires_mpv=False`, route to browser launcher adapter.
3. Select adapter by `launch_mode`.
4. Return launch status to main session loop.

Decision:
- Mode A must support window re-anchor behavior consistent with emulator workflows
  (bring browser back to internal/main monitor rect via hotkey).
- Mode B should integrate with NOW PLAYING for browser-emulated playback controls.

## Shared Config Hierarchy

Global browser section:

```json
{
  "browser_playback": {
    "default_mode": "browser",
    "browser_path": "",
    "playwright_timeout_sec": 30,
    "playwright_headless": false,
    "playwright_force_fullscreen": true,
    "profiles": {
      "<site>": {
        "title_match": ["SiteName", "PlayerHost"],
        "mode_override": "browser",
        "reanchor_hotkey": "ctrl+alt+m",
        "playwright_wait_until": "domcontentloaded",
        "playwright_fullscreen_js": true,
        "keymap": {
          "toggle_pause": "Space",
          "seek_back": "ArrowLeft",
          "seek_forward": "ArrowRight",
          "fullscreen": "f",
          "mute": "m"
        }
      }
    }
  }
}
```

Rules:

- `default_mode` chooses global fallback behavior.
- each provider selects a `browser_profile`.
- profile can override mode and mode-specific behavior safely.
- local overrides in `crt_config.local.json` take precedence.
- mode-specific keys are ignored safely by other modes.

Mode selection precedence (highest to lowest):

1. `browser_playback.profiles.<site>.mode_override`
2. provider directive `launch_mode`
3. `browser_playback.default_mode`

## Profile Model

Profiles are the modular extension point for multi-site support.

Each profile defines:

- window matching hints (title/process patterns)
- re-anchor preferences (Mode A)
- Playwright wait/fullscreen strategy (Mode B)
- NOW PLAYING key bridge mappings

Hotkey safety rule:

- avoid terminal-interrupt shortcuts (for example `ctrl+c`) for re-anchor actions.
- use non-destructive combinations (for example `ctrl+alt+m`) as defaults.

Adding a new site should require:

1. new provider file with URL matching
2. one profile entry in config
3. registry registration

No new mode-specific launcher code should be required.

## Shared Error and Logging Rules

- Log provider decision: selected mode and URL host.
- Log launch result: success/failure and fallback used.
- User-facing errors should be actionable (missing browser, missing Playwright, blocked page).
- No silent fallback without logging.

## Shared Modularity Rules

- `media/providers/<site>.py` must not import Playwright directly.
- `media/browser_launcher.py` owns all mode implementations.
- mode functions are independent and callable via common interface:
  - `launch_system_browser(url, cfg) -> int`
  - `launch_playwright_browser(url, cfg) -> int`
- profile resolution is centralized; modes consume normalized profile input only.

Window/control integration modules should also stay separated:

- window management: existing `session/window_utils` helpers
- browser control bridge: dedicated browser adapter layer (no provider-specific IPC code)

## Shared Test Gates

1. Non-browser-only providers are unaffected.
2. Browser-backed provider routes to browser path, not mpv.
3. Launch mode switch via config works without code changes.
4. Fallback behavior is deterministic and logged.
5. Profile-driven behavior switches sites without code changes.

## Additional Ideas (Backlog)

1. Mode C: attach to existing browser tab/session instead of opening a new window.
2. Optional re-anchor watchdog for Mode A (periodic internal-monitor correction).
3. Per-site browser key profiles for NOW PLAYING control bridge (Mode B).
4. Configurable fallback policy chain (`playwright -> browser` or `browser only`).
5. Persist browser window rect/profile across launches.
6. NOW PLAYING capability banner for browser mode limitations.
7. Browser mode telemetry (launch latency, fallback reason, fullscreen success).
