# Media Session Setup Guide

Setup guide for `launch_youtube.py` — YouTube and multi-site CRT playback.

---

## Prerequisites

### Required

| Tool | Min version | Purpose |
|------|-------------|---------|
| mpv | 0.35+ | Video player |
| yt-dlp | any recent | YouTube extraction (Tier 1 providers) |
| Node.js | 18+ | HiAnime resolver (`integrations/aniwatch-js`) and YouTube n-challenge JS runtime |
| Firefox | any | Cookie source for YouTube authentication (see below) |

All four must be installed before the launcher can play YouTube or HiAnime content.

### Why Node.js is required for YouTube

YouTube's bot detection uses a JavaScript challenge (`n` parameter) that yt-dlp must
solve at runtime. Without a JS runtime, yt-dlp can only see storyboard images and fails
with `Requested format is not available`. The launcher passes `--js-runtimes=node` to
yt-dlp automatically. Node.js must be on PATH.

Verify Node is reachable:
```bash
node --version
```

---

## Initial Config Setup

### 1. Verify `crt_config.json`

These keys must be set to valid paths:

```json
{
  "mpv_path":    "D:\\Emulators\\mpv\\mpv.exe",
  "yt_dlp_path": "D:\\Emulators\\yt-dlp\\yt-dlp_x86.exe"
}
```

### 2. Create `crt_config.local.json`

This file is **gitignored** — it stores credentials and user-specific paths that must not
be committed.

```bash
cp crt_config.local.json.example crt_config.local.json
```

Edit `crt_config.local.json`:

```json
{
  "youtube_cookies_from_browser": "firefox"
}
```

The file is merged on top of `crt_config.json` at startup. Only keys you set here are
overridden; everything else comes from `crt_config.json`.

### 3. Set up Firefox cookies

YouTube requires authentication cookies to bypass bot detection. The launcher reads them
from Firefox's on-disk cookie store — **Firefox does not need to be open**.

1. Open Firefox
2. Go to `youtube.com`
3. Sign in to your Google account
4. Close Firefox (optional — yt-dlp reads the file directly)

That's it. The launcher will use Firefox cookies automatically on every run.

**Why not Chrome?** Chrome 127+ (released mid-2024) encrypts its cookie database with
App-Bound Encryption, a system-level key that yt-dlp cannot access. Edge has the same
restriction. Firefox does not use this encryption.

**Cookie file alternative:** If you prefer not to use Firefox, export cookies from Chrome
using the "Get cookies.txt LOCALLY" extension, save to a stable path, and set:
```json
{ "youtube_cookies_file": "D:\\path\\to\\youtube-cookies.txt" }
```
Cookie files expire and must be re-exported periodically (typically every few weeks).

### 4. Install aniwatch npm package (for HiAnime)

```bash
cd integrations/aniwatch-js
npm install
```

This installs `aniwatch@^2.24.3` (pinned in `package.json`). Only needed for hianime.to
playback — YouTube works without it.

---

## Running the Launcher

```bash
python launch_youtube.py
```

Or with a direct URL:
```bash
python launch_youtube.py --url "https://www.youtube.com/watch?v=..."
```

---

## Troubleshooting

### `Requested format is not available`

yt-dlp solved the n-challenge but could not select a video format. Common causes:

- **Node.js not on PATH** — run `node --version` to confirm. If missing, install Node.js.
- **Cookies not set** — `crt_config.local.json` does not exist or has an empty
  `youtube_cookies_from_browser`. Create the file per the setup steps above.
- **Firefox never signed into YouTube** — open Firefox, go to youtube.com, sign in.

Check `runtime/mpv.log` for the exact yt-dlp error and the command it ran.

### `Sign in to confirm you're not a bot`

Cookies are not being passed to yt-dlp, or the Firefox cookie store is expired/empty.
Confirm `crt_config.local.json` exists with `youtube_cookies_from_browser: "firefox"` and
that Firefox has a valid YouTube session.

### `Could not copy Chrome cookie database` / `Failed to decrypt with DPAPI`

You have `youtube_cookies_from_browser` set to `chrome` or `edge`. These don't work on
Windows — see "Why not Chrome?" above. Switch to `firefox` or use a cookie file.

### `mpv exited with code 2` and window never appeared

Check `runtime/mpv.log`. The most useful sections:
- Lines with `[ytdl_hook]` — shows the exact yt-dlp command and its stdout/stderr
- Lines with `[e][...]` (error level) — the direct failure reason

### HiAnime URL not resolving

1. Confirm Node.js is on PATH: `node --version`
2. Confirm the aniwatch package is installed: `ls integrations/aniwatch-js/node_modules/aniwatch`
3. Test the resolver directly:
   ```bash
   node integrations/aniwatch-js/resolve.js "https://hianime.to/watch/show-slug?ep=12345"
   ```
   It should print a JSON object to stdout. Errors go to stderr.
4. Check that the URL is a `/watch/` URL with an `?ep=` parameter — other hianime.to
   URL formats are not supported.

### IPC degraded / all telemetry N/A

This is a separate issue from playback — the video plays but the IPC pipe failed to
connect. Check `runtime/youtube.log` for `IPC connection failed` lines. This can happen
if mpv started too slowly or if the pipe name is in use from a prior crashed session.
Wait a few seconds and retry, or restart the launcher.

---

## Log Files

| File | When to read it |
|------|----------------|
| `runtime/youtube.log` | Session events: provider selected, mpv command, exit code, IPC status |
| `runtime/mpv.log` | mpv internals: yt-dlp subprocess command, format selection, hook trace |
| `runtime/mpv_stderr.log` | Always empty on Windows (mpv is a GUI process); ignore |
