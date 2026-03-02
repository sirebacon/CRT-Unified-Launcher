# Multi-Website Media Support Plan

## Goal
Make the current YouTube-on-CRT flow reusable for other websites without duplicating session logic (window move, snap/unsnap, telemetry panel, key controls, IPC handling).

## Why This Is Needed
- Current launcher mixes site-specific logic (YouTube URL rules, yt-dlp behavior) with generic playback/session behavior.
- Adding new websites directly to the existing YouTube flow will increase fragility and regressions.
- A provider model keeps per-site behavior isolated and lets the CRT/session stack stay stable.

## Supported Site Categories

Two provider types are supported. They share the same MediaSession, window/snap behavior,
IPC loop, and telemetry — but differ in how mpv receives the stream URL.

### Tier 1 — yt-dlp-backed providers
Examples: YouTube, Vimeo, Bilibili, Dailymotion, Twitter/X clips, Reddit videos, TikTok.

mpv invocation:
```
mpv --script-opts=ytdl_hook-ytdl_path=yt-dlp.exe <url>
```
A Tier 1 provider is a thin yt-dlp configuration wrapper. It contributes only:
- Which hosts to accept in `can_handle()`
- Whether `--ytdl-raw-options=yes-playlist=` applies
- A `--ytdl-format` string for quality selection
- Any extractor-specific args (e.g. `--extractor-args "youtube:player_client=android"`)

MediaSession owns the base mpv command. The provider contributes deltas via
`mpv_extra_args()`. Adding a Tier 1 provider is typically under 50 lines.

### Tier 2 — resolver-backed providers
Examples: HiAnime (hianime.to), and other JS-rendered anime streaming sites not supported
by yt-dlp.

mpv invocation:
```
mpv --no-ytdl [--sub-file=<subtitle_url> ...] <resolved_hls_or_mp4_url>
```
A Tier 2 provider calls an external resolver subprocess (e.g. `integrations/aniwatch-js`)
to obtain the raw stream URL and subtitle tracks before mpv is launched. The provider's
`resolve_target()` returns the pre-resolved URL; MediaSession passes it directly to mpv
without the yt-dlp hook. The resolver runs as a short-lived subprocess; its output is JSON.

The `uses_ytdl: bool` capability flag distinguishes the two tiers. MediaSession includes
`--script-opts=ytdl_hook-ytdl_path=yt-dlp.exe` only when `uses_ytdl` is `True`.

### Out of Scope (current plan)
- **Live streams:** mpv will play them if a live URL is pasted, but session-save,
  bookmarks, and resume are not guaranteed to behave correctly. No special handling planned.
- **External tool streams (e.g. Twitch via streamlink):** requires a two-step resolution
  outside the yt-dlp path; not a primary use case for CRT playback.
- **DRM content:** Netflix, Disney+, Amazon Prime Video — Widevine DRM, not playable in mpv
  without a custom CDM build. No plan to support these.

### JS-Rendered Anime Streaming Sites
Sites like 9animetv.to, Zoro/Aniwatch, AnimePahe, and similar aggregators render their
video players entirely in JavaScript. yt-dlp returns `Unsupported URL` for these - they
are not reachable via the standard yt-dlp hook path.

Three approaches exist, in order of integration effort:

**Option A - aniwatch-js resolver bridge (current direction)**
Use the local Node integration at `integrations/aniwatch-js` to resolve anime metadata,
episode servers, and raw stream URLs via the installed `aniwatch` package.

Integration pattern: the launcher calls a small Node resolver script (non-interactive),
receives a resolved stream URL (m3u8/mp4) plus headers/subtitle metadata, and passes the
URL to mpv as a `GenericProvider` target. This preserves the existing MediaSession model.

Status: **Installed** (2026-03-02). Local package scaffold exists at
`integrations/aniwatch-js` with dependency `aniwatch@^2.24.3`.

Implementation notes:
- Keep Node logic isolated to `integrations/aniwatch-js`; Python side treats it as an
  external resolver process.
- Standardize resolver output as JSON so MediaSession parsing is deterministic.
- Preserve provider capability flags (`supports_playlist`, `supports_title_fetch`,
  `supports_resume`) on the Python provider based on resolver support.
- Keep a timeout/fallback path so launcher startup cannot hang on resolver failures.

Previous `ani-cli` investigation remains valid as background context:
- `ani-cli` is search-based and not URL-native.
- For allmanga/allanime URLs specifically, direct API integration is still viable.
- See `ani-cli-allmanga-investigation.md` for historical findings.

