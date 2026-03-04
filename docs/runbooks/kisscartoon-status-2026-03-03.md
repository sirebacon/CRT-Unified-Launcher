# KissCartoon Browser Playback — Status & Issues (2026-03-03)

## What We Built

### Tier 3 Provider Pattern
KissCartoon's CDN (`storage.googleapis.com`) returns HTTP 403 to all Python HTTP clients. Only
Chrome's internal media element can access it. We introduced a new "Tier 3" provider concept:

- `requires_mpv: False` — skip mpv entirely
- `launch_mode: "browser"` — hand the URL to a browser launcher
- `browser_profile: "kisscartoon"` — load profile-specific config

Files created:
- `media/providers/kisscartoon.py` — URL matching, title parsing from slug, returns Tier 3 directive
- `media/browser_launcher.py` — Mode A (system browser) and Mode B (Playwright) launchers
- `media/providers/registry.py` — KissCartoonProvider registered before GenericProvider fallback

`youtube/launcher.py` — Tier 3 early-return branch (before mpv/yt-dlp checks):
```python
if not resolved.get("requires_mpv", True):
    # mode precedence: profile.mode_override > provider launch_mode > default_mode
    ...launch_system_browser() or launch_playwright_browser()
```

### Mode A — System Browser (WORKING)
- Launches Chrome with `--user-data-dir=runtime/browser_isolated` (isolated OS process)
- Loads local unpacked extensions via `--load-extension=<path>`
- Blocks on `proc.wait()` (fresh Chrome instance); falls back to `input()` if Chrome
  reused an existing instance (fast-exit detection)
- Profile config in `crt_config.json → browser_playback.profiles.kisscartoon`

### Mode B — Playwright (ABANDONED for KissCartoon)
- Built and partially working (page navigation, extension loading)
- **Fatal issue**: the WCO embed player (`embed.wcostream.com`) detects the CDP WebSocket
  connection and aborts `script.php` requests via `AbortController` → ERR_BLOCKED_BY_CLIENT
- Stealth script (`navigator.webdriver` patch, `window.chrome` restore, etc.) does NOT help
  because the detection is network-level (the server/JS checks for the CDP connection itself)
- Mode B falls back to Mode A automatically
- Status: stub only, not usable for KissCartoon

### CRT Fullscreen Fix Extension
Located at `media/browser_ext/crt_fullscreen/`. Loaded via `--load-extension` in Mode A.
Must be manually installed via "Load unpacked" in `chrome://extensions` (Developer Mode required).

**Current version: 1.7**

Files:
- `manifest.json` — MV3, `declarativeNetRequest` permission, CSS content script
- `style.css` — fullscreen video CSS fix (`object-fit: contain`)
- `rules.json` — 32 DNR ad-blocking rules
- `fullscreen_override.js` — EXISTS ON DISK but NOT loaded (see issues below)

---

## What Is Working

| Feature | Status |
|---|---|
| `python youtube/launcher.py <kisscartoon-url>` | Works — opens Chrome, plays video |
| Isolated Chrome profile | Works — separate from personal Chrome |
| Tier 3 routing (no mpv, no yt-dlp) | Works |
| CSS fullscreen fix (no cropping) | Works — `.jw-flag-fullscreen` and `:fullscreen` targeted |
| Extension auto-loading via `--load-extension` | Works after Developer Mode enabled manually once |
| Mode A blocking on browser close | Works |

---

## What Is Broken / Open Issues

### 1. Ads Still Showing
**Status**: Partially fixed — 32 DNR rules added, but KissCartoon uses ad networks
we may not have covered yet.

**What we have**: Google AdSense, DoubleClick, IMA SDK, videojs.ads, GTM, GA, Amazon,
ExoClick, AdSterra, HillTopAds, JuicyAds, TrafficJunky, Clickadu, PopAds, PopCash,
PropellerAds, MGID, and others.

**What to do next**: Open the KissCartoon page in regular Chrome (not isolated profile)
with DevTools → Network tab, identify which ad domains load, add them to `rules.json`.
Then reload extension in `chrome://extensions`.

