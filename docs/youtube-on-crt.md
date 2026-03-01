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

- mpv in windowed mode respects an explicit position and size (`--geometry`).
- mpv's OSD (progress bar, time, pause/play indicator) renders **inside** the
  video window — on the CRT, not outside it.
- Aspect ratio is handled by mpv automatically: 4:3 content fills the window,
  widescreen content is letterboxed within it.
- The window can be enforced by the same watcher logic used for emulators.
- No browser is involved on the CRT side at all.

### Dependencies

| Tool | Purpose | Install |
|------|---------|---------|
| `mpv` | Video player | https://mpv.io (portable build) |
| `yt-dlp` | YouTube stream resolver | `pip install yt-dlp` or standalone exe |

Both need to be on PATH or have their paths configured in `crt_config.json`.

---

## Workflow

```
1. Browse YouTube on main monitor.
2. Copy the video URL.
3. Open CRT Station → [YouTube] option.
4. Paste URL when prompted.
5. mpv opens on the CRT at the calibrated rect.
6. Control playback (see Control Options below).
7. Quit → CRT Station returns to menu.
```

---

## CRT Rect

mpv uses the same rect system as emulators. A dedicated entry would be added
to `crt_presets.json` under `emulator_rects`:

```json
"mpv": {"x": -1218, "y": 43, "w": 1066, "h": 835}
```

This is calibrated the same way as other emulators via
`python crt_tools.py calibrate adjust`.

A profile file `profiles/mpv-session.json` would follow the same schema as
`dolphin-session.json` etc., so the preset system picks it up automatically.

---

## Control Options

Two options depending on physical setup. **One must be chosen before
implementation.**

### Option A — mpv IPC (Recommended for TV/distance use)

CRT Station shows a "Now Playing" screen on the main monitor after launch.
The user types single-key commands there; CRT Station forwards them to mpv
via mpv's JSON IPC socket (`--input-ipc-server`).

```
Now playing: <title>
[Space]  Pause / Resume
[←/→]   Seek -10s / +10s
[↑/↓]   Volume up / down
[M]      Mute
[Q]      Quit
```

Pros: user never needs to touch the CRT side, full control from main monitor.
Cons: slightly more implementation complexity (IPC socket handling).

### Option B — Direct mpv window interaction

mpv launches normally. The user moves their mouse to the CRT to interact with
the mpv window directly. mpv's OSD appears on the CRT on hover/keypress.

Pros: zero extra code, standard mpv behaviour.
Cons: requires the user to physically reach the CRT display with the mouse.

---

## Resolved Decisions

- **Control option**: Option A (IPC, main-monitor control) implemented.
  `session/mpv_ipc.py` is a thin named pipe client; `launch_youtube.py`
  shows a Now Playing screen with keyboard controls using `msvcrt`.
- **Paths**: `mpv_path` and `yt_dlp_path` in `crt_config.json`.
  Defaults: `D:\Emulators\mpv\mpv.exe` and `D:\Emulators\yt-dlp\yt-dlp_x86.exe`.
- **Audio**: mpv plays through the system default audio device (unchanged).
- **Enforcement**: Single initial move only — mpv does not self-resize.
- **Queue / repeat**: Single video per session (v1).

---

## Files

| File | Status | Purpose |
|------|--------|---------|
| `session/mpv_ipc.py` | Created | Thin write-only named pipe IPC client |
| `profiles/mpv-session.json` | Created | Window profile (same schema as emulators) |
| `launch_youtube.py` | Created | Orchestrator: URL prompt, mpv launch, IPC control loop |
| `crt_station.py` | Modified | Added option 4 `[CINEMA] Launch YouTube` |
| `crt_presets.json` | Modified | Added `mpv` rect to each preset's `emulator_rects` |
| `crt_config.json` | Modified | Added `mpv_path` and `yt_dlp_path` keys |
| `tools/preset.py` | Modified | Added `"mpv": "mpv-session.json"` to `_EMULATOR_PROFILE_FILES` |

---

## Non-Goals (v1)

- No browser on the CRT.
- No YouTube search or browse interface in CRT Station.
- No download to disk — stream only.
- No subtitle/caption support.
