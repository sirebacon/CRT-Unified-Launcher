"""Main YouTube session orchestrator."""

import argparse
import logging
import msvcrt
import os
import subprocess
import sys
import time
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from session.mpv_ipc import MpvIpc
from session.window_utils import get_rect, move_window, get_window_title
from session.audio import get_current_audio_device_name, set_default_audio_best_effort

from youtube.config import (
    _MPV_PROFILE_PATH,
    _PIPE_NAME,
    apply_quality_preset,
    fetch_title,
    is_playlist_url,
    load_config,
    load_json,
    paste_from_clipboard,
    validate_youtube_url,
)
from youtube.player import wait_for_window
from youtube.player import get_preset_target_rect
from youtube.controls import (
    build_now_playing_status_text,
    clear_compact_status_line,
    show_adjust_mode,
    show_adjust_status,
    show_compact_status,
    show_now_playing,
    update_now_playing_status_line,
)
from youtube.adjust import handle_adjust_key, _STEPS
from youtube.state import (
    add_bookmark,
    add_favorite,
    add_to_history,
    get_bookmarks,
    load_favorites,
    load_history,
    load_ui_prefs,
    load_session,
    load_zoom_presets,
    save_ui_prefs,
    save_session,
)
from youtube.queue import build_temp_playlist, load_queue_file, load_saved_queue, save_queue
from youtube.telemetry import TelemetryEngine


def _setup_log() -> logging.Logger:
    log_path = os.path.join(_PROJECT_ROOT, "runtime", "youtube.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = logging.getLogger("youtube")
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S",
        ))
        log.addHandler(fh)
    return log


log = _setup_log()

_HIDE_AFTER = 5.0  # seconds before auto-hiding controls
_VISIBLE_REDRAW_SEC = 1.0
_HIDDEN_STATUS_REDRAW_SEC = 0.25
_SHOW_COMPACT_WHEN_HIDDEN = False


def _fmt_time(seconds: float) -> str:
    if seconds is None:
        return "?:??"
    s = int(seconds)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def _run_favorites_menu() -> Optional[str]:
    """Show favorites menu. Returns a URL to load, or None."""
    favs = load_favorites()
    if not favs:
        print("\n  No favorites yet. Use [+] while playing to add.")
        time.sleep(1.5)
        return None
    os.system("cls" if os.name == "nt" else "clear")
    print("=== Favorites ===")
    for i, fav in enumerate(favs, 1):
        typ = "[PL]" if fav.get("type") == "playlist" else "[VD]"
        title = fav.get("title", fav.get("url", "?"))
        print(f"  {i:2d}) {typ} {title}")
    print()
    print("  H) History   B) Back")
    print("Pick: ", end="", flush=True)
    try:
        pick = input().strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if pick.lower() == "h":
        return _run_history_menu()
    if pick.isdigit():
        idx = int(pick) - 1
        if 0 <= idx < len(favs):
            return favs[idx].get("url")
    return None


def _run_history_menu() -> Optional[str]:
    """Show recent history (last 10). Returns a URL to load, or None."""
    hist = load_history()
    if not hist:
        print("\n  No history yet.")
        time.sleep(1.5)
        return None
    recent = list(reversed(hist[-10:]))
    os.system("cls" if os.name == "nt" else "clear")
    print("=== Recent History ===")
    for i, entry in enumerate(recent, 1):
        title = entry.get("title", entry.get("url", "?"))
        print(f"  {i:2d}) {title}")
    print()
    print("  B) Back")
    print("Pick: ", end="", flush=True)
    try:
        pick = input().strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if pick.isdigit():
        idx = int(pick) - 1
        if 0 <= idx < len(recent):
            return recent[idx].get("url")
    return None


