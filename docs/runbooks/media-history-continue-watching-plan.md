# Media History + Continue Watching (Netflix-Style) Plan

Status: Design (not yet implemented)
Date: 2026-03-04
Scope: YouTube + HiAnime only

## Goal

Add an easy "continue watching" experience across multiple shows/videos so you can switch content and resume where you left off, per title/series, without losing place.

## Why This Is Needed

Current state is URL-centric:

- History exists (`runtime/youtube_history.json`) but does not group by show/movie.
- Session resume exists (`runtime/youtube_session.json`) but only for the last active item.
- Bookmarks exist (`runtime/youtube_bookmarks.json`) but are manual and URL-based.

This is good for one-off playback, but not for "watch several shows over time" workflow.

## Product Behavior (Target UX)

### 1) Continue Watching Lane

At media startup, show a compact "Continue Watching" list **only when in-progress items exist**. If the list is empty, skip straight to the URL prompt — no extra keypress required for the common case.

- Most recent in-progress items first.
- Each row shows: title, provider, progress percent, last watched date.
- Selecting one resumes directly at saved position (and episode for HiAnime).

### 2) Watch History (Manageable)

Keep a separate "History" screen:

- Chronological (most recent first).
- Filter by provider (`youtube`, `hianime`).
- Optional clear actions:
  - remove single item
  - clear provider history
  - clear all history

### 3) Auto-Progress Rules

Update progress during playback and on exit:

- Save checkpoint every N seconds (configurable, default 15s).
- Only write if position has moved by at least a minimum delta (avoid no-op saves while paused).
- Mark as completed when progress >= completion threshold (default 92%).
- Completed items drop out of Continue lane but stay in History.

Playback outcome classification:

- `completed`: progress >= completion threshold (e.g. 92%), regardless of whether playback ended naturally or user pressed Next near the end.
- `skipped`: user explicitly presses Next/Prev while progress is below completion threshold. **Applies to HiAnime only** — YouTube single videos have no Next/Prev action, so their outcome is always `completed` or `in_progress`.
- `in_progress`: playback exits/stops below threshold without explicit Next/Prev skip action.

Behavior by class:

- `completed` and `skipped` both leave Continue lane.
- `completed`, `skipped`, and `in_progress` are all recorded in History with their outcome.
- Only `in_progress` items are eligible for Continue Watching lane.

## Provider-Specific Resume Keys

We need a stable identity per title so resume survives URL variations.

### YouTube

- Primary id: `video_id` from URL (`v=` query or `youtu.be/<id>` path).
- Fallback id: normalized URL.
- Continue key format: `youtube:video:<video_id>`

Notes:

- Playlist URLs resolve to per-video progress entries (each video tracked independently).
- **Known limitation**: playlist position is not tracked. Resuming a playlist Continue entry resumes the last-watched video at its timestamp, but does not restore the playlist queue position. Full playlist-level resume is a future extension.

### HiAnime

- Series id: parsed from canonical episode URL path — the slug before `?ep=` (e.g. `super-demon-hero-wataru-4045`). Stable across episode changes.
- Episode id: `ep=` query parameter value.
- Continue key format:
  - series progress: `hianime:series:<series_id>`
  - episode progress entry: `hianime:episode:<episode_id>`

Resume behavior:

- Resume at the exact episode + time position.
- If episode is completed, derive the next episode dynamically at resume-time using the existing `getEpisodes` API call (by `episode_index + 1`) — do **not** cache `next_episode_url` in the progress record, as stored URLs become stale if the show's episode list changes.

## Data Model (V2 Persistence)

Add a new persistence file:

- `runtime/media_progress.json`

Schema:

```json
{
  "version": 1,
  "items": [
    {
      "continue_key": "hianime:series:super-demon-hero-wataru-4045",
      "provider": "hianime",
      "entity_type": "series",
      "title": "Super Demon Hero Wataru",
      "sub_title": "Episode 23 - Fierce Battle",
      "target_url": "https://hianime.to/watch/...",
      "resume_position_sec": 812.4,
      "duration_sec": 1420.0,
      "progress_pct": 57.2,
      "episode_url": "https://hianime.to/watch/...?ep=23",
      "episode_index": 22,
      "last_watched_at": "2026-03-04T22:10:03Z",
      "is_completed": false,
      "playback_outcome": "in_progress"
    }
  ]
}
```

