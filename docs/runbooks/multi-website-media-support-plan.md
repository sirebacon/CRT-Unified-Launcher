# Multi-Website Media Support Plan

## Goal
Make the current YouTube-on-CRT flow reusable for other websites without duplicating session logic (window move, snap/unsnap, telemetry panel, key controls, IPC handling).

## Why This Is Needed
- Current launcher mixes site-specific logic (YouTube URL rules, yt-dlp behavior) with generic playback/session behavior.
- Adding new websites directly to the existing YouTube flow will increase fragility and regressions.
- A provider model keeps per-site behavior isolated and lets the CRT/session stack stay stable.

## Target Architecture

### 1. Core Session Runner (generic)
Owns:
- mpv process launch + reconnect behavior
- window placement and adjust mode
- snap/unsnap and profile rect handling
- key loop and mode switching
- telemetry rendering and IPC health behavior
- session/history/bookmark persistence primitives

Must not know website-specific URL rules.

### 2. Provider Interface (site-specific)
Each site implements the same contract:
- `name()`
- `can_handle(url: str) -> bool`
- `validate(url: str) -> Optional[str]`
- `resolve_target(url: str) -> dict`
- `fetch_title(url: str) -> str`
- `is_playlist(url: str) -> bool`
- `build_mpv_args(...) -> list[str]`

Optional capabilities:
- cookie/auth requirements
- provider-specific metadata extraction
- provider-specific queue normalization

### 3. Provider Registry
A central registry resolves URL -> provider.
- First matching provider handles request.
- If none match, fallback to a generic/direct provider.

### 4. Config Separation
Keep shared config in `crt_config.json`, add provider sections:
- `providers.youtube`
- `providers.vimeo`
- `providers.twitch`
- etc.

Only provider sections may contain provider-specific flags (cookies, extractor args, domain settings).

## Proposed Folder Structure
- `youtube/` (existing module, gradually split)
- `media/core/` (generic runner + session lifecycle)
- `media/providers/base.py` (interface)
- `media/providers/youtube.py`
- `media/providers/generic.py`
- `media/providers/registry.py`

## Rollout Plan

### Phase 0: No Behavior Change Refactor
- Extract provider interface and registry.
- Wrap current YouTube behavior behind `YouTubeProvider`.
- Keep CLI behavior and keys unchanged.

Acceptance:
- Existing YouTube flows behave the same.
- No changes required in user workflow.

### Phase 1: Generic Provider
- Add `GenericProvider` for direct media URLs that mpv can open.
- Keep same window/telemetry/snap flow.

Acceptance:
- Direct URL playback works with current controls.

### Phase 2: Add One New Website
- Add a second provider (recommended: Vimeo first; lower auth complexity).
- Document config requirements.

Acceptance:
- URL auto-routes to the correct provider.
- Playlist/title behavior works at least as well as generic provider.

### Phase 3: Capability Matrix and Fallback Rules
- Add provider capability flags (`supports_playlist`, `supports_title_fetch`, etc.).
- UI adapts based on capabilities (hide unsupported actions).

Acceptance:
- No broken controls shown for unsupported provider features.

## Risk Areas
- IPC differences are not provider-specific; avoid per-provider IPC forks.
- Playlist semantics vary by site; normalize with provider capability flags.
- Auth/cookies can break silently; require explicit log lines for cookie path and extractor errors.
- Regression risk if window/snap behavior leaks into provider modules.

## Non-Goals (for this plan)
- Full browser automation for DRM/unsupported streams.
- Site-specific scraping in core modules.
- Replacing mpv with a different player.

## Testing Strategy
- Smoke tests per provider:
  - single video
  - playlist (if supported)
  - next/prev behavior
  - snap -> unsnap -> snap during playback
  - transition between playlist items preserves window + zoom behavior
- IPC mode checks:
  - write-only mode degrades gracefully
  - duplex mode updates telemetry fields
- Terminal UX checks:
  - top status remains live
  - no duplicate status lines

## Definition of Done
- Adding a new provider requires only:
  - new provider file
  - registry entry
  - provider config section
- Core session logic is unchanged when onboarding a provider.
- Existing YouTube behavior remains stable.

## Immediate Next Steps
1. Scaffold `media/providers/base.py` and `media/providers/registry.py`.
2. Move current YouTube URL/target/title/is_playlist logic into `YouTubeProvider`.
3. Keep launcher entrypoint unchanged, but resolve provider through registry.
4. Add `GenericProvider` as fallback.
5. Add a short runbook for adding a new provider in under 30 minutes.