**Note**: DNR blocks network requests at the browser level — no JS injection, no player
interference. Safer than uBlock for this use case.

### 2. Fullscreen Ctrl+Alt+A Adjust Mode Not Working
**Status**: Intentionally disabled (JS removed from manifest).

**Background**: `fullscreen_override.js` was written to intercept `requestFullscreen()`
and fake fullscreen inside the browser window (useful for CRT rect adjustment). It was
removed because:
- The video player is inside a cross-origin embed iframe
- `position: fixed` inside an iframe only fills *the iframe viewport*, not the browser window
- The fake fullscreen approach therefore has no visible effect

**What currently works**: Native OS fullscreen (JWPlayer's fullscreen button) + CSS fix
prevents cropping. No rect adjustment.

**To fix**: The fullscreen_override.js approach needs to target the IFRAME element in the
parent page, not the player element inside the iframe. This requires a different architecture:
- Detect fullscreen entry from the parent frame (listen for postMessage or fullscreenchange)
- Apply CSS to the iframe element itself to make it fill the window
- This is significantly more complex than the current approach

### 3. Anti-Debug Trap (F12 Blocked)
**Status**: Known site behavior, not fixable without extension work.

**What happens**: KissCartoon/WCO runs `setInterval(() => { debugger }, 50)` (or similar).
Every time DevTools opens, it immediately pauses execution.

**Workaround**:
- Press **Ctrl+F8** immediately after opening DevTools (deactivates all breakpoints)
- Or: Sources tab → right-click the paused line → "Never pause here"

**To fix in extension**: Add a content script that intercepts `setInterval`/`setTimeout`
and strips calls containing only a `debugger` statement. Not yet implemented — risk of
breaking player.

### 4. Extension Requires Manual "Load Unpacked" (First Time)
**Status**: Known Chrome limitation.

`--load-extension` requires Developer Mode to be enabled in the isolated profile.
Once enabled manually (one-time setup), it persists in the profile.

**Steps (one-time)**:
1. Launch Chrome with the isolated profile via Mode A
2. Go to `chrome://extensions`
3. Enable "Developer mode" toggle (top-right)
4. Click "Load unpacked" → select `media/browser_ext/crt_fullscreen`
5. Done — persists across sessions

After any extension update: click the reload (↺) button in `chrome://extensions`.

### 5. Mode B CDP Detection (Fundamental Limitation)
**Status**: Unresolved — Mode B abandoned for KissCartoon.

The WCO embed player uses an `AbortController` pattern to cancel video requests when CDP
is detected. This happens regardless of `navigator.webdriver` patching or stealth scripts.
The only known working path is Mode A (uncontrolled system browser).

---

## Config Reference

`crt_config.json → browser_playback.profiles.kisscartoon`:
```json
{
  "title_match": ["KissCartoon"],
  "mode_override": "browser",
  "browser_args": [],
  "local_extensions": ["media/browser_ext/crt_fullscreen"],
  "window_presets": [
    {"label": "Adjusted (inset 20px)", "x": -1260, "y": 20, "w": 1240, "h": 920}
  ]
}
```

Key top-level settings:
- `browser_path` — path to Chrome executable
- `isolated_profile_dir` — `runtime/browser_isolated` (relative to project root)
- `isolated_profile_mode` — `"persistent"` (profile survives between sessions)

---

## Extension File Layout

```
media/browser_ext/crt_fullscreen/
  manifest.json           — MV3, v1.7, DNR + CSS content script
  style.css               — object-fit: contain for fullscreen video
  rules.json              — 32 DNR ad-blocking rules (network-level)
  fullscreen_override.js  — DISABLED — fake fullscreen + Ctrl+Alt+A (see issue #2)
```

---

## Next Steps (Priority Order)

1. **Ads**: Identify remaining ad domains via DevTools in regular Chrome, add to `rules.json`
2. **Anti-debug**: Add `setInterval` interceptor to extension content script (optional)
3. **Fullscreen adjust**: Redesign to target the iframe element from the parent frame
4. **Mode B**: Investigate if there is a non-CDP Playwright mode (e.g. no remote debugging port)
   that avoids the embed player detection — likely not possible with standard Playwright