def _cycle_zoom_preset(
    zoom_locked: bool,
    zoom_preset_name: Optional[str],
    ipc_connected: bool,
    ipc: MpvIpc,
) -> tuple[bool, Optional[str], str]:
    """Cycle zoom mode in this order: Off -> preset1 -> preset2 -> ... -> Off."""
    presets = load_zoom_presets()
    order = [None] + [p.get("name") for p in presets if p.get("name")]
    if not order:
        if ipc_connected:
            ipc.reset_zoom_pan()
        return False, None, "Zoom OFF"

    current = zoom_preset_name if zoom_locked and zoom_preset_name else None
    if current not in order:
        current = None
    next_idx = (order.index(current) + 1) % len(order)
    next_name = order[next_idx]

    if next_name is None:
        if ipc_connected:
            ipc.reset_zoom_pan()
        log.info("zoom cycle -> OFF")
        return False, None, "Zoom OFF"

    if ipc_connected:
        for p in presets:
            if p.get("name") == next_name:
                ipc.set_property("video-zoom", p.get("zoom", 0.0))
                ipc.set_property("video-pan-x", p.get("pan_x", 0.0))
                ipc.set_property("video-pan-y", p.get("pan_y", 0.0))
                break
    log.info("zoom cycle -> %s", next_name)
    return True, next_name, f"Zoom ON ({next_name})"


def _reapply_video_state(
    hwnd: Optional[int],
    x: int,
    y: int,
    w: int,
    h: int,
    ipc_connected: bool,
    ipc: MpvIpc,
    zoom_locked: bool,
    zoom_preset_name: Optional[str],
) -> None:
    """Re-apply window + zoom state after a track/video transition."""
    if hwnd is not None:
        move_window(hwnd, x, y, w, h, strip_caption=True)

    if not ipc_connected:
        return

    if zoom_locked and zoom_preset_name:
        for p in load_zoom_presets():
            if p.get("name") == zoom_preset_name:
                ipc.set_property("video-zoom", p.get("zoom", 0.0))
                ipc.set_property("video-pan-x", p.get("pan_x", 0.0))
                ipc.set_property("video-pan-y", p.get("pan_y", 0.0))
                log.info("re-applied locked zoom preset on transition: %s", zoom_preset_name)
                return

    # Fallback: re-apply any previously-set zoom/pan values from IPC cache.
    z = ipc.get_property("video-zoom")
    px = ipc.get_property("video-pan-x")
    py = ipc.get_property("video-pan-y")
    if z is not None or px is not None or py is not None:
        ipc.set_property("video-zoom", z if z is not None else 0.0)
        ipc.set_property("video-pan-x", px if px is not None else 0.0)
        ipc.set_property("video-pan-y", py if py is not None else 0.0)
        log.info("re-applied cached zoom/pan on transition")


def _snap_to_preset_crt(
    hwnd: Optional[int],
    ipc_connected: bool,
    ipc: MpvIpc,
    x: int,
    y: int,
    w: int,
    h: int,
) -> tuple[int, int, int, int]:
    if hwnd is None:
        print("\n  Window not found; cannot snap.")
        time.sleep(0.8)
        return x, y, w, h

    target = get_preset_target_rect()
    if target is None:
        print("\n  Cannot read preset target rect.")
        time.sleep(0.8)
        return x, y, w, h

    x, y, w, h = target
    move_window(hwnd, x, y, w, h, strip_caption=True)
    if ipc_connected:
        ipc.reset_zoom_pan()
    print(f"\n  Snapped to preset CRT area: x={x}, y={y}, w={w}, h={h}")
    time.sleep(0.8)
    return x, y, w, h


def _unsnap_to_profile_rect(
    hwnd: Optional[int],
    ipc_connected: bool,
    ipc: MpvIpc,
    x: int,
    y: int,
    w: int,
    h: int,
) -> tuple[int, int, int, int]:
    if hwnd is None:
        print("\n  Window not found; cannot unsnap.")
        time.sleep(0.8)
        return x, y, w, h
    try:
        profile = load_json(_MPV_PROFILE_PATH)
        x, y, w, h = profile["x"], profile["y"], profile["w"], profile["h"]
    except Exception:
        print("\n  Cannot read saved profile rect.")
        time.sleep(0.8)
        return x, y, w, h

    move_window(hwnd, x, y, w, h, strip_caption=True)
    if ipc_connected:
        ipc.reset_zoom_pan()
    print(f"\n  Unsnapped to profile area: x={x}, y={y}, w={w}, h={h}")
    time.sleep(0.8)
    return x, y, w, h


