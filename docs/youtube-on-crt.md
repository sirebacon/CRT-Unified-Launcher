# YouTube on CRT — Design Document

## Goal

Play YouTube videos on the CRT in windowed mode using the same calibrated
rect system as emulators. The user browses YouTube on the main monitor,
copies a URL, and sends it to the CRT to play.

---

## Why Not a Browser

A browser window on the CRT was considered and rejected:

- Browsers are difficult to enforce position on (multiple processes, frequent
  self-resizing during page load and tab activity).
- Browser fullscreen on the CRT would display at the full native resolution
  with no control over the windowed rect — inconsistent with how every other
  mode works.
- The user's preferred workflow is to browse on the main monitor and send a
  URL to the CRT, not to move the browser between displays.

---

## Chosen Approach: mpv + yt-dlp

`yt-dlp` resolves the YouTube URL to a stream. `mpv` plays the stream
positioned at the CRT rect, borderless, in windowed mode — exactly like an
emulator window.

### Why This Works Well

- mpv in windowed mode respects an explicit position and size.
- mpv's OSD (progress bar, time, pause/play indicator) renders **inside** the
  video window — on the CRT, not outside it.
- `--no-keepaspect-window` keeps the window at exactly the rect we set;
  IPC zoom/pan handles content framing independently of OS window size.
- The window stays fixed after placement; no watcher loop is needed.
- No browser is involved on the CRT side at all.

### Dependencies

| Tool | Purpose | Install |
|------|---------|---------|
| `mpv` | Video player | https://mpv.io (portable build) |
| `yt-dlp` | YouTube stream resolver | `pip install yt-dlp` or standalone exe |

Paths are configured in `crt_config.json` under `mpv_path` and `yt_dlp_path`.
Defaults: `D:\Emulators\mpv\mpv.exe` and `D:\Emulators\yt-dlp\yt-dlp_x86.exe`.

---

## Workflow

```
1. Browse YouTube on main monitor.
2. Copy the video URL (single video or playlist).
3. Open CRT Station → [CINEMA] Launch YouTube.
4. Paste URL when prompted.
5. mpv opens on the CRT at the calibrated rect.
6. Control playback from the Now Playing screen (main monitor).
7. Quit → CRT Station returns to menu.
```

---

## CRT Rect

mpv uses the same rect system as emulators. The entry in `crt_presets.json`
under `emulator_rects` is:

```json
"mpv": {"x": -1211, "y": 43, "w": 1057, "h": 835}
```

The profile file `profiles/mpv-session.json` follows the same schema as
`dolphin-session.json` etc., so the preset system picks it up automatically.
Default rect: `x=-1211  y=43  w=1057  h=835`.

Calibration: press `A` in the Now Playing screen to enter Adjust mode, then
`S` to save the current position, or `R` to snap back to the preset target.

---

## Control: mpv IPC (main-monitor keyboard)

CRT Station shows a Now Playing screen on the main monitor after launch.
The user types single-key commands there; `launch_youtube.py` forwards them
to mpv via mpv's JSON IPC named pipe (`--input-ipc-server`).

### Player mode keys

```
[Space]   Pause / Resume
[← →]     Seek -10s / +10s
[↑ ↓]     Volume +5 / -5
[M]       Mute
[N]       Next video / next HiAnime episode
[P]       Previous video / prev HiAnime episode
[Z]       Cycle zoom presets (Off → default → ...)
[A]       Enter Adjust mode
[+]       Add current URL to favorites
[L]       Browse favorites menu
[H]       Watch history screen (filter Y/I/A; R<N> remove; C clear)
[K]       Mark current item as completed (drops from Continue lane immediately)
[B]       Save bookmark at current timestamp
[J]       Jump to a saved bookmark
[Q]       Quit
```

Controls auto-hide after 5 seconds of inactivity. Press any key to restore.

### Startup — Continue Watching lane

If any in-progress items exist, a **Continue Watching** lane is shown before the URL prompt.
When the lane is empty, the launcher goes straight to the URL prompt with no extra keypress.

```
Continue Watching:
  1) Super Demon Hero Wataru  [Episode 3 - ...]  → Ep 4  57%  2026-03-04
  2) Cool YouTube Video                                   40%  2026-03-03

  1-N play  R<N> remove  K<N> mark done  B<N> bookmark  U<N> up-next  H history  A activity  Enter URL prompt
```

