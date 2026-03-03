# Multi-Website Media Support Plan

## Goal
Make the current YouTube-on-CRT flow reusable for other websites without duplicating session logic (window move, snap/unsnap, telemetry panel, key controls, IPC handling).

## Why This Is Needed
- Current launcher mixes site-specific logic (YouTube URL rules, yt-dlp behavior) with generic playback/session behavior.
- Adding new websites directly to the existing YouTube flow will increase fragility and regressions.
- A provider model keeps per-site behavior isolated and lets the CRT/session stack stay stable.

## Supported Site Categories

Two provider types are supported. They share the same MediaSession, window/snap behavior,
IPC loop, and telemetry - but differ in how mpv receives the stream URL.

### Tier 1 - yt-dlp-backed providers
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

### Tier 2 - resolver-backed providers
Examples: HiAnime (hianime.to), WCO (wco.tv / wcostream.tv), and other sites not
reliably supported by plain yt-dlp URL handoff.

mpv invocation:
```
mpv --no-ytdl [--sub-file=<subtitle_url> ...] <resolved_hls_or_mp4_url>
```
A Tier 2 provider resolves URLs before playback and returns a normalized payload for mpv.
Resolution can be done either by:
- external subprocess (HiAnime via `integrations/aniwatch-js`)
- in-process HTTP resolver logic (WCO via `media/providers/wco_http.py`)

For WCO specifically, the provider now returns a localhost proxy URL (`127.0.0.1`) to mpv.
The proxy forwards bytes from the upstream CDN using Python's HTTP stack, which avoids
mpv/ffmpeg-side CDN 404 behavior observed on direct WCO CDN playback.

The `uses_ytdl: bool` capability flag distinguishes the two tiers. MediaSession includes
`--script-opts=ytdl_hook-ytdl_path=yt-dlp.exe` only when `uses_ytdl` is `True`.

### Out of Scope (current plan)
- **Live streams:** mpv will play them if a live URL is pasted, but session-save,
  bookmarks, and resume are not guaranteed to behave correctly. No special handling planned.
- **External tool streams (e.g. Twitch via streamlink):** requires a two-step resolution
  outside the yt-dlp path; not a primary use case for CRT playback.
- **DRM content:** Netflix, Disney+, Amazon Prime Video - Widevine DRM, not playable in mpv
  without a custom CDM build. No plan to support these.

### JS-Rendered Anime Streaming Sites
Sites like hianime.to, AnimePahe, and similar aggregators render their video players
entirely in JavaScript. yt-dlp returns `Unsupported URL` for these — they are not
reachable via the standard yt-dlp hook path. They are handled as **Tier 2** providers.

**Current approach: aniwatch-js resolver bridge**
The local Node integration at `integrations/aniwatch-js` resolves anime metadata, episode
servers, and raw stream URLs via the `aniwatch` npm package. The launcher calls
`resolve.js` as a short-lived subprocess, receives a JSON payload (stream URL, subtitle
tracks, episode list), and routes the result through `AniwatchProvider` to mpv.

Status: **Implemented and verified** (2026-03-03). `integrations/aniwatch-js/resolve.js`
and `media/providers/aniwatch.py` are wired into the provider registry, including episode
next/prev and autoplay flow through launcher episode metadata fields.

### WCO Streaming Sites
WCO is implemented as a Tier 2 provider using modular Python resolver files:
- `media/providers/wco.py`
- `media/providers/wco_http.py`
- `media/providers/wco_playlist.py`
- `media/providers/wco_types.py`
- `media/providers/wco_utils.py`

Current behavior:
- resolves WCO episode pages to CDN-backed media flow via curl_cffi (Cloudflare bypass)
- calls `server/getvid?evid=<enc>&json` (matching browser JS) to obtain the CDN URL
- serves playback to mpv through a local HTTP proxy (`127.0.0.1`) to avoid mpv/ffmpeg CDN 404s
- forwards Range headers for seeking support
- populates episode navigation metadata (`has_next`, `has_prev`, next/prev URL/title)

Known limitations:
- **lb cluster (m01/m02)** — Western cartoons (e.g. 2 Stupid Dogs) use `lb.wcostream.com`
  whose CDN nodes return 404 to all Python HTTP clients regardless of TLS fingerprint or
  headers. The browser plays these fine; cause is unknown. The proxy surfaces a 404 to mpv.
- if WCO's embed page JS itself falls back to `/error.mp4` for an episode, no resolver code
  can make that title playable — the content does not exist on WCO at all.

Reference: see `docs/runbooks/wco-mpv-cdn-404-proxy-fix.md`.

Implementation constraints:
- Node logic stays isolated to `integrations/aniwatch-js`; Python treats it as an opaque
  subprocess.
- Resolver output is JSON; schema is defined by the `resolve_target` contract above.
- Hard timeout enforced on the subprocess (default 10s); non-zero exit is a hard failure.

**Fallback for other JS-rendered sites: custom yt-dlp extractor**
If a site is not covered by the aniwatch package, a yt-dlp extractor plugin
(`--extractor-plugins`) is the next option. Requires one-time reverse-engineering of the
site's video delivery API. Once written, it becomes a Tier 1 provider with no resolver
subprocess.

