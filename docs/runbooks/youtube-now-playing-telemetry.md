# YouTube Now Playing Telemetry

## Goal

Expose useful live playback state in `NOW PLAYING (YouTube/CRT)` using mpv IPC
properties, while keeping controls responsive.

## Core Data We Can Display

1. Playback state
- mpv property: `pause`
- UI: `Playing` / `Paused`

2. Time/progress
- mpv properties: `time-pos`, `duration`
- UI: current time and total duration (`MM:SS / MM:SS`)

3. Volume + mute
- mpv properties: `volume`, `mute`
- UI: `Vol 65` and `Muted` state

4. Playlist position
- mpv properties: `playlist-pos`, `playlist-count`
- UI: `Item 3 / 24` (convert `playlist-pos` to 1-based index for display)

5. Current media title
- mpv property: `media-title`
- UI: title line (optional if already using window-title polling)

## Optional Diagnostics

- `speed` (playback speed)
- `audio-device`, `audio-codec-name`
- `video-params/w`, `video-params/h` (resolution)

These are optional and should not clutter the default screen.

## Property Scope (v1 vs v2)

### v1 (implement first)

- `pause`
- `time-pos`
- `duration`
- `volume`
- `mute`
- `playlist-pos`
- `playlist-count`
- `media-title` (optional if window-title polling remains the source)

### v2 (advanced diagnostics)

- `cache-buffering-state`
- `demuxer-cache-duration`
- `speed`
- `video-codec`
- `video-params/w`, `video-params/h`
- `container-fps` / `estimated-vf-fps`
- `audio-codec-name`
- `audio-params/channel-count`
- `audio-params/samplerate`
- `hwdec-current`

## Control Feedback Strategy

For key actions (`pause`, `seek`, `volume`, `mute`, `next`, `prev`):

1. Apply command immediately.
2. Show short transient action text (example: `Seek +10s`, `Next video`).
3. Refresh the live status from properties.

This gives quick confirmation even if property polling is delayed.

## Polling Recommendations

- Poll at moderate rate (2–4 Hz) to avoid UI lag.
- Keep per-property reads timeout-bounded.
- On `None` read, keep last known value instead of blanking the UI.
- Never block keyboard processing on telemetry refresh.

Recommended cadence:
- Core status line (v1 fields): 4 Hz (every 250ms)
- Advanced telemetry panel (`T` ON): 1 Hz (every 1000ms)

## Failure Behavior

If a property read fails:
- preserve previous displayed value
- continue playback controls normally
- log debug-level read failure (not user-facing spam)

Display formatting rule:
- If no previous value exists, render `N/A`.
- Keep field widths fixed where practical to avoid visual jitter.

## Suggested First Implementation (Minimal)

Add one compact status line with:
- `Playing/Paused`
- `time-pos / duration`
- `Vol N` + `Muted`
- `playlist index/count` when available

Keep existing menu text unchanged for v1.

## Proposed UI Layout With `T` Toggle

### `T` OFF (default)

```text
========================================
        NOW PLAYING (YouTube/CRT)
========================================
Title: Journey to the West - Ep 01
Playlist: 1 / 26

Status: Playing | 03:41 / 24:12 | Vol 65 | Mute Off | Zoom default

Playback: [Space] Pause  [<- ->] Seek  [^ v] Volume  [M] Mute  [N/P] Next/Prev
Window:   [A] Adjust      [Z] Cycle zoom
Library:  [+] Favorite    [L] Favorites [H] History  [B/J] Bookmarks
System:   [T] Telemetry   [Q] Quit
========================================
```

### `T` ON (advanced telemetry visible)

```text
========================================
        NOW PLAYING (YouTube/CRT)
========================================
Title: Journey to the West - Ep 01
Playlist: 1 / 26

Status: Playing | 03:41 / 24:12 | Vol 65 | Mute Off | Zoom default

Telemetry:
- Cache: 7.2s buffered | Buffering: no
- Video: h264 | 1920x1080 | 23.976 fps | HW: d3d11va
- Audio: aac | 2ch | 48 kHz
- IPC: duplex | get_property ~35 ms

Playback: [Space] Pause  [<- ->] Seek  [^ v] Volume  [M] Mute  [N/P] Next/Prev
Window:   [A] Adjust      [Z] Cycle zoom
Library:  [+] Favorite    [L] Favorites [H] History  [B/J] Bookmarks
System:   [T] Telemetry   [Q] Quit
========================================
```

## `T` Toggle Behavior

- Default state on launch: telemetry hidden (`T` OFF).
- Press `T` to toggle telemetry panel visibility.
- Toggled state affects display only (does not affect playback behavior).
- When telemetry reads fail, show last-known values or `N/A` without blocking controls.

## UI Acceptance Checklist

1. `T` toggles panel visibility instantly (<100ms perceived delay).
2. No key lag while telemetry is polling (playback controls remain responsive).
3. Missing properties never crash the UI; fields show last-known value or `N/A`.
4. Status line remains stable (no severe line-shifting/jitter during updates).
5. Playlist and time fields update during active playback when available.

## Must-Do Before Expansion

These items should be completed before adding broader telemetry features.