| Key | Action |
|-----|--------|
| `1`–`N` | Play item at saved position; shows bookmark choice prompt if bookmarks exist |
| `R<N>` | Remove item from Continue lane |
| `K<N>` | Mark item completed — drops from lane, stays in history |
| `B<N>` | Bookmark picker — list bookmarks for item N, pick one to play from that time |
| `U<N>` | Up Next — play the next HiAnime episode from the beginning (HiAnime only) |
| `H` | Watch History screen |
| `A` | Recent Activity screen — merged in-progress + history sorted by recency |
| Enter | Skip to URL prompt |

### Adjust mode keys (press A to enter, A to exit)

```
Arrow keys   Move window left/right/up/down
[ / ]        Narrower / Wider
- / =        Shorter / Taller
1–9          Step size (1/5/10/25/50/100/200/500/1000 px)
[S]          Save current rect to profiles/mpv-session.json
[R]          Snap to preset CRT area + reset zoom/pan
[F]          Fill CRT height with selected content (drag picker on CRT)
[P]          Save current zoom/pan as a named preset
[C]          Clear zoom/pan (show unzoomed letterboxed video)
[Z]          Revert last R / F (also clears zoom/pan)
[A]          Back to player controls
```

---

## Content Fill (F key)

YouTube videos are 16:9. Many encode 4:3 content with pillar bars inside the
16:9 frame. The F key fills the CRT height with only the actual picture area:

1. Press F in Adjust mode.
2. The window snaps to the preset target; zoom/pan resets so the unzoomed
   letterboxed video is visible.
3. Drag a cyan rectangle around the actual picture (no encoded bars).
4. `launch_youtube.py` computes `video-zoom` and `video-pan-x/y` IPC values
   so that content fills the full window height with equal overscan on each
   horizontal side (CRT-style).
5. Press C to clear the zoom at any time. Press R to reset everything.

The OS window stays at the target size (1057×835) throughout — only mpv's
internal rendering changes. Arrow keys and size adjustments work normally
after F.

---

## Playlist Support

If the URL contains a `list=` parameter (video-in-playlist or pure playlist
URL), autoplay is enabled automatically:

- `--ytdl-raw-options=yes-playlist=` is passed to mpv so yt-dlp expands the
  full playlist.
- mpv queues and plays each video in sequence without relaunching.
- The Now Playing screen polls the mpv window title every 2 seconds and
  updates automatically when the next video starts.
- N / P keys skip forward or back in the queue.
- Zoom/pan settings persist across playlist items; press C or F to adjust for
  a specific video.

---

## Resolved Decisions

| Decision | Choice |
|----------|--------|
| Control option | Option A (IPC, main-monitor keyboard) |
| Window AR enforcement | `--no-keepaspect-window`; mpv never auto-resizes |
| Content fill | IPC `video-zoom` + `video-pan-x/y`; window stays fixed |
| Audio | mpv default audio device (unchanged) |
| Playlist | Enabled automatically when URL contains `list=` |
| Rect profile | `profiles/mpv-session.json`; managed by preset system |

---

## Files