**Historical context:** ani-cli was evaluated first and ruled out — it is search-based and
does not accept URLs. See `ani-cli-allmanga-investigation.md` for details.

## Target Architecture

### 1. MediaSession (generic)
Owns:
- mpv process launch + reconnect behavior
- base mpv command (pipe name, window flags, yt-dlp hook path when `uses_ytdl` is True)
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
  "playlist_items": list[dict],   # optional; normalized episode list for next/prev
  "current_index": int,           # optional; index into playlist_items
  "has_next": bool,               # optional; episode navigation hint
  "has_prev": bool,               # optional; episode navigation hint
  "next_episode_url": str,        # optional; episode navigation target
  "prev_episode_url": str,        # optional; episode navigation target
  "next_episode_title": str,      # optional; episode navigation label
  "prev_episode_title": str,      # optional; episode navigation label
}
```

Tier 2 providers (resolver-backed) populate `subtitle_urls` and `extra_headers` from the
resolver JSON output. Tier 1 providers leave these empty.
If `supports_playlist` is `True`, providers should also populate `playlist_items` and
`current_index` so MediaSession can provide deterministic episode navigation.

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
format availability varies - some sites offer only `best`/`worst`, some use named formats.

Each provider defines its own quality preset map in `crt_config.json` under its provider
section. MediaSession passes the quality label through; the provider resolves it to the
correct format string for that site.

### 4. Cookie and Auth

**Tier 1 (yt-dlp-backed):** Auth is a yt-dlp concern, never a MediaSession concern.

- **Browser extraction**: `--cookies-from-browser=<browser>` — yt-dlp reads cookies
  directly from the browser's on-disk profile. **On Windows, only Firefox is reliably
  supported.** Chrome 127+ uses App-Bound Encryption for its cookie store; yt-dlp cannot
  decrypt it and returns `Failed to decrypt with DPAPI`. Edge has the same restriction.
- **Cookie file**: `--cookies=/path/to/cookies.txt` — a Netscape-format export (e.g. from
  the "Get cookies.txt LOCALLY" Chrome extension). Stable but requires periodic re-export
  as cookies expire.

Both are passed as yt-dlp args via `mpv_extra_args()`. MediaSession never reads or
manages cookie files directly.

**Local config override for cookies:** Cookie settings belong in `crt_config.local.json`
(gitignored) rather than `crt_config.json` (committed). Copy
`crt_config.local.json.example` to `crt_config.local.json` and set either:
```json
{ "youtube_cookies_from_browser": "firefox" }
```
or:
```json
{ "youtube_cookies_file": "D:\\path\\to\\cookies.txt" }
```
`load_config()` in `youtube/config.py` merges the local file on top of the base config at
startup. The local file is never committed to git.

**YouTube n-challenge and JS runtime:** YouTube's `n` parameter challenge requires a
JavaScript runtime to solve. Without it, yt-dlp can only see storyboard images and fails
with `Requested format is not available`. The `YouTubeProvider` always passes
`--js-runtimes=node` to yt-dlp via `--ytdl-raw-options`. Node.js must be on PATH (it is
already required for the AniwatchProvider).

**`--ytdl-raw-options` accumulation:** mpv replaces its `ytdl-raw-options` list each time
the flag appears on the command line — multiple `--ytdl-raw-options=key=value` flags lose
all but the last one. `YouTubeProvider.mpv_extra_args()` therefore combines all raw options
into a single comma-separated flag: `--ytdl-raw-options=js-runtimes=node,cookies-from-browser=firefox`.

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
- `providers.hianime`
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
than it appears - only `youtube/config.py` (URL/target logic) and the provider-dispatch
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
    session.py      # MediaSession - main orchestration loop
    state.py
    telemetry.py
  providers/
    base.py         # Provider interface + capability flags (both tiers)
    generic.py      # GenericProvider fallback
    registry.py
    youtube.py      # Tier 1
    aniwatch.py     # Tier 2 - calls integrations/aniwatch-js resolver
integrations/
  aniwatch-js/      # Node.js resolver bridge (aniwatch@^2.24.3)
    package.json
    resolve.js      # CLI entry: accepts episode URL, prints JSON stream info to stdout
youtube/            # kept as thin shim during transition; removed after Phase 2
```

## Rollout Plan

### Phase 0: No Behavior Change Refactor ✓ DONE
- Scaffold `media/providers/base.py` and `media/providers/registry.py`. ✓
- Wrap current YouTube URL/target/title/is_playlist logic in `YouTubeProvider`. ✓
- Replace provider-specific dispatch in `launcher.py` with registry lookup. ✓
- Keep all CLI args (`--url`, `--quality`, `--queue-file`, `--add-to-queue`) and all key bindings unchanged. ✓
- Note: generic modules (`adjust`, `controls`, etc.) remain in `youtube/` for now; `media/core/` move deferred to a later phase.

### Phase 1: Generic Provider ✓ DONE
- `GenericProvider` added as fallback (`--no-ytdl`, `supports_*: False`). ✓

