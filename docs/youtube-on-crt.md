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
[N]       Next video in playlist  (playlist URLs only)
[P]       Previous video in playlist  (playlist URLs only)
[A]       Enter Adjust mode
[+]       Add current URL to favorites
[L]       Browse favorites menu
[H]       Recent history menu
[B]       Save bookmark at current timestamp
[J]       Jump to a saved bookmark
[Q]       Quit
```

Controls auto-hide after 5 seconds of inactivity. Press any key to restore.

### Adjust mode keys (press A to enter, A to exit)

```
Arrow keys   Move window left/right/up/down
[ / ]        Narrower / Wider
- / =        Shorter / Taller
1–9          Step size (1/5/10/25/50/100/200/500/1000 px)
[S]          Save current rect to profiles/mpv-session.json
[R]          Snap to preset CRT area + reset zoom/pan
[F]          Fill CRT height with selected content (drag picker on CRT)
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
| `youtube/launcher.py` | Main orchestration loop (URL prompt, mpv launch, key handling) |
| `youtube/config.py` | Config loading, URL validation, quality presets, clipboard paste |
| `youtube/player.py` | Monitor/window helpers, preset rect, IPC fill, region picker |
| `youtube/controls.py` | Terminal display: Now Playing, Adjust mode, status lines |
| `youtube/adjust.py` | Adjust-mode key handler (extracted from main loop) |
| `youtube/state.py` | Session, favorites, history, bookmarks (JSON-backed) |
| `youtube/queue.py` | Queue file loading/saving |
| `session/mpv_ipc.py` | Named pipe IPC client — commands + `get_property` + `seek_absolute` |
| `session/audio.py` | Audio helpers; `get_current_audio_device_name` added |
| `session/_region_picker.py` | Subprocess tkinter overlay for content-area drag selection |
| `session/window_utils.py` | Shared Win32 helpers |
| `profiles/mpv-session.json` | Window profile; managed by preset system |
| `crt_station.py` | `[CINEMA] Launch YouTube` menu option |
| `crt_presets.json` | `mpv` rect in each preset's `emulator_rects` |
| `crt_config.json` | `mpv_path`, `yt_dlp_path`, `youtube_audio_device`, `youtube_quality_presets` |
| `tools/preset.py` | `"mpv": "mpv-session.json"` in `_EMULATOR_PROFILE_FILES` |
| `runtime/youtube_session.json` | Last session state (URL, position, playlist index) |
| `runtime/youtube_favorites.json` | Saved favorites |
| `runtime/youtube_history.json` | Playback history (capped at 200) |
| `runtime/youtube_bookmarks.json` | Per-URL timestamp bookmarks |
| `runtime/youtube_queue.json` | Saved URL queue |

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
- `[H]` shows the last 10 history entries.
- History is automatically recorded on each launch; capped at 200 entries.

### Bookmarks

- `[B]` saves a named timestamp for the current URL to `runtime/youtube_bookmarks.json`.
- `[J]` shows the bookmark list; pick a number to seek to that position via IPC.

## Non-Goals

- No browser on the CRT.
- No YouTube search or browse interface in CRT Station.
- No download to disk — stream only.
- No subtitle/caption support.