**Option B - custom yt-dlp extractor (best long-term integration)**
yt-dlp supports local extractor plugins via `--extractor-plugins`. Writing a Python
extractor for a specific site requires reverse-engineering the site's video delivery API
(typically visible in browser DevTools network tab as an `.m3u8` or `.mp4` request). Once
written, the site behaves like any other yt-dlp-backed provider with no changes to the
launcher architecture.

Effort: medium. Requires one-time reverse-engineering per site. Extractors can break when
sites update their delivery mechanism.

**Option C — Playwright-based resolver (most powerful, highest effort)**
A small Python script using [Playwright](https://playwright.dev/python/) launches a
headless browser, navigates to the URL, intercepts the network request for the media
stream, and returns the raw URL to the launcher. Works for any JS-rendered site regardless
of obfuscation. Most resilient to site structure changes since it observes real network
traffic rather than scraping HTML.

Effort: high. Requires Playwright installation and a per-site wait/intercept script.
Adds a browser dependency to the launcher stack.

**Recommendation:** proceed with Option A (`aniwatch-js` resolver bridge) as the immediate path for Aniwatch/HiAnime support. Keep Option B (custom yt-dlp extractor) as the long-term fallback for sites where scraper-based resolution proves unstable.

## Target Architecture

### 1. MediaSession (generic)
Owns:
- mpv process launch + reconnect behavior
- base mpv command (pipe name, window flags, yt-dlp hook path)
- window placement and adjust mode
- snap/unsnap and profile rect handling
- key loop and mode switching
- telemetry rendering and IPC health behavior
- session/history/bookmark persistence primitives

Must not know website-specific URL rules, format strings, or extractor args.

### 2. Provider Interface (site-specific)
Each site implements the same contract:
- `name() -> str`
- `can_handle(url: str) -> bool`
- `validate(url: str) -> Optional[str]`
- `resolve_target(url: str) -> dict`
- `fetch_title(url: str) -> str`
- `is_playlist(url: str) -> bool`
- `mpv_extra_args(url: str, quality: str, config: dict) -> list[str]`

`resolve_target` returns:
```python
{
  "target_url": str,              # what gets passed to mpv (may differ from input URL)
  "is_playlist": bool,
  "extra_mpv_flags": list[str],   # e.g. ["--ytdl-raw-options=yes-playlist="]
  "subtitle_urls": list[str],     # optional; mpv receives as --sub-file=<url> (Tier 2 only)
  "extra_headers": dict,          # optional; passed as --http-header-fields= (Tier 2 only)
}
```

Tier 2 providers (resolver-backed) populate `subtitle_urls` and `extra_headers` from the
resolver JSON output. Tier 1 providers leave these empty.

Static capability flags (declared per provider):
- `uses_ytdl: bool`               # True = yt-dlp hook in mpv command; False = --no-ytdl
- `supports_playlist: bool`
- `supports_title_fetch: bool`
- `supports_resume: bool`         # requires reliable IPC time-pos reads
- `requires_cookies: bool`

Only capability flags that are `True` have their corresponding UI controls shown.

### 3. Quality Presets (per-provider)
Quality presets are **provider-owned**, not global. yt-dlp format selector strings
(`bestvideo[height<=720]+bestaudio/best[height<=720]`) work for most Tier 1 sites but
format availability varies — some sites offer only `best`/`worst`, some use named formats.

Each provider defines its own quality preset map in `crt_config.json` under its provider
section. MediaSession passes the quality label through; the provider resolves it to the
correct format string for that site.

### 4. Cookie and Auth

**Tier 1 (yt-dlp-backed):** Auth is a yt-dlp concern, never a MediaSession concern.

- **Cookie file**: `--cookies=/path/to/cookies.txt` — stable, works for most authenticated
  sites (Patreon, Nebula, private YouTube videos, etc.)
- **Browser extraction**: `--cookies-from-browser=chrome` — convenient but fragile across
  browser updates; not recommended for automated playback

Both are passed as yt-dlp args via `mpv_extra_args()`. MediaSession never reads or
manages cookie files directly. If a cookie path is configured, the provider must log the
resolved path at DEBUG level on each launch so auth failures are diagnosable.

**Tier 2 (resolver-backed):** Auth is the resolver subprocess's concern. The Node resolver
receives any required session tokens or headers via its config input and returns
`extra_headers` in its JSON output. MediaSession passes those through to mpv via
`--http-header-fields=`. The Python provider never handles auth tokens directly.

### 5. Provider Registry
A central registry resolves URL -> provider.
- First matching provider handles request.
- If none match, fallback to `GenericProvider`.

### 6. Config Separation
Keep shared config in `crt_config.json`, add provider sections:
- `providers.youtube`
- `providers.vimeo`
- etc.

Only provider sections may contain provider-specific flags (cookies, extractor args,
quality presets, domain settings).

**Migration note:** Current `crt_config.json` uses flat keys (`youtube_audio_device`,
`youtube_quality_presets`, `youtube_ipc_duplex`). These remain valid and are read by
`YouTubeProvider` during Phase 0. A `providers.youtube` section is additive; flat keys
are not removed until Phase 2 is stable. `load_config()` in `youtube/config.py` is
replaced by a generic config loader that passes provider sections through to each
provider's own config reader.

## Existing Code: What Moves Where

Most of the generic session stack already exists in `youtube/`. Phase 0 scope is narrower
than it appears — only `youtube/config.py` (URL/target logic) and the provider-dispatch
section of `youtube/launcher.py` need surgery. The rest moves as-is:

| File | Destination | Notes |
|------|-------------|-------|
| `youtube/adjust.py` | `media/core/adjust.py` | No YouTube-specific logic |
| `youtube/controls.py` | `media/core/controls.py` | No YouTube-specific logic |
| `youtube/player.py` | `media/core/player.py` | No YouTube-specific logic |
| `youtube/telemetry.py` | `media/core/telemetry.py` | IPC-based, fully generic |
| `youtube/state.py` | `media/core/state.py` | URL-keyed, works for any provider |
| `youtube/queue.py` | `media/core/queue.py` | Just URL lists, provider-agnostic |
| `youtube/config.py` (URL/title/validate/quality fns) | `media/providers/youtube.py` | YouTube-specific logic |
| `youtube/config.py` (load_config, path constants) | `media/core/config.py` | Generic config loading |
| `youtube/launcher.py` | `media/core/session.py` + thin entrypoint | Provider dispatch extracted |

## Proposed Folder Structure
```
media/
  core/
    adjust.py
    config.py
    controls.py
    player.py
    queue.py
    session.py      # MediaSession — main orchestration loop
    state.py
    telemetry.py
  providers/
    base.py         # Provider interface + capability flags (both tiers)
    generic.py      # GenericProvider fallback
    registry.py
    youtube.py      # Tier 1
    aniwatch.py     # Tier 2 — calls integrations/aniwatch-js resolver
integrations/
  aniwatch-js/      # Node.js resolver bridge (aniwatch@^2.24.3)
    package.json
    resolve.js      # CLI entry: accepts episode URL, prints JSON stream info to stdout
youtube/            # kept as thin shim during transition; removed after Phase 2
```

## Rollout Plan

### Phase 0: No Behavior Change Refactor
- Scaffold `media/providers/base.py` and `media/providers/registry.py`.
- Move generic modules (`adjust`, `controls`, `player`, `telemetry`, `state`, `queue`) to `media/core/` unchanged.
- Wrap current YouTube URL/target/title/is_playlist logic in `YouTubeProvider`.
- Replace provider-specific dispatch in `launcher.py` with registry lookup.
- Keep `youtube/` as import shims until Phase 1 is complete.
- Keep all CLI args (`--url`, `--quality`, `--queue-file`, `--add-to-queue`) and all key bindings unchanged.

Acceptance:
- Existing YouTube flows behave identically.
- No changes required in user workflow.
- `youtube/` shims pass all existing smoke tests.

### Phase 1: Generic Provider
- Add `GenericProvider` for direct media URLs and local files that mpv can open natively.
  `supports_title_fetch: False`, `supports_playlist: False`, `supports_resume: False`.
- Hide unsupported controls based on capability flags.

Acceptance:
- Direct URL/file playback works with window and key controls.
- Controls not applicable to the active provider are not shown.

### Phase 2: Add HiAnime Provider (Tier 2)
- Write `integrations/aniwatch-js/resolve.js`: accepts a hianime.to episode URL via
  argv, calls `getEpisodeServers()` then `getAnimeEpisodeSources()`, prints resolved
  stream URL + subtitle tracks as JSON to stdout, exits non-zero on failure.
- Add `media/providers/aniwatch.py`: `can_handle` matches `hianime.to` URLs, `resolve_target`
  calls the Node script as a subprocess with a timeout, parses JSON output.
- `uses_ytdl: False`, `supports_playlist: True`, `supports_title_fetch: True`,
  `supports_resume: True`.
- Document resolver config (Node path, timeout) under `providers.hianime` in `crt_config.json`.
- Remove `youtube/` shim layer once HiAnime provider is confirmed stable.

Acceptance:
- hianime.to URL auto-routes to AniwatchProvider without user intervention.
- Stream plays in mpv with correct window placement and subtitle track available.
- Resolver subprocess failure (timeout, bad URL, site down) degrades gracefully with a
  logged error — launcher does not hang.
- Playlist: episode list fetched, next/prev navigation works.
- New provider runbook exists (see Definition of Done).

### Phase 3: Capability Matrix and Fallback Rules
- Capability flags (`supports_playlist`, `supports_title_fetch`, `supports_resume`, etc.)
  are enforced: MediaSession hides controls the active provider does not support.

Acceptance:
- No broken or non-functional controls shown for any provider or mode.
- Degrading to write-only IPC mode suppresses resume/bookmark controls cleanly.

## Risk Areas
- IPC differences are not provider-specific; avoid per-provider IPC forks.
- Playlist semantics vary by site; normalize with provider capability flags rather than
  conditional branches in MediaSession.
- Auth/cookies can break silently; require explicit log lines for cookie path loaded and
  any extractor errors at DEBUG level.
- Regression risk if window/snap behavior leaks into provider modules — provider modules
  must not call `move_window`, `get_rect`, or any MediaSession function directly.
- yt-dlp extractor breakage — yt-dlp ships extractor updates frequently; a site that works
  today may break after an update. Keep yt-dlp updated and treat extractor errors as a
  first suspect when a previously working provider stops resolving URLs.
- **Resolver subprocess (Tier 2):** The Node resolver is a short-lived process. If it
  hangs, the launcher hangs. Always enforce a hard timeout (default 10s) and treat
  non-zero exit or timeout as a hard failure with a user-visible error, not a silent
  fallback.
- **aniwatch package breakage:** The `aniwatch` npm package scrapes hianime.to. Site
  structure changes can break it between package versions. Pin the version in
  `package.json` and test after any update. Keep the package version in
  `providers.hianime.resolver_version` in `crt_config.json` so breakage is diagnosable
  from logs.
- **Node.js availability:** The resolver requires Node.js on PATH. If Node is missing, the
  AniwatchProvider must fail at registration time (not at playback time) with a clear
  message.

## Non-Goals (for this plan)
- Live streams — mpv will play them if a live URL is pasted, but session-save, bookmarks,
  and resume are not guaranteed to behave correctly. No special handling planned.
- Full browser automation for DRM/unsupported streams.
- Site-specific scraping in core modules.
- Replacing mpv with a different player.

## Testing Strategy
- Smoke tests per provider:
  - single video plays and title displays correctly
  - playlist (if `supports_playlist`): next/prev, title updates per item
  - transition between playlist items preserves window rect and zoom state
  - snap -> unsnap -> snap during playback
  - bookmark save and jump (if `supports_resume`)
- IPC mode checks:
  - write-only mode degrades gracefully (resume/bookmark controls hidden)
  - duplex mode updates telemetry fields live
- Terminal UX checks:
  - status line remains live and does not duplicate
  - controls panel reflects active provider capabilities (no phantom keys)
- Config checks:
  - missing provider section falls back to defaults without crash
  - unknown quality preset logs warning and uses `best`
- Tier 2 resolver checks:
  - resolver JSON output parses correctly into `resolve_target` dict
  - subtitle URL is passed to mpv and track appears in player
  - resolver timeout (simulated by killing the Node process) is caught and surfaced as
    an error, not a hang
  - Node not on PATH: AniwatchProvider fails at registration with a clear message
  - aniwatch package returns no sources: provider logs error, does not launch mpv with
    an empty URL

## Definition of Done
- Adding a new **Tier 1** provider requires only:
  - new provider file in `media/providers/`
  - one registry entry
  - optional provider config section in `crt_config.json`
- Adding a new **Tier 2** provider requires only:
  - a resolver script in `integrations/<name>/`
  - new provider file in `media/providers/`
  - one registry entry
  - optional provider config section in `crt_config.json`
- MediaSession is unchanged when onboarding either type of provider.
- Existing YouTube behavior remains stable.
- A "how to add a provider" runbook exists covering:
  - one working Tier 1 example (YouTube or Vimeo) with quality presets, cookie config,
    and capability flags
  - one working Tier 2 example (HiAnime) with resolver JSON contract, timeout config,
    and subtitle passthrough

## Immediate Next Steps
1. Scaffold `media/providers/base.py` (interface + capability dataclass including
   `uses_ytdl`) and `media/providers/registry.py`.
2. Move generic modules to `media/core/` with `youtube/` shims keeping imports working.
3. Move YouTube URL/target/title/validate/quality logic into `media/providers/youtube.py`.
4. Replace provider-dispatch in `launcher.py` with registry lookup; keep all CLI args and
   keys unchanged.
5. Add `GenericProvider` as fallback.
6. Write `integrations/aniwatch-js/resolve.js` (accepts hianime.to URL, outputs JSON
   stream info).
7. Add `media/providers/aniwatch.py` wired to the Node resolver subprocess.
8. Verify end-to-end: hianime.to episode URL → resolver → raw HLS → mpv with subtitles.