Field notes:
- `playback_outcome` is the **source of truth** for item state. `is_completed` is a derived convenience field (`is_completed = playback_outcome == "completed"`). If they ever drift, `playback_outcome` wins.
- `next_episode_url` / `has_next` — not stored; derived dynamically at resume-time (staleness risk if cached).
- `play_count` — deferred to v2; not surfaced in any UX in this phase.

History stays separate:

- keep existing `runtime/youtube_history.json` for backward compatibility
- add `runtime/media_history.json` as unified cross-provider history (new writes)

## Navigation and Controls

The startup prompt adapts based on state:

- **If Continue Watching items exist:**
  - `C` — Continue Watching (show lane)
  - `H` — History
  - `U` — Enter URL
- **If no Continue items exist:**
  - Skip straight to the existing URL prompt (no gate, no extra keypress)

This means zero friction is added to the common case (fresh session or no in-progress content).

During playback:
- existing controls unchanged
- optional add: `K` — mark completed (forces item out of Continue lane immediately)

No hard dependency on telemetry panel for this feature.

## Implementation Plan

### Phase 1 — Persistence and Models

Create `youtube/progress.py`:

- load/save `media_progress.json` using atomic write (temp file + rename)
- upsert progress item by `continue_key`
- completion logic (threshold check) and pruning (cap at `media_continue_max_items`)
- continue lane query (sorted by `last_watched_at`, exclude completed)
- min-delta guard: skip write if position hasn't moved by at least 5s since last save

Create `youtube/media_history.py`:

- unified history read/write helpers
- provider filtering and delete/clear operations

### Phase 2 — Provider Identity Adapters

Add a separate `get_continue_metadata(url) -> dict` method to providers rather than
extending `resolve_target()`. This keeps playback resolution decoupled from the progress
system. Providers that don't support it return `{}`.

```python
# Provider interface addition (media/providers/base.py)
def get_continue_metadata(self, url: str) -> dict:
    """Return identity metadata for the Continue Watching system. Optional."""
    return {}
```

Implementations:

- `YouTubeProvider`: extract `video_id` from URL, set `entity_type="video"`.
- `AniwatchProvider`: extract `series_id` (slug) and `episode_index` from URL + resolver payload, set `entity_type="series"`.

Returned dict shape:

```python
{
  "continue_key": str,           # e.g. "hianime:series:naruto-123"
  "entity_type": "video" | "series",
  "series_title": str,           # optional
  "episode_title": str,          # optional
  "episode_index": int           # optional — used for next-episode derivation
}
```

### Phase 3 — Launcher Integration

Update `youtube/launcher.py`:

- conditional startup menu (only shown when continue items exist)
- call `provider.get_continue_metadata(url)` after provider resolution
- periodic progress checkpoint writes (every N seconds, with min-delta guard)
- finalize progress on exit/end-of-file
- load selected continue entry: set start URL + `--start=<resume_position_sec>` for mpv

### Phase 4 — UX and Management

- lightweight list rendering for continue/history menus
- remove/clear options in history screen
- add config knobs in `crt_config.json`:
  - `media_progress_save_interval_sec` (default 15)
  - `media_completion_threshold_pct` (default 92)
  - `media_continue_max_items` (default 20)

### Phase 5 — Migration

- no destructive migration needed
- if `youtube_history.json` exists, read-only import into unified history on first run
- dual-write to both old and new history files for approximately 2 weeks of real sessions, then drop old-only writes
- add a log line on first import so it's easy to confirm migration ran

### Phase 6 — Optional UX Enhancements (Post-Stabilization)

These are optional follow-ups after Phase 1-5 are stable in real usage.

#### 6.1 Continue Row Quick Actions

In Continue Watching lane:

- `R` — remove item from Continue lane
- `K` — mark as watched/completed
- `B` — open bookmarks picker (if bookmarks exist for that item)

Rationale:

- keeps content management in one place
- avoids extra menu hops for common actions

#### 6.2 HiAnime "Up Next" Shortcut

For HiAnime series entries:

- derive next episode at selection-time using live `getEpisodes` call + `episode_index + 1`
- show "Up Next" label in item detail row when available
- one-key action to start next episode from beginning (ignore saved timestamp)

Rationale:

- makes episodic flow faster when binge-watching
- reuses dynamic next-episode derivation model already chosen in this plan

#### 6.3 Unified "Recent Activity" View

Add a compact recent view that merges:

- in-progress Continue items
- recently completed history items

Sort by `last_watched_at` descending; include provider badge.

Rationale:

- gives one fast switchboard between YouTube and HiAnime
- avoids context switching between Continue and History menus

#### 6.4 Progress Safety Guards

Additional write guards:

- do not write progress before 30s playback position
- do not write when duration is unknown/invalid
- clamp resume position to `min(saved, duration - 10s)` to avoid resume-at-end edge cases

Rationale:

- reduces bad checkpoints from accidental opens or malformed duration reporting

#### 6.5 Bookmark-Aware Resume Choice

If bookmarks exist for selected Continue item:

- offer quick prompt:
  - `1` Resume last position
  - `2` Pick bookmark

Rationale:

- integrates existing bookmark system with Continue lane instead of parallel UX paths

#### 6.6 Diagnostics in CRT Tools

Add a lightweight debug command (example):

```powershell
python crt_tools.py session media-progress
```

Outputs:

- parsed continue keys
- provider/entity_type
- resume timestamp + progress percent
- completed/in-progress state
- last update time

Rationale:

- speeds troubleshooting when identity/resume behavior is wrong
- avoids manual JSON inspection

## Files Expected to Change

- `youtube/launcher.py`
- `youtube/state.py` (or keep untouched and add companion modules)
- `media/providers/base.py` (add `get_continue_metadata` stub)
- `media/providers/youtube.py`
- `media/providers/aniwatch.py`
- `docs/runbooks/media-setup.md` (usage updates)
- new:
  - `youtube/progress.py`
  - `youtube/media_history.py`

## Non-Goals (Initial)

- WCO continue watching (can be added later once identity stability is proven).
- Browser tier providers (KissCartoon Mode A/B).
- Cross-device sync/cloud profile sync.
- Full playlist-level resume for YouTube (per-video resume only in this phase).
- `play_count` tracking (deferred — no UX to surface it yet).

## Risks and Mitigations

- **Identity drift** (URL variants map to different entries):
  - Mitigation: provider-specific canonical IDs derived from stable slug/video_id, not raw URL.
- **Corrupt JSON on hard kill**:
  - Mitigation: atomic write pattern (write to `.tmp` then `os.replace()`).
- **Overwriting progress too aggressively** (e.g. while paused for a long time):
  - Mitigation: interval-based saves with min-delta position check — skip write if position unchanged.
- **Stale next-episode URL**:
  - Mitigation: never store `next_episode_url`; always derive next episode dynamically at resume-time using `episode_index + 1` + live `getEpisodes` call.

## Acceptance Criteria

1. YouTube:
   - start video, exit midway, reopen from Continue lane resumes near saved timestamp.
2. HiAnime:
   - start episode, switch to another show, return via Continue lane resumes same episode/time.
3. Completed items:
   - videos/episodes above threshold are removed from Continue lane but still in History.
4. Manageability:
   - user can remove one continue item and clear history from UI.
5. Backward compatibility:
   - existing playback/session/history features continue to work.
6. Zero added friction when no continue items exist:
   - launcher goes directly to URL prompt if the Continue lane is empty.
7. Skip classification:
   - pressing Next/Prev below threshold records `playback_outcome="skipped"` and does not keep the item in Continue lane.

## Suggested Rollout

1. Ship behind config flag: `media_continue_enabled` (default `true` after initial validation).
2. Validate with 5–10 real sessions across YouTube and HiAnime before considering stable.
3. Promote as default flow once resume reliability is confirmed.
4. After stabilization, selectively enable Phase 6 enhancements (start with 6.4 safety guards + 6.1 row actions).
