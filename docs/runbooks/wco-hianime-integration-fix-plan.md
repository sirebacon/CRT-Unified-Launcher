# WCO & HiAnime Integration - Current Status and Remaining Work

## Update (2026-03-02 Evening) - WCO Still Failing → Fix Applied

Latest clean-run logs showed WCO failing at playback time even after sending
full embed referer + origin + cookie headers to mpv.

### Key error

From `runtime/mpv.log` and `runtime/youtube.log`:

- target URL: `https://lb.wcostream.com/getvid?evid=...`
- mpv failure: `https: HTTP error 404 Not Found`, process exit code `2`
- headers included: `Referer: embed.wcostream.com/...`, `Origin: embed.wcostream.com`, `Cookie: PHPSESSID=...`

### Root cause

The `getvid?evid=` token is bound to the resolver's session/IP context.
mpv as a separate HTTP client cannot replay it even with identical headers.

### Fix applied (2026-03-02)

`wco_http._follow_getvid_redirect` was added to `wco_http.py`.
`resolve_episode_http` now calls it after getting the quality token:

1. Call `getvid?evid=<token>` with `allow_redirects=False` from within the active
   curl_cffi session (which has PHPSESSID context).
2. The server returns a 302 redirect; read the `Location` header — this is the final
   CDN stream URL (e.g. `https://t01.wcostream.com/…mp4?…`).
3. Return the CDN URL as `target_url` to mpv with minimal headers (no session
   context required — the CDN URL is session-independent).
4. If the redirect follow fails for any reason, fall back to the raw `getvid` URL
   with the original session headers (same as before). A warning is logged.

**Status: fix applied, confirmed working (see CDN notes below).**

### CDN path findings (2026-03-02)

WCO uses two different CDN clusters depending on the show:

| embed_server | server | CDN path | Status |
|---|---|---|---|
| `neptun` | `neptun.wcostream.com` | `neptun → t0X/c0X.wcostream.com/getvid?evid=<same_token>` → MP4 stream | **Works** |
| `anime` | `lb.wcostream.com` | `lb → m0X.wcostream.com/getvid?evid=<new_token>` | **404 — content unavailable** |

Recent anime (One Piece, Naruto, etc.) uses `embed=neptun`. These work end-to-end.

Old Western cartoons (2 Stupid Dogs, etc.) use `embed=anime`. The `m0X` CDN nodes
return genuine 404 for these files — the content is not hosted there. The embed page
JS itself falls back to `/error.mp4` for these episodes. **Not fixable in the resolver.**

**Test with:** `wco.tv/one-piece-episode-1` or `wco.tv/naruto-episode-1`.

## Status Summary

| Area | Status |
|---|---|
| WCO HTTP resolution chain | Done |
| WCO 404 fix (neptun/lb getvid stage) | Fix applied — follow redirect from Python, pass CDN URL to mpv (awaiting test) |
| WCO quality selection (SD/HD/FHD) | Done |
| WCO modular scaffold files | Created - not yet wired |
| WCO episode navigation (N/P autoplay) | Not started |
| HiAnime N/P controls in NOW PLAYING | Done |
| HiAnime title fix (not "master.m3u8") | Done |
| HiAnime autoplay after EOF | Done |

---

## WCO - What Was Fixed

**Problem (resolved):** mpv received HTTP 404 when calling the pre-fetched CDN URL.

**Root cause:** The resolver was calling `neptun.wcostream.com/getvid?evid=<enc>&json` to
get the CDN redirect URL, then handing that downstream URL to mpv. Neptune generates
a single-use redirect token per request. The token was consumed by the Python
resolver call before mpv could use it.

**Fix:** The resolver now returns `neptun.wcostream.com/getvid?evid=<enc>` (no `&json`)
directly to mpv. mpv hits neptun fresh, gets a live redirect to the CDN, and follows it.

