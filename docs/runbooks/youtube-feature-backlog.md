# YouTube Mode Feature Backlog

## Goal

Track high-value follow-up features for `launch_youtube.py`.

---

## Completed

| Feature | Notes |
|---------|-------|
| mpv + yt-dlp core | Single video playback via IPC named pipe |
| Adjust mode | Arrow keys, size, step, save (S), snap (R), revert (Z) |
| Content fill (F) | IPC `video-zoom` + `video-pan-x/y`; window stays fixed at target |
| Clear zoom/pan (C) | Resets to unzoomed letterboxed view |
| `--no-keepaspect-window` | Prevents mpv auto-resize; window obeys all adjustments |
| Playlist autoplay | `list=` URL detection + `--ytdl-raw-options=yes-playlist=` |
| Playlist title tracking | Polls mpv window title every 2s; Now Playing auto-updates |
| N / P keys | `playlist-next` / `playlist-prev` IPC; shown only for playlist URLs |
| 1) Modularization | `launch_youtube.py` → thin entrypoint; logic in `youtube/` package |
| 2) Playlist index display | `[3 / 12]` via IPC `playlist-pos` + `playlist-count` |
| 3) Audio device override | `youtube_audio_device` in config; auto-restore on exit |
| 4) Queue file support | `--queue-file`, `--add-to-queue`; temp playlist in `runtime/` |
| 5) Resume last session | Session saved to `runtime/youtube_session.json`; resume prompt on relaunch |
| 6) Clipboard paste + URL validation | `V` at URL prompt; host whitelist validation |
| 7) Crash-safe cleanup | `finally` always restores audio + terminates mpv; better error messages |
| 8) Quality/profile presets | `--quality` arg; `youtube_quality_presets` in `crt_config.json` |
| 9) History + favorites | `[+]` `[L]` `[H]` keys; JSON in `runtime/` |
| 10) Per-video bookmarks | `[B]` save, `[J]` jump; `runtime/youtube_bookmarks.json` |
| 11) Auto-hide status | 5s inactivity → compact status line; any key restores full controls |
| 12) Multi-provider media layer | `media/providers/` registry; YouTube (Tier 1), HiAnime/WCO (Tier 2), KissCartoon (Tier 3 browser) |
| 13) Continue Watching (Phases 1–5) | `youtube/progress.py` + `media_history.py`; lane at startup; periodic checkpoints; K key; finalization on exit |
| 14) Continue Watching (Phase 6) | B<N> bookmark picker; U<N> up-next for HiAnime; A=recent activity screen; bookmark-aware resume prompt; `crt_tools.py media progress/history` |

---

## Implementation Guidance

- Keep "manual where fragile, automate where stable."
- Prefer additive toggles over behavior changes that could break current flow.
- Preserve current keyboard controls and terminal UX as defaults.
