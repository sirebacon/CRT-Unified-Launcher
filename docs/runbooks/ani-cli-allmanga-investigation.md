# ani-cli / allmanga.to Investigation

**Date:** 2026-03-02
**Context:** Testing Option A from the multi-website media support plan — ani-cli as an
external resolver for JS-rendered anime streaming sites that yt-dlp cannot handle.

## Test URL

```
https://allmanga.to/bangumi/F2drY6aLebFshBrYN/p-1-sub
```

Show: **Berserk (1997)**
Show ID: `F2drY6aLebFshBrYN`
Episode: 1, sub

---

## Installation

ani-cli 4.10.0 installed to `C:\Program Files\Git\bin\bash.exe` (on Git Bash PATH).
Confirmed accessible: `ani-cli --version` returns `4.10.0`.

---

## Backend Discovery

Inspecting the ani-cli script (`~/.local/bin/ani-cli`):

```sh
allanime_refr="https://allmanga.to"
allanime_base="allanime.day"
allanime_api="https://api.${allanime_base}"
```

**ani-cli's backend is allmanga.to / api.allanime.day.**
The URL the user submitted is from ani-cli's own CDN.
This means any allmanga.to URL is natively supported by ani-cli's resolver stack —
no third-party integration required.

---

## API Test Results

### Episode List Query

Called `episodes_list_gql` with show ID `F2drY6aLebFshBrYN`:

```json
{
  "availableEpisodesDetail": {
    "sub": ["25","24","23",...,"1"],
    "dub": ["25","24","23",...,"1"],
    "raw": []
  }
}
```

- 25 episodes available, both sub and dub. Raw not available.

### Stream Sources for Episode 1 (Sub)

Called `episode_embed_gql` with `showId`, `translationType: sub`, `episodeString: 1`.

Decoded source list (name : priority):

| Source | Priority | Type | Notes |
|--------|----------|------|-------|
| Default | 8.5 | iframe | wixmp — m3u8 multi-quality |
| Yt-mp4 | 7.9 | player | YouTube-hosted MP4 (single quality) |
| Luf-Mp4 | 7.5 | iframe | hianime — m3u8 multi-quality |
| S-mp4 | 7.4 | iframe | SharePoint MP4 (single quality) |
| Vid-mp4 | 4.0 | iframe | vidstreaming.io |
| Mp4 | 4.0 | iframe | mp4upload.com |
| Ok | 3.5 | iframe | ok.ru |
| Sl-mp4 | 3.0 | iframe | Streamlare |
| Uv-mp4 | 1.0 | iframe | (low priority fallback) |

ani-cli's provider selection order (by `generate_link` case):
1. `Default` (wixmp, m3u8, multi-quality)
2. `Yt-mp4` (YouTube, mp4, single)
3. `S-mp4` (SharePoint, mp4, single)
4. `Luf-Mp4` (hianime, m3u8, multi-quality) — fallback

The `--`-prefixed `sourceUrl` values are XOR-encoded and decoded internally by
`get_links()` before a second curl resolves the actual CDN URL.

---

## Critical Finding: ani-cli Does Not Accept URLs

ani-cli is **search-based only**. Usage:

```sh
ani-cli [options] [query]   # query is an anime name, not a URL
```

There is no `--url` flag or URL input mode. The integration pattern described in
`multi-website-media-support-plan.md` — *"the launcher calls ani-cli to resolve the URL"*
— does not match how ani-cli actually works.

---

## Revised Integration Options

### Option A1 — Search ani-cli by name (minimal code)

The launcher extracts or prompts for the anime name and runs:

```sh
ani-cli -S 1 -e 1 --exit-after-play "berserk"
```

Limitations:
- `-S 1` always picks the first search result — fragile if the name is ambiguous.
- Episode number and sub/dub mode must be supplied separately; cannot derive from URL.
- Interactive fzf selection breaks non-interactive launcher use.
- Name must come from user input or a separate page fetch.

### Option A2 — Call allanime API directly (recommended)

Extract the show ID from the allmanga.to URL and call the allanime GraphQL API
directly — replicating what ani-cli does internally, without spawning ani-cli at all.

URL pattern: `https://allmanga.to/bangumi/{showId}/p-{episode}-{mode}`

Steps:
1. Parse `showId`, `episode`, `mode` from the URL.
2. Call `episode_embed_gql` on `https://api.allanime.day/api`.
3. XOR-decode the `sourceUrl` for the chosen provider.
4. Follow the provider-specific resolution step to get the final m3u8/mp4 URL.
5. Pass the raw URL to mpv as a `GenericProvider` target.

This fits the existing launcher architecture cleanly:
- No ani-cli subprocess required.
- No interactive terminal needed.
- Fits the `resolve_target()` provider interface from the media support plan.
- A `AllAnimeProvider` would handle any `allmanga.to` URL.

The XOR decode key and provider resolution logic are already visible in the ani-cli
source and can be ported to Python in under 50 lines.

### Option B — Custom yt-dlp extractor

Still valid. yt-dlp extractor plugin for allanime.day would be the cleanest permanent
solution and would integrate with no changes to MediaSession. Requires one-time
reverse-engineering of the GraphQL + CDN chain.

---

## Recommendation

**Implement Option A2** (direct allanime API calls) as a Python `AllAnimeProvider`.

- Lower effort than a full yt-dlp extractor (Option B).
- More reliable than piping through ani-cli (Option A1).
- API is already validated and documented above.
- Porting the decode logic from the ani-cli shell script to Python is straightforward.
- URL structure gives us show ID, episode, and mode directly — no name search needed.

ani-cli remains useful as a reference implementation and fallback for sites outside the
allanime network, but should not be the runtime dependency for allmanga.to playback.

---

## Next Steps

1. Port the XOR decode + provider resolution chain from ani-cli to a Python helper.
2. Implement `AllAnimeProvider` in `media/providers/allanime.py`:
   - `can_handle`: match `allmanga.to/bangumi/` URLs.
   - `resolve_target`: API call → decode → CDN resolution → raw URL.
   - `supports_playlist: True` (25-episode list confirmed via API).
   - `supports_title_fetch: True` (show name available from API).
   - `supports_resume: True` (raw URL → reliable IPC time-pos reads).
3. Register in `media/providers/registry.py`.
4. Test end-to-end: Berserk ep 1 sub plays in mpv with correct title and window placement.
5. Update `multi-website-media-support-plan.md` to reflect that allmanga.to routes to
   `AllAnimeProvider`, not through ani-cli.