### Phase 2: Add HiAnime Provider (Tier 2) ✓ DONE
- `integrations/aniwatch-js/resolve.js` written and deployed. ✓
- `media/providers/aniwatch.py` wired to the Node resolver subprocess. ✓
- `uses_ytdl: False`, `supports_playlist: True`, `supports_title_fetch: True`, `supports_resume: True`. ✓

### Phase 2b: Add WCO Provider (Tier 2) ✓ DONE
- Modular WCO resolver/provider stack implemented under `media/providers/wco_*`. ✓
- Local proxy playback path added for mpv compatibility with WCO CDN behavior. ✓
- Episode next/prev metadata wired to existing launcher controls/autoplay path. ✓
- Playwright fallback removed from active design (HTTP path is primary). ✓

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
- Regression risk if window/snap behavior leaks into provider modules - provider modules
  must not call `move_window`, `get_rect`, or any MediaSession function directly.
- yt-dlp extractor breakage - yt-dlp ships extractor updates frequently; a site that works
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
  AniwatchProvider should fail when selected for a matching URL (before playback launch),
  with a clear error, without impacting unrelated providers.

## Future Scope (not current priority)

Once the Tier 1/Tier 2 provider model is stable, the
following sites are natural additions. None require changes to MediaSession or the core
architecture - each is a new provider file and a registry entry.

### Tier 1 additions (yt-dlp-backed, low effort)

| Site | 4:3 content | Notes |
|------|-------------|-------|
| Vimeo | Yes | Large archive of classic films, documentaries, and retro content in 4:3 |
| Dailymotion | Yes | Old TV recordings, classic shows, and retro clips commonly in 4:3 |
| Rumble | Yes | Retro and archival uploads; VOD only (live streams out of scope) |
| Twitch VODs | Yes | Retro gaming streams and classic gaming content; VOD only, no live |
| Bilibili | Yes | Large Japanese/Chinese retro anime and classic game content archive |
| Kick.com | No | yt-dlp supported; VOD only |
| NicoNico | No | yt-dlp supported; may need account cookies for some content |
| Odysee | No | yt-dlp supported |
| Crunchyroll | No | yt-dlp supported with cookie auth; good anime complement to HiAnime |

### Tier 2 additions (resolver-backed, medium effort)

| Site | Notes |
|------|-------|
| AnimePahe | JS-rendered; may be coverable by aniwatch package or needs separate resolver |
| 9animetv.to | JS-rendered; allanime API viable (see `ani-cli-allmanga-investigation.md`) |
| Gogoanime | JS-rendered; popular fallback when HiAnime lacks a title |

### Not planned
- **Funimation** — merged into Crunchyroll; handle via Crunchyroll provider
- **Live streams** — any site; session-save and resume undefined for live content
- **DRM content** — Netflix, Disney+, Amazon Prime; Widevine not supported in mpv

## Non-Goals (for this plan)
- Live streams - mpv will play them if a live URL is pasted, but session-save, bookmarks,
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
  - Node not on PATH: AniwatchProvider fails with a clear message when a matching URL is selected
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

## Implementation Status

### Completed (as of 2026-03-03)

- [x] `media/providers/base.py` — `Provider` ABC + `ProviderCapabilities` dataclass
- [x] `media/providers/registry.py` — URL → provider dispatch, `setup(cfg)`, `get_provider_or_generic(url)`
- [x] `media/providers/youtube.py` — `YouTubeProvider` (Tier 1): cookie auth, js-runtime, quality presets, combined `--ytdl-raw-options`
- [x] `media/providers/generic.py` — `GenericProvider` fallback (`--no-ytdl`, accepts any URL)
- [x] `media/providers/aniwatch.py` — `AniwatchProvider` (Tier 2): calls Node resolver subprocess, timeout, JSON parse
- [x] `integrations/aniwatch-js/resolve.js` — Node resolver for hianime.to (servers → sources → JSON output)
- [x] HiAnime episode navigation/autoplay metadata integrated with launcher controls
- [x] `media/providers/wco.py` — WCO provider facade and registry integration
- [x] `media/providers/wco_http.py` — WCO HTTP resolver + localhost proxy playback path
- [x] `media/providers/wco_playlist.py` — episode list extraction + navigation metadata
- [x] `media/providers/wco_types.py` / `wco_utils.py` — shared contract + helpers
- [x] `docs/runbooks/wco-mpv-cdn-404-proxy-fix.md` — root cause and proxy design record
- [x] `youtube/launcher.py` — updated to use provider registry; prompts generalized to "Media URL"; mpv command built from provider
- [x] `crt_config.local.json` pattern — gitignored local override file; `load_config()` merges it on startup
- [x] `crt_config.local.json.example` — template with cookie key documentation
- [x] mpv `--log-file` — mpv writes internal log to `runtime/mpv.log` (replaces empty stderr capture)

### Remaining / Not Yet Started

- [ ] `media/core/` — generic modules (`adjust`, `controls`, `player`, `telemetry`, `state`, `queue`) not yet moved from `youtube/`; `youtube/` is still the live implementation, not a shim
- [ ] Phase 3 capability enforcement — controls not hidden based on provider flags yet
- [ ] "How to add a provider" runbook