**Confirmed working resolution chain:**
```
wco.tv/<slug>
  -> wcostream.tv/<slug>          (curl_cffi impersonation, Cloudflare bypass)
  -> embed.wcostream.com iframe   (PHPSESSID session cookie acquired here)
  -> getvidlink.php               (returns enc/hd/fhd quality tokens + server URL)
  -> neptun|lb.wcostream.com/getvid?evid=<token>   <- handed to mpv
    -> CDN node (t01/m01/etc.)    (mpv follows redirect here)
      -> MP4 stream
```

---

## WCO - Canonical Resolve Contract

This is the canonical `resolve_target` payload for WCO output and downstream launcher use:

```python
{
  "target_url": str,
  "is_playlist": bool,
  "extra_mpv_flags": list[str],
  "subtitle_urls": list[str],
  "extra_headers": dict[str, str],
  "playlist_items": list[dict],
  "current_index": int,
  "has_next": bool,
  "has_prev": bool,
  "next_episode_url": str,
  "prev_episode_url": str,
  "next_episode_title": str,
  "prev_episode_title": str,
}
```

WCO playlist/autoplay implementation may compute additional internal fields (`has_next`,
`has_prev`, `prev_episode_url`, etc.), but the provider should map output to this canonical
contract before returning.

---

## WCO - Scaffold Modules: Current State

Five scaffold files were created in a previous pass. They are not wired to the
live `wco.py` code. The current working logic lives entirely in `wco.py`.

| File | State | Notes |
|---|---|---|
| `wco.py` | Working | Full provider + resolution. All live logic lives here. |
| `wco_utils.py` | Ready | Duplicates helpers already in `wco.py` - not yet imported |
| `wco_types.py` | Has bug | `validate_resolve_result` incorrectly rejects `getvid?` URLs in strict mode - see below |
| `wco_http.py` | Stub | `NotImplementedError` - resolution logic is in `wco.py` |
| `wco_playlist.py` | Stub | `NotImplementedError` - episode navigation not implemented |
| `wco_playwright.py` | Defer/Delete | Playwright fallback - HTTP resolution works; not needed now |

### wco_types.py bug - strict_final_url

`validate_resolve_result` rejects any URL containing `getvid?` in strict mode:

```python
looks_intermediate = "getvid?" in lower
if looks_intermediate and not looks_stream:
    raise ValueError("WCO resolve result appears to be an intermediate getvid URL")
```

This is wrong. The confirmed playable URL is a `getvid?evid=...` URL on
neptun/lb.wcostream.com. It is not an intermediate URL in this integration path.

If `wco_types` is ever wired in, `validate_resolve_result` must be updated to accept
`getvid?evid=` on known WCO streaming hosts as a valid target.

---

## WCO - Remaining Work

### 1. Wire wco.py to wco_utils.py (deduplication)

`wco.py` currently has its own `_VALID_HOSTS`, `_slug_to_title`, and `_wcostream_url`
that duplicate what is already in `wco_utils.py`. `wco.py` should import from
`wco_utils.py` and remove the duplicates.

This is a refactor only - no behavior changes.

### 2. Fix wco_types.py validate_resolve_result

Update `validate_resolve_result` strict mode to accept `getvid?evid=` URLs on
known WCO CDN hosts (neptun/lb.wcostream.com) as valid playable targets.

### 3. Implement wco_http.py

Move the resolution pipeline from `wco.py._resolve_fresh` into
`wco_http.resolve_episode_http()`, returning a `WCOResolveResult`.

Make `wco.py._resolve_fresh` call `resolve_episode_http()` and map the result to the
canonical provider contract. This makes the HTTP logic independently testable.

### 4. Implement wco_playlist.py - episode navigation

Fetch the series episode list so WCO episodes support N/P navigation and autoplay,
matching the HiAnime experience.

**What needs to happen:**
- Given an episode URL like `wco.tv/dragon-ball-z-episode-5`, derive the series page
  URL (for example `wco.tv/anime/dragon-ball-z/?season=all`)
- Fetch the series page and parse the episode list (title + URL per episode)
- Identify the current episode index within the list
- Compute navigation internals (`has_next`, `next_episode_url`, `has_prev`, `prev_episode_url`)
- Map output back to canonical provider contract (`playlist_items`, `current_index`, `next_episode_url`)