| File | Purpose |
|------|---------|
| `launch_youtube.py` | Thin entrypoint — delegates to `youtube/launcher.py` |
| `youtube/launcher.py` | Main orchestration loop (URL prompt, mpv launch, key handling, Continue Watching integration) |
| `youtube/continue_ui.py` | Continue lane, Watch History screen, Recent Activity screen |
| `youtube/progress.py` | Continue Watching progress persistence (`media_progress.json`) |
| `youtube/media_history.py` | Unified cross-provider watch history (`media_history.json`) |
| `youtube/config.py` | Config loading, URL validation, quality presets, clipboard paste |
| `youtube/player.py` | Monitor/window helpers, preset rect, IPC fill, region picker |
| `youtube/controls.py` | Terminal display: Now Playing, Adjust mode, status lines |
| `youtube/adjust.py` | Adjust-mode key handler (extracted from main loop) |
| `youtube/state.py` | Session, favorites, history, bookmarks (JSON-backed) |
| `youtube/queue.py` | Queue file loading/saving |
| `media/providers/base.py` | Provider base class; `get_continue_metadata()` stub |
| `media/providers/youtube.py` | YouTube provider; `get_continue_metadata()` implementation |
| `media/providers/aniwatch.py` | HiAnime provider; `get_continue_metadata()` implementation |
| `session/mpv_ipc.py` | Named pipe IPC client — commands + `get_property` + `seek_absolute` |
| `session/audio.py` | Audio helpers; `get_current_audio_device_name` added |
| `session/_region_picker.py` | Subprocess tkinter overlay for content-area drag selection |
| `session/window_utils.py` | Shared Win32 helpers |
| `tools/media.py` | `crt_tools.py media progress/history` diagnostic commands |
| `profiles/mpv-session.json` | Window profile; managed by preset system |
| `crt_station.py` | `[CINEMA] Launch YouTube` menu option |
| `crt_presets.json` | `mpv` rect in each preset's `emulator_rects` |
| `crt_config.json` | `mpv_path`, `yt_dlp_path`, `youtube_audio_device`, `youtube_quality_presets`, Continue Watching knobs |
| `tools/preset.py` | `"mpv": "mpv-session.json"` in `_EMULATOR_PROFILE_FILES` |
| `runtime/youtube_session.json` | Last session state (URL, position, playlist index) |
| `runtime/youtube_favorites.json` | Saved favorites |
| `runtime/youtube_history.json` | Legacy playback history (read-only after migration) |
| `runtime/youtube_bookmarks.json` | Per-URL timestamp bookmarks |
| `runtime/youtube_queue.json` | Saved URL queue |
| `runtime/media_progress.json` | Continue Watching progress entries (capped at 40) |
| `runtime/media_history.json` | Unified cross-provider watch history (capped at 500) |

---

## Additional Features

### Audio device override

Set `youtube_audio_device` in `crt_config.json` to a device name token (e.g. `"Speakers"`)
to automatically switch the default playback device on launch and restore it on exit.
Empty string (default) means no switching.

### Quality presets

Pass `--quality <name>` to `launch_youtube.py`. Available presets defined in
`crt_config.json` under `youtube_quality_presets`: `best` (default), `720p`, `480p`, `audio`.

### Queue file

`--queue-file <path>` loads a `.txt` (one URL per line) or `.json` (list) and plays
them in sequence. `--add-to-queue <url>` appends to `runtime/youtube_queue.json` and exits.

### Resume last session

On exit, the current playback position and playlist index are saved to
`runtime/youtube_session.json`. On the next launch with the same URL, you are prompted
to resume from where you left off.

### Favorites and history

- `[+]` adds the current URL/title to `runtime/youtube_favorites.json`.
- `[L]` opens the favorites menu (numbered list; pick to see URL).
- `[H]` during playback opens the Watch History screen (filter by provider; R<N> remove;
  C clear; number to re-open URL).
- Watch history is automatically recorded on each launch to `runtime/media_history.json`
  (unified across YouTube and HiAnime); capped at 500 entries.

### Bookmarks

- `[B]` saves a named timestamp for the current URL to `runtime/youtube_bookmarks.json`.
- `[J]` shows the bookmark list; pick a number to seek to that position via IPC.
- Bookmarks integrate with the Continue lane: selecting a Continue item that has bookmarks
  prompts `1) Resume at saved position  2) Pick bookmark` before playback starts.
- `B<N>` in the Continue lane opens the bookmark picker for item N directly.

### Continue Watching

Progress is tracked automatically during playback and on exit. Items appear in the Continue
Watching lane at startup until marked complete or removed.

- Progress checkpoints every 15 seconds (configurable: `media_progress_save_interval_sec`).
- Items are marked `completed` when progress reaches the threshold (default 92%:
  `media_completion_threshold_pct`). Completed items leave the Continue lane but stay in
  Watch History.
- HiAnime items that are skipped via N/P while below threshold are marked `skipped`.
- `[K]` during playback marks the current item completed immediately without quitting.
- `runtime/media_progress.json` stores up to 40 entries (20 in-progress + 20 done).

Config knobs in `crt_config.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `media_continue_enabled` | `true` | Toggle the entire system on/off |
| `media_continue_max_items` | `20` | Max items in Continue lane |
| `media_progress_save_interval_sec` | `15` | Checkpoint interval |
| `media_completion_threshold_pct` | `92` | Percent to mark completed |

Diagnostics: `python crt_tools.py media progress` / `python crt_tools.py media history`.

See `docs/runbooks/media-history-continue-watching-plan.md` for full design notes.

## Non-Goals

- No browser on the CRT.
- No YouTube search or browse interface in CRT Station.
- No download to disk — stream only.
- No subtitle/caption support.
