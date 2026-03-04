# Mode B - Playwright Fullscreen (Multi-Site)

## Inherits

This mode inherits all shared contracts from:

- `docs/runbooks/browser-playback-core.md`

## Purpose

Provide a more integrated browser playback path using Playwright-controlled Chromium,
including scripted fullscreen behavior and deterministic startup flow.
Applies to any site with a browser profile mapped to Mode B.

Design intent:
- keep playback visible/managed through NOW PLAYING session UX
- map NOW PLAYING controls to browser key events where practical
- do not assume Cloudflare is the primary failure mode when Playwright reaches page content

## Implementation

Adapter function:

- `launch_playwright_browser(url, cfg) -> int`

Behavior:

1. Validate Playwright availability.
2. Launch Chromium (non-headless by default).
3. Navigate to episode URL.
4. Wait for DOM readiness (`domcontentloaded` default); avoid strict `networkidle` as
   ad/polling traffic may prevent settle.
5. Attempt fullscreen in the player iframe context (not outer page root), then optional
   key fallback.
6. Keep session alive until browser/page exits.
7. Bridge selected NOW PLAYING controls to page keyboard events (play/pause, seek,
   fullscreen, mute) using Playwright keyboard APIs targeted at active player frame.

## Mode B Config Keys

- `browser_playback.default_mode = "playwright"` (optional global default)
- `browser_playback.playwright_timeout_sec`
- `browser_playback.playwright_headless` (default `false`)
- `browser_playback.playwright_force_fullscreen` (default `true`)
- `browser_playback.profiles.<site>.mode_override = "playwright"` (optional)
- `browser_playback.profiles.<site>.playwright_wait_until`
- `browser_playback.profiles.<site>.playwright_fullscreen_js`
- `browser_playback.profiles.<site>.keymap`

## Failure/Fallback Behavior

- If Playwright package/browser runtime missing:
  - log warning
  - fallback to Mode A launcher
- If frame/player interaction fails (for example iframe focus/fullscreen targeting):
  - fallback to Mode A launcher
- If fullscreen call fails:
  - continue playback without fullscreen, log warning

## Pros

- Better launch control and potential UX integration
- Scriptable startup and fullscreen behavior

## Cons

- Higher maintenance and dependency overhead
- More brittle to site/browser behavior changes
- Slower startup vs Mode A

## Architecture Note

NOW PLAYING key bridge requires launcher-session loop integration:

1. session key loop must stay active while Playwright browser is open
2. key events must be routed to Playwright page/frame context
3. browser lifecycle and launcher loop must coordinate shutdown signaling

## Acceptance Criteria

1. Playwright mode launches Chromium and navigates successfully.
2. Fullscreen is attempted and logged.
3. Missing Playwright gracefully falls back to Mode A.
4. Non-browser-only providers are unaffected.
5. NOW PLAYING control bridge sends expected browser key events.
6. Per-site key/wait/fullscreen behavior is profile-driven.