These fields feed into the existing N/P/autoplay machinery in `youtube/launcher.py`
(the same path that powers HiAnime navigation).
No launcher behavior changes are required for WCO if these fields are populated.

**Series page URL derivation:** episode slug format is
`<show-name>-episode-<N>[-english-dubbed|subbed]`. The series slug is the part before
`-episode-`.
This is a working hypothesis and must be probe-validated against real WCO series URL patterns.

### 5. Drop or archive wco_playwright.py

Playwright is not needed for the current confirmed path. The scaffold can be deleted
or retained as a deferred placeholder with explicit comments.

**Recommendation:** delete it for now to reduce dead code and confusion.

---

## HiAnime - Current State

All core HiAnime features are working:

- Title populated from `getEpisodes` data (not the empty `episodeTitle` from
  `getEpisodeSources`). Streaming filename filter prevents `.m3u8` from overwriting it.
- NOW PLAYING shows `[N] Next episode` / `[P] Previous episode` hints when navigation is available.
- N/P keys during playback immediately load next/prev episode via a new launcher process.
- Autoplay after EOF uses 5-second countdown with `N=play now` / `C` or `Q=cancel`.
- Resolver cache: `AniwatchProvider._cache` prevents double-fetching within one session
  (`fetch_title` + `resolve_target` share the cache).

No known HiAnime issues at this time.

---

## Implementation Order

1. Fix `wco_types.py` `validate_resolve_result` (strict mode getvid check).
2. Wire `wco.py` imports to use `wco_utils.py` (remove duplicates).
3. Implement `wco_http.py` by migrating the working HTTP logic from `wco.py`.
4. Make `wco.py` a thin facade calling `wco_http.resolve_episode_http()`.
5. Implement `wco_playlist.py` episode list fetching and index detection.
6. Wire playlist result into canonical resolve output (`playlist_items`, `current_index`, `next_episode_url`).
7. Verify N/P navigation and autoplay work for WCO episodes end-to-end.
8. Delete or archive `wco_playwright.py`.

Steps 1-4 are refactoring with no user-visible change. Steps 5-7 deliver new
functionality. Step 8 is cleanup.

---

## Validation Checklist

### Playback (existing)
- [x] mpv opens successfully (no 404, no exit code 2)
- [x] `runtime/mpv.log` shows stream opened without errors
- [x] video/audio starts within normal time
- [x] provider log shows selected=WCO, resolved URL host, quality token length

### Quality
- [ ] `--quality best` selects FHD token (observed around 512 bytes)
- [ ] `--quality 720p` selects HD token (observed around 512 bytes)
- [ ] `--quality 480p` selects SD/enc token (observed around 491 bytes)
- [ ] falls back gracefully when a quality tier is absent

### Episode navigation (after wco_playlist.py is implemented)
- [ ] NOW PLAYING shows `[N] Next episode` / `[P] Previous episode` when available
- [ ] N key loads next episode immediately
- [ ] P key loads previous episode immediately
- [ ] autoplay countdown appears after EOF when next episode exists
- [ ] first episode: no [P], no prev autoplay
- [ ] last episode: no [N], no autoplay after EOF

---

## Key File Locations

| File | Purpose |
|---|---|
| `media/providers/wco.py` | Provider + all live resolution logic |
| `media/providers/wco_utils.py` | URL helpers (ready, not yet wired) |
| `media/providers/wco_types.py` | Result types + validator (has bug, see above) |
| `media/providers/wco_http.py` | HTTP resolver scaffold (`NotImplementedError`) |
| `media/providers/wco_playlist.py` | Playlist scaffold (`NotImplementedError`) |
| `media/providers/wco_playwright.py` | Playwright scaffold (defer/delete) |
| `media/providers/base.py` | Provider base class (resolve_target takes quality) |
| `youtube/launcher.py` | mpv orchestration, N/P/autoplay logic |
| `integrations/aniwatch-js/resolve.js` | HiAnime resolver (Node.js) |

