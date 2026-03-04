# Media History + Continue Watching (Netflix-Style)

Status: **Fully Implemented** — Phases 1–6 complete (including 6.1B, 6.2, 6.3, 6.5, 6.6)
Date: 2026-03-04
Scope: YouTube + HiAnime

---

## Goal

A "continue watching" experience across multiple shows/videos so you can switch content and
resume where you left off, per title/series, without losing place.

---

## What Was Built

### Phase 1 — Persistence and Models

`youtube/progress.py` — atomic read/write of `runtime/media_progress.json`:
- `upsert_progress()` — insert/update by `continue_key`; min-delta guard skips writes if
  position hasn't moved ≥5s (avoids no-op saves while paused)
- `get_continue_lane()` — returns `in_progress` items sorted by `last_watched_at` descending
- `mark_completed()` / `remove_item()` — management helpers
- Outcome constants: `OUTCOME_IN_PROGRESS`, `OUTCOME_COMPLETED`, `OUTCOME_SKIPPED`
- Pruning: at most 20 in-progress + 20 done entries kept (cap configurable)

`youtube/media_history.py` — unified cross-provider history in `runtime/media_history.json`:
- `add_entry()`, `get_history()`, `remove_entry()`, `clear_provider()`, `clear_all()`
- One-time import from legacy `runtime/youtube_history.json` on first run

### Phase 2 — Provider Identity Adapters

`get_continue_metadata(url) -> dict` added to `media/providers/base.py` (stub),
`media/providers/youtube.py`, and `media/providers/aniwatch.py`.

Returned dict shape:
```python
{
  "continue_key": str,       # e.g. "hianime:series:naruto-123"
  "entity_type": str,        # "video" | "series"
  "title": str,
  "sub_title": str,          # episode title for series
  "episode_index": int,      # 0-based; used for next-episode derivation
  "episode_url": str,        # direct episode URL for resume
  "target_url": str,         # canonical landing page URL
}
```

Key formats:
- YouTube: `youtube:video:<video_id>`
- HiAnime series: `hianime:series:<series-slug>`

### Phase 3 — Launcher Integration

`youtube/launcher.py` updates:
- Continue Watching lane shown at startup **only when in-progress items exist** — zero
  added friction when the lane is empty.
- `provider.get_continue_metadata(url)` called after resolution; `episode_index` backfilled
  from `resolved["current_index"]` when not yet in cache.
- Periodic progress checkpoints every `media_progress_save_interval_sec` seconds (default 15).
- In-playback `K` key marks current item completed immediately.
- In-playback `H` key opens the Watch History screen without quitting mpv.
- Finalization on exit: writes final outcome (`completed`, `skipped`, or `in_progress`)
  based on progress percent vs. `media_completion_threshold_pct` threshold.
- `N`/`P` key presses set skip flags → finalization records `skipped` when pct < threshold.

### Phase 4 — UX and Management (Continue UI)

`youtube/continue_ui.py`:
- `run_continue_lane()` — interactive Continue lane (see Phase 6 for full key list)
- `run_media_history_screen()` — paginated history; Y/I/A filter, R<N> remove, C clear

Config knobs in `crt_config.json`:
- `media_continue_enabled` (default `true`)
- `media_continue_max_items` (default `20`)
- `media_progress_save_interval_sec` (default `15`)
- `media_completion_threshold_pct` (default `92`)

### Phase 5 — Migration

One-time import of `runtime/youtube_history.json` into `runtime/media_history.json` on first
run. Import is idempotent (sentinel file `youtube_history.json.imported` prevents re-import).

### Phase 6 — UX Enhancements

All Phase 6 sub-features are implemented.

#### 6.1B — Bookmark Picker from Continue Lane

`B<N>` in the Continue lane opens the bookmark list for item N. Bookmarks are looked up via
`get_bookmarks(url)` using the item's `episode_url` (or `target_url` as fallback). Selecting
a bookmark returns the URL at that exact timestamp — no separate screen needed.