1. Event-driven updates (or strict polling boundaries)
- Reduce unnecessary polling and keep command responsiveness as top priority.

2. Rate limiting / backoff when IPC degrades
- Automatically reduce telemetry frequency under timeout/error conditions.

3. IPC health indicator
- Show explicit status in UI (`OK`, `degraded`, `reconnecting`) for easier diagnosis.

4. Persistent UI preferences
- Persist telemetry toggle/state (`T`), selected detail level, and layout mode.

5. Performance budget guardrails
- Define and enforce max IPC calls/sec and redraw frequency targets.

6. Telemetry failure/latency test harness
- Add repeatable tests for missing properties, slow IPC, and reconnect scenarios.

7. Extensibility for non-YouTube sources (design constraint)
- Keep telemetry data model source-agnostic (`source_type`, generic field names).
- Keep source-specific extraction in adapters, not in the renderer/UI layer.

## Implementation Approach (Modularized)

### Guiding structure

- `session/mpv_ipc.py`: transport only (IPC protocol + requests)
- `youtube/telemetry.py`: telemetry scheduling, backoff, health, snapshot generation
- `youtube/controls.py`: pure rendering of snapshot state
- `youtube/launcher.py`: orchestration and key handling only
- `youtube/state.py` or `youtube/ui_prefs.py`: persisted UI preferences
- `youtube/telemetry_sources/*`: source adapters (YouTube/mpv first, others later)

### Must-do mapping

1. Event-driven updates / polling boundaries
- Implement in `youtube/telemetry.py` with a single `tick(now)` path.
- Start with strict polling boundaries, then add event-driven hooks later.

2. Rate limiting / backoff
- Implement inside `youtube/telemetry.py`.
- Maintain success/failure counters and adjust poll interval dynamically.

3. IPC health indicator
- Expose `health` field in telemetry snapshot (`ok`, `degraded`, `reconnecting`).
- Render in `youtube/controls.py`; do not compute health in UI layer.

4. Persistent UI preferences
- Persist telemetry toggle/detail level/layout mode in `youtube/state.py`
  (or a dedicated `youtube/ui_prefs.py`).
- `launcher` reads/writes prefs; `controls` remains stateless.

5. Performance budget guardrails
- Define max IPC calls/sec and redraw/sec in `youtube/telemetry.py`.
- Prioritize core fields first when budget is tight.

6. Failure/latency test harness
- Add a telemetry-focused harness with a fake IPC adapter.
- Simulate timeout, `None`, slow response, reconnect.

7. Extensibility for non-YouTube sources
- Add adapter interface in `youtube/telemetry_sources/base.py`.
- Implement `youtube/telemetry_sources/mpv_source.py` first.
- Keep snapshot model source-agnostic:
  - `source_type`
  - `title`
  - `position_sec`
  - `duration_sec`
  - `queue_index`
  - `queue_count`
  - `health`

### Suggested implementation order

1. `youtube/telemetry.py` + snapshot model
2. Health + backoff logic
3. UI preference persistence
4. UI rendering updates in `youtube/controls.py`
5. Test harness for failure/latency paths
6. Source-adapter abstraction for future non-YouTube sources

## Default Values (Recommended)

Use these defaults unless runtime evidence suggests changes are needed:

- Core status poll interval: `250ms` (4 Hz)
- Advanced telemetry poll interval (`T` ON): `1000ms` (1 Hz)
- `get_property` timeout (core fields): `200ms`
- `get_property` timeout (advanced fields): `250ms`
- Max IPC calls per second budget: `20`
- Max redraw rate budget: `6` redraws/sec

Health/backoff thresholds:
- `degraded` after `3` consecutive telemetry read failures
- `reconnecting` after `6` consecutive failures
- return to `ok` after `3` consecutive successful telemetry cycles
- degraded poll interval multiplier: `2x`
- reconnect poll interval multiplier: `4x`
- reconnect attempt interval: `1000ms`

Pending/staleness behavior:
- Keep last-known telemetry values for up to `5s`
- After `5s` without refresh, show `N/A` for stale fields
- Keep fixed-width status rendering to reduce visual jitter

## UI Preferences Schema (Example)

```json
{
  "youtube_ui_prefs": {
    "show_telemetry_panel": false,
    "telemetry_level": "basic",
    "compact_mode": false
  }
}
```

## Additional Pre-Implementation Constraints

### 1) Terminal resize handling

Implement renderer safeguards in `youtube/controls.py`:

- Read terminal width on each redraw.
- Truncate long fields (title/status segments) to fit available width.
- Avoid intentional wrapping for status lines.
- If width is too small, fall back to compact rendering blocks.

Boundary rule:
- Keep resize/fit logic inside renderer only (no telemetry/IPC code here).

### 2) Thread-safety boundary for telemetry state

Use a strict ownership model:

- `youtube/telemetry.py` is the only writer of telemetry snapshot state.
- `youtube/launcher.py` and `youtube/controls.py` read snapshot copies only.
- If background tasks are introduced later:
  - guard telemetry internals with one lock in `youtube/telemetry.py`
  - publish immutable/copy snapshots to readers

Implementation rule:
- One writer, many readers, copy-on-publish.