def run() -> int:
    parser = argparse.ArgumentParser(description="Play a YouTube URL on the CRT via mpv.")
    parser.add_argument("--url", help="YouTube URL to play")
    parser.add_argument("--quality", default="best",
                        help="Playback quality preset (default: best)")
    parser.add_argument("--queue-file", metavar="PATH",
                        help="Load queue from text/JSON file")
    parser.add_argument("--add-to-queue", metavar="URL",
                        help="Append URL to runtime/youtube_queue.json and exit")
    args = parser.parse_args()
    log.info("=== launcher started args=%s", vars(args))

    # --add-to-queue early exit
    if args.add_to_queue:
        existing = load_saved_queue()
        existing.append(args.add_to_queue)
        save_queue(existing)
        print(f"[youtube] Added to queue: {args.add_to_queue}")
        print(f"[youtube] Queue now has {len(existing)} item(s).")
        return 0

    # Load config
    cfg = load_config()
    mpv_path = cfg["mpv_path"]
    yt_dlp_path = cfg["yt_dlp_path"]
    x, y, w, h = cfg["x"], cfg["y"], cfg["w"], cfg["h"]
    audio_device_token = cfg.get("youtube_audio_device", "").strip()
    quality_presets = cfg.get("youtube_quality_presets", {})
    use_duplex_ipc = bool(cfg.get("youtube_ipc_duplex", False))
    ui_prefs = load_ui_prefs()
    show_telemetry_panel = bool(ui_prefs.get("show_telemetry_panel", False))
    # Determine URL / queue
    url: Optional[str] = args.url
    is_queue = False
    queue_urls = []

    if args.queue_file:
        queue_urls = load_queue_file(args.queue_file)
        if not queue_urls:
            print("[youtube] Queue file is empty or could not be read.")
            return 1
        is_queue = True

    if not url and not is_queue:
        session = load_session()
        if session:
            print(f"[youtube] Last session: {session.get('title') or session['url']}")
            pos_str = _fmt_time(session.get("position_sec", 0))
            print(f"           at {pos_str}  ({session['url']})")
            print()
            print("YouTube URL, V=paste from clipboard, or Enter to resume last:")
        else:
            print("YouTube URL (or V to paste from clipboard):")

        try:
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            return 0

        if user_input.lower() == "v":
            user_input = paste_from_clipboard() or ""
            if not user_input:
                print("[youtube] Clipboard is empty or does not contain text.")
                return 1
            print(f"[youtube] Pasted: {user_input}")
        elif user_input.lower() == "r" and session:
            url = session["url"]
        elif not user_input and session:
            # Enter with no input when a last session exists → resume it
            url = session["url"]
        elif user_input:
            url = user_input

    if not url and not is_queue:
        log.info("exit: no URL provided")
        print("[youtube] No URL provided.")
        return 1

    # Validate URL
    if url:
        err = validate_youtube_url(url)
        if err:
            log.warning("exit: invalid URL — %s", err)
            print(f"[youtube] {err}")
            return 1

    # Check for session resume
    resume_to_sec: Optional[float] = None
    resume_playlist_pos: Optional[int] = None

    if url:
        session = load_session()
        if session and session.get("url") == url:
            pos_sec = session.get("position_sec", 0.0)
            pl_pos = session.get("playlist_pos", 0)
            if pos_sec and pos_sec > 5:
                pos_str = _fmt_time(pos_sec)
                print(f"[youtube] Resume from {pos_str}? [Y/N]: ", end="", flush=True)
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = "n"
                if ans == "y":
                    resume_to_sec = pos_sec
                    resume_playlist_pos = pl_pos if pl_pos else None

    # Fetch title
    log.info("=== session start url=%s", url or "(queue)")

    if url:
        print("[youtube] Fetching title...")
        title = fetch_title(yt_dlp_path, url)
        if title:
            print(f"[youtube] Title: {title}")
        else:
            print("[youtube] Could not fetch title — check yt-dlp path and network")
            title = ""
    else:
        title = "(queue)"

    is_playlist = is_queue or (url is not None and is_playlist_url(url))
    if is_playlist and not is_queue:
        print("[youtube] Playlist URL detected — autoplay enabled.")

    # Show quality info
    if args.quality and args.quality != "best":
        print(f"[youtube] Quality preset: {args.quality}")
    else:
        print(f"[youtube] Quality: best | 720p | 480p | audio  (use --quality to change)")

    # Build mpv command
    if is_queue:
        temp_playlist = build_temp_playlist(queue_urls)
        save_queue(queue_urls)
        target_url = temp_playlist
        log.info("queue mode: temp playlist %s (%d items)", temp_playlist, len(queue_urls))
    else:
        target_url = url

    cmd = [
        mpv_path,
        f"--input-ipc-server={_PIPE_NAME}",
        "--no-border",
        "--force-window=yes",
        "--no-keepaspect-window",
        f"--script-opts=ytdl_hook-ytdl_path={yt_dlp_path}",
    ]

    if is_playlist and not is_queue:
        cmd.append("--ytdl-raw-options=yes-playlist=")

    cmd = apply_quality_preset(cmd, args.quality, quality_presets)

    if resume_to_sec:
        cmd.append(f"--start={resume_to_sec:.1f}")
    if resume_playlist_pos:
        cmd.append(f"--playlist-start={resume_playlist_pos}")

    cmd.append(target_url)

    # Switch audio
    _prev_audio: Optional[str] = None
    if audio_device_token:
        _prev_audio = get_current_audio_device_name()
        set_default_audio_best_effort(audio_device_token)

    # Launch mpv
    print("[youtube] Launching mpv...")
    log.info("launching mpv: %s", " ".join(str(c) for c in cmd))
    try:
        proc = subprocess.Popen(cmd)
    except Exception as e:
        log.exception("failed to launch mpv: %s", e)
        print(f"[youtube] Failed to launch mpv ({mpv_path}): {e}")
        if _prev_audio:
            set_default_audio_best_effort(_prev_audio)
        return 1

    log.info("mpv pid=%d", proc.pid)
    try:
        print(f"[youtube] Waiting for mpv window (PID {proc.pid})...")
        hwnd = wait_for_window(proc.pid)
        if hwnd is None:
            log.warning("mpv window not found within 15s")
            print("[youtube] mpv window not found within 15s — continuing without window move.")
        else:
            log.info("mpv window hwnd=0x%x  first move to (%d,%d,%d,%d)", hwnd, x, y, w, h)
            print(f"[youtube] Window found. Moving to CRT rect ({x}, {y}, {w}x{h})...")
            move_window(hwnd, x, y, w, h, strip_caption=True)

        ipc = MpvIpc(use_duplex=use_duplex_ipc)
        ipc_connected = ipc.connect(retries=10, delay=0.5)
        if not ipc_connected:
            log.warning("IPC connection failed")
            print("[youtube] WARNING: IPC connection failed — keyboard control unavailable.")
            print("[youtube] Hint: check pipe name and mpv --input-ipc-server support.")
        else:
            log.info("IPC connected (mode=%s, requested_duplex=%s)", ipc.mode, use_duplex_ipc)
            # Re-apply rect after IPC is up: mpv can briefly override the window
            # position while it finishes initialising (loading video, codec setup).
            if hwnd is not None:
                move_window(hwnd, x, y, w, h, strip_caption=True)
                log.info("mpv window re-positioned after IPC connect")

        telemetry = TelemetryEngine(ipc, is_playlist=is_playlist)
        telemetry.set_ipc_mode(ipc.mode if ipc_connected else "offline")
        last_telemetry = telemetry.tick(
            time.monotonic(),
            show_advanced=show_telemetry_panel,
            zoom_locked=False,
            zoom_preset_name=None,
        )

        if url:
            add_to_history(url, title)

        # --- Loop state ---
        adjust_mode = False
        step_idx = 2  # default 10 px
        prev_rect = None

        prev_win_title: str = ""
        _title_check_at: float = time.monotonic() + 4.0

        playlist_pos: Optional[int] = None
        playlist_count: Optional[int] = None

        _last_keypress: float = time.monotonic()
        controls_hidden: bool = False
        _quit_flag = False
        _last_visible_redraw: float = time.monotonic()
        _last_hidden_status_redraw: float = 0.0

        zoom_locked: bool = False
        zoom_preset_name: Optional[str] = None

        layout = show_now_playing(
            title,
            is_playlist,
            zoom_locked=zoom_locked,
            zoom_preset_name=zoom_preset_name,
            telemetry=last_telemetry,
            show_advanced_telemetry=show_telemetry_panel,
        )
        status_row = layout.get("status_row")
        status_width = layout.get("width")
        last_status_text = layout.get("status_text")

        # Drain any keystrokes that accumulated in the console input buffer
        # during the loading phase (title fetch, mpv launch, IPC connect).
        # Without this, buffered keys (e.g. left-arrow) would be processed
        # immediately as player commands, causing an unintended seek/rewind.
        while msvcrt.kbhit():
            msvcrt.getch()

        # --- Main loop ---
        while proc.poll() is None and not _quit_flag:
            now = time.monotonic()
            prev_snapshot = last_telemetry
            last_telemetry = telemetry.tick(
                now,
                show_advanced=show_telemetry_panel,
                zoom_locked=zoom_locked,
                zoom_preset_name=zoom_preset_name,
            )
            telemetry_changed = last_telemetry != prev_snapshot

            # Title + playlist position poll (every 2s)
            if hwnd is not None and now >= _title_check_at:
                _title_check_at = now + 2.0
                changed = False

                wt = get_window_title(hwnd)
                if wt and wt != prev_win_title:
                    prev_win_title = wt
                    new_t = wt[:-6] if wt.endswith(" - mpv") else wt
                    if new_t and new_t != title:
                        title = new_t
                        log.info("title changed → %r", title)
                        changed = True

                if is_playlist and ipc_connected:
                    pos = ipc.get_property("playlist-pos")
                    count = ipc.get_property("playlist-count")
                    new_pos = (pos + 1) if pos is not None else None
                    new_count = count
                    if new_pos != playlist_pos or new_count != playlist_count:
                        playlist_pos = new_pos
                        playlist_count = new_count
                        changed = True

                if changed:
                    _reapply_video_state(
                        hwnd, x, y, w, h,
                        ipc_connected, ipc,
                        zoom_locked, zoom_preset_name,
                    )
                    if not adjust_mode and not controls_hidden:
                        layout = show_now_playing(
                            title, is_playlist, playlist_pos, playlist_count,
                            zoom_locked, zoom_preset_name,
                            telemetry=last_telemetry,
                            show_advanced_telemetry=show_telemetry_panel,
                        )
                        status_row = layout.get("status_row")
                        status_width = layout.get("width")
                        last_status_text = layout.get("status_text")

            # Auto-hide after inactivity
            if not adjust_mode and not controls_hidden:
                if now - _last_keypress > _HIDE_AFTER:
                    controls_hidden = True
                    if _SHOW_COMPACT_WHEN_HIDDEN:
                        show_compact_status(title, playlist_pos, playlist_count, telemetry=last_telemetry)
                        _last_hidden_status_redraw = now
                    else:
                        clear_compact_status_line()
                elif telemetry_changed:
                    new_status_text = build_now_playing_status_text(last_telemetry, zoom_preset_name)
                    line_updated = False
                    if (
                        not show_telemetry_panel
                        and status_row is not None
                        and status_width is not None
                        and new_status_text != last_status_text
                    ):
                        line_updated = update_now_playing_status_line(
                            new_status_text,
                            status_row,
                            status_width,
                        )
                        if line_updated:
                            last_status_text = new_status_text

                    if (
                        (not line_updated and (now - _last_visible_redraw) >= _VISIBLE_REDRAW_SEC)
                        or (show_telemetry_panel and (now - _last_visible_redraw) >= _VISIBLE_REDRAW_SEC)
                    ):
                        layout = show_now_playing(
                            title, is_playlist, playlist_pos, playlist_count,
                            zoom_locked, zoom_preset_name,
                            telemetry=last_telemetry,
                            show_advanced_telemetry=show_telemetry_panel,
                        )
                        status_row = layout.get("status_row")
                        status_width = layout.get("width")
                        last_status_text = layout.get("status_text")
                        _last_visible_redraw = now
            elif not adjust_mode and controls_hidden:
                # Keep the compact line alive while hidden.
                if telemetry_changed and status_row is not None and status_width is not None:
                    new_status_text = build_now_playing_status_text(last_telemetry, zoom_preset_name)
                    if new_status_text != last_status_text:
                        if update_now_playing_status_line(new_status_text, status_row, status_width):
                            last_status_text = new_status_text
                if _SHOW_COMPACT_WHEN_HIDDEN and (now - _last_hidden_status_redraw) >= _HIDDEN_STATUS_REDRAW_SEC:
                    show_compact_status(title, playlist_pos, playlist_count, telemetry=last_telemetry)
                    _last_hidden_status_redraw = now

            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue

            _last_keypress = time.monotonic()

            # Restore controls if hidden — don't consume the key, process it normally
            if controls_hidden and not adjust_mode:
                controls_hidden = False
                clear_compact_status_line()
                layout = show_now_playing(
                    title, is_playlist, playlist_pos, playlist_count,
                    zoom_locked, zoom_preset_name,
                    telemetry=last_telemetry,
                    show_advanced_telemetry=show_telemetry_panel,
                )
                status_row = layout.get("status_row")
                status_width = layout.get("width")
                last_status_text = layout.get("status_text")
                _last_visible_redraw = now

            ch = msvcrt.getch()

            # --- Adjust mode ---
            if adjust_mode:
                result = handle_adjust_key(
                    ch, hwnd, ipc_connected, ipc, title,
                    x, y, w, h, step_idx, prev_rect,
                    is_playlist, playlist_pos, playlist_count,
                    zoom_locked, zoom_preset_name,
                )
                adjust_mode = result["adjust_mode"]
                x, y, w, h = result["x"], result["y"], result["w"], result["h"]
                step_idx = result["step_idx"]
                prev_rect = result["prev_rect"]
                if result.get("quit"):
                    _quit_flag = True

            # --- Player mode ---
            else:
                if ch == b"\xe0":
                    ch2 = msvcrt.getch()
                    if ch2 == b"K":
                        ipc.seek(-10)
                        print("\n  Seek -10s.")
                        time.sleep(0.15)
                    elif ch2 == b"M":
                        ipc.seek(10)
                        print("\n  Seek +10s.")
                        time.sleep(0.15)
                    elif ch2 == b"H":
                        ipc.add_volume(5)
                        print("\n  Volume +5.")
                        time.sleep(0.15)
                    elif ch2 == b"P":
                        ipc.add_volume(-5)
                        print("\n  Volume -5.")
                        time.sleep(0.15)
                elif ch == b" ":
                    ipc.toggle_pause()
                    print("\n  Toggled pause.")
                    time.sleep(0.2)
                elif ch in (b"m", b"M"):
                    ipc.toggle_mute()
                    print("\n  Toggled mute.")
                    time.sleep(0.2)
                elif ch in (b"n", b"N"):
                    if is_playlist:
                        ipc.playlist_next()
                        log.info("playlist: skipped to next video")
                        print("\n  Next video.")
                        time.sleep(0.2)
                elif ch in (b"p", b"P"):
                    if is_playlist:
                        ipc.playlist_prev()
                        log.info("playlist: skipped to previous video")
                        print("\n  Previous video.")
                        time.sleep(0.2)
                elif ch in (b"a", b"A"):
                    adjust_mode = True
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                    show_adjust_mode(title)
                    if hwnd is not None:
                        show_adjust_status(x, y, w, h, _STEPS[step_idx])
                elif ch == b"+":
                    if url:
                        add_favorite(url, title)
                        print("\n  Added to favorites.")
                    else:
                        print("\n  No URL to save (queue mode).")
                    time.sleep(0.8)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"l", b"L"):
                    picked = _run_favorites_menu()
                    if picked:
                        print(f"  URL: {picked}")
                        print("  (Restart launch_youtube.py with this URL to play.)")
                        time.sleep(2)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"h", b"H"):
                    picked = _run_history_menu()
                    if picked:
                        print(f"  URL: {picked}")
                        print("  (Restart launch_youtube.py with this URL to play.)")
                        time.sleep(2)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"b", b"B"):
                    if ipc_connected:
                        t = ipc.get_property("time-pos")
                        if t is not None:
                            ts = _fmt_time(t)
                            print(f"\n  Bookmark name (Enter = \"{ts}\"): ", end="", flush=True)
                            try:
                                name = input().strip() or ts
                            except (EOFError, KeyboardInterrupt):
                                name = ts
                            add_bookmark(url or "", t, name)
                            log.info("bookmark saved: %s @ %.1fs", name, t)
                            print("  Bookmark saved.")
                            time.sleep(0.8)
                        else:
                            print("\n  Could not get current time.")
                            time.sleep(0.8)
                    else:
                        print("\n  IPC not connected.")
                        time.sleep(0.8)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"j", b"J"):
                    if ipc_connected:
                        marks = get_bookmarks(url or "")
                        if marks:
                            print()
                            for i, m in enumerate(marks, 1):
                                print(f"  {i}) {_fmt_time(m['time_sec'])}  {m['name']}")
                            print("  Pick number (or Enter to cancel): ", end="", flush=True)
                            try:
                                pick = input().strip()
                            except (EOFError, KeyboardInterrupt):
                                pick = ""
                            if pick.isdigit():
                                idx_ = int(pick) - 1
                                if 0 <= idx_ < len(marks):
                                    ipc.seek_absolute(marks[idx_]["time_sec"])
                                    log.info("jumped to bookmark %s", marks[idx_]["name"])
                                    print(f"  Jumped to {_fmt_time(marks[idx_]['time_sec'])}")
                                    time.sleep(0.8)
                        else:
                            print("\n  No bookmarks for this URL.")
                            time.sleep(0.8)
                    else:
                        print("\n  IPC not connected.")
                        time.sleep(0.8)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"z", b"Z"):
                    zoom_locked, zoom_preset_name, status = _cycle_zoom_preset(
                        zoom_locked, zoom_preset_name, ipc_connected, ipc
                    )
                    print(f"\n  {status}")
                    time.sleep(0.5)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"r", b"R"):
                    x, y, w, h = _snap_to_preset_crt(
                        hwnd, ipc_connected, ipc,
                        x, y, w, h,
                    )
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"u", b"U"):
                    x, y, w, h = _unsnap_to_profile_rect(
                        hwnd, ipc_connected, ipc,
                        x, y, w, h,
                    )
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"t", b"T"):
                    show_telemetry_panel = not show_telemetry_panel
                    ui_prefs["show_telemetry_panel"] = show_telemetry_panel
                    save_ui_prefs(ui_prefs)
                    print(f"\n  Telemetry {'ON' if show_telemetry_panel else 'OFF'}.")
                    time.sleep(0.2)
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"q", b"Q", b"\x1b"):
                    ipc.quit()
                    _quit_flag = True

        # Save session on exit
        if url:
            pos_sec = None
            pl_pos_0 = None
            if ipc_connected:
                pos_sec = ipc.get_property("time-pos")
                pl_pos = ipc.get_property("playlist-pos")
                pl_pos_0 = pl_pos
            save_session(url, title, is_playlist, pl_pos_0, pos_sec)
            log.info("session saved: pos=%.1fs playlist_pos=%s", pos_sec or 0, pl_pos_0)

        ipc.close()
        rc = proc.poll()
        if rc is not None and rc != 0:
            log.warning("mpv exited with code %d", rc)
            print(f"[youtube] mpv exited with code {rc} — check youtube.log")
        else:
            log.info("mpv exited cleanly rc=%s", rc)

    except Exception:
        log.exception("unhandled exception in run() — mpv will be terminated")
        raise

    finally:
        if _prev_audio:
            set_default_audio_best_effort(_prev_audio)
        if proc.poll() is None:
            log.info("terminating mpv (still running at cleanup)")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    log.info("=== session end")
    print("[youtube] Done.")
    return 0