```
Continue Watching:
  1) Super Demon Hero Wataru  [Episode 3 ...]  → Ep 4  57%  2026-03-04
  B<N> bookmark — opens bookmark list for item N
Pick: B1
  1) Opening ends  @ 1:31
  2) Fight starts  @ 8:44
Pick bookmark (Enter to cancel): 2
  → plays from 8:44
```

#### 6.2 — HiAnime "Up Next" Row Hint + U<N> Action

Each HiAnime entry in the Continue lane now shows a `→ Ep N` hint when `episode_index` is
known (e.g. `→ Ep 4` for an item at episode_index=2, since 0-based index 2 means episode 3,
next is episode 4).

`U<N>` re-resolves the stored `episode_url` through the HiAnime provider and retrieves
`next_episode_url` from the resolved metadata. The launcher then calls `provider.resolve_target`
a second time on that URL so the next episode plays from the beginning (position=None).
If no `next_episode_url` is available, falls back to playing the current episode.

```
Continue Watching:
  1) Super Demon Hero Wataru  [Episode 3 ...]  → Ep 4  57%  2026-03-04
  U<N> up-next — play next episode from beginning
Pick: U1
  → resolves next episode URL → plays Ep 4 from 0:00
```

#### 6.3 — Recent Activity Screen

`A` from the Continue lane (or `H` from the Activity screen) opens `run_recent_activity_screen()`.

Merges in-progress Continue items and history entries, de-duplicates by URL (in-progress wins
when the same URL appears in both), sorts by timestamp descending, shows up to 25 items.

Each row shows: `▶/✓/»` badge, `[prov]`, title, optional sub_title, progress %, date.

From the Activity screen: `H` opens the full History screen, `X` exits, number re-opens URL.

#### 6.4 — Progress Safety Guards *(implemented in Phase 4)*

- Checkpoint skips if `duration_sec` is unknown or `resume_position_sec < 30`.
- Resume position clamped to `duration_sec - 10` to avoid resume-at-end edge cases.
- Finalization skips `in_progress` write if position < 30s (avoids polluting Continue lane
  from accidental opens).

#### 6.5 — Bookmark-Aware Resume Prompt

When a Continue lane item is selected by number and **both** a saved resume position and at
least one bookmark exist for that URL, the user sees a choice prompt before playback starts:

```
  Resume at 8:44 (saved)  or pick bookmark?
  1) Resume at 8:44
  2) Pick bookmark
Pick [Enter=1]:
```

Picking `2` shows the numbered bookmark list. Selecting a bookmark overrides the resume
position. Pressing Enter or selecting `1` resumes from the saved position. This integrates
the bookmark system directly into the Continue lane selection flow.

#### 6.6 — Media Diagnostics in crt_tools

New `tools/media.py` module exposes two diagnostic commands via `crt_tools.py`:

```bash
python crt_tools.py media progress   # in-progress + done entries, formatted table
python crt_tools.py media history    # stats by provider/outcome + recent 15 entries
```

`media progress` output:
```
=== Media Progress  (2 in-progress, 3 done) ===

In-progress:
  ▶ [hia] Super Demon Hero Wataru  [Episode 3 - ...]
       12:44/24:01  57%  2026-03-04 22:10  key=hianime:series:super-...
  ▶ [you] Cool YouTube Video
       4:12/10:30  40%  2026-03-03 18:44  key=youtube:video:abc123

Done (completed/skipped):
  ✓ [hia] Another Show  [Episode 12]
       ...
```

`media history` output:
```
=== Watch History  (15 total entries) ===

By provider:
  youtube       10
  hianime        5

By outcome:
  ✓ completed        8
  ▶ in_progress      4
  » skipped          3

Most recent 15 entries:
  ✓ [you] Cool YouTube Video         100%  2026-03-04
  ...
```

---

## Data Model

### `runtime/media_progress.json`

```json
{
  "version": 1,
  "items": [
    {
      "continue_key": "hianime:series:super-demon-hero-wataru-4045",
      "provider": "hianime",
      "entity_type": "series",
      "title": "Super Demon Hero Wataru",
      "sub_title": "Episode 3 - Fierce Battle",
      "target_url": "https://hianime.to/watch/...",
      "episode_url": "https://hianime.to/watch/...?ep=23",
      "episode_index": 2,
      "resume_position_sec": 764.3,
      "duration_sec": 1420.0,
      "progress_pct": 53.8,
      "last_watched_at": "2026-03-04T22:10:03Z",
      "is_completed": false,
      "playback_outcome": "in_progress"
    }
  ]
}
```

- `playback_outcome` is the **source of truth**. `is_completed` is a derived convenience field.
- `next_episode_url` is **not stored** — always derived dynamically at resume-time from
  `episode_index + 1` + a live `getEpisodes` API call. This prevents stale cached URLs.
- Pruning cap: 20 in-progress + 20 done = 40 entries max (~16KB). Configurable via
  `media_continue_max_items`.

### `runtime/media_history.json`

A flat JSON list of history entries, newest first. Cap: 500 entries (~75KB).

```json
[
  {
    "url": "https://hianime.to/watch/...?ep=23",
    "title": "Super Demon Hero Wataru",
    "provider": "hianime",
    "progress_pct": 53.8,
    "playback_outcome": "in_progress",
    "watched_at": "2026-03-04T22:10:03Z"
  }
]
```

---

## Continue Lane — Full Key Reference

At startup (when in-progress items exist):

```
Continue Watching:
  1) Title  [Sub]  → Ep N    57%  YYYY-MM-DD
  ...

  1-N play  R<N> remove  K<N> mark done  B<N> bookmark  U<N> up-next  H history  A activity  Enter URL prompt
```

| Key | Action |
|-----|--------|
| `1`–`N` | Play item; if bookmarks exist → shows Resume vs. Pick Bookmark prompt (6.5) |
| `R<N>` | Remove item from Continue lane immediately |
| `K<N>` | Mark item as completed; drops from Continue lane |
| `B<N>` | Open bookmark list for item; pick number to play from that timestamp |
| `U<N>` | Play next episode (HiAnime only); re-resolves via live API |
| `H` | Open Watch History screen |
| `A` | Open Recent Activity screen (merged in-progress + history) |
| Enter | Proceed to URL prompt |

---

## Outcome Classification

| Outcome | Condition |
|---------|-----------|
| `completed` | `progress_pct >= media_completion_threshold_pct` (default 92%) |
| `skipped` | N/P pressed during HiAnime playback **and** pct < threshold |
| `in_progress` | Playback exited/stopped below threshold without N/P skip action |

`completed` and `skipped` remove items from the Continue lane. All outcomes are recorded in
History. Only `in_progress` items appear in the Continue lane.

---

## Files Changed / Created

| File | Change |
|------|--------|
| `youtube/progress.py` | New — progress persistence |
| `youtube/media_history.py` | New — unified history persistence |
| `youtube/continue_ui.py` | New — Continue lane + history + activity screens |
| `youtube/launcher.py` | Modified — lane integration, checkpoints, finalization, Up Next re-resolve |
| `media/providers/base.py` | Modified — `get_continue_metadata()` stub |
| `media/providers/youtube.py` | Modified — `get_continue_metadata()` implementation |
| `media/providers/aniwatch.py` | Modified — `get_continue_metadata()` implementation |
| `tools/media.py` | New — `media_progress()`, `media_history()` diagnostic functions |
| `tools/cli.py` | Modified — `media progress/history` subcommands |

---

## Non-Goals

- WCO continue watching (no stable identity key available from their CDN flow).
- Browser tier providers (KissCartoon Mode A/B) — no mpv duration/position data.
- Cross-device sync.
- Full playlist-level resume for YouTube (per-video resume only).
- `play_count` tracking (no UX to surface it).
