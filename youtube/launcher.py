"""Main media session orchestrator (YouTube, HiAnime, and generic URLs)."""

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
from session.window_utils import find_window, get_rect, move_window, get_window_title
from session.audio import get_current_audio_device_name, set_default_audio_best_effort
from media.browser_launcher import launch_system_browser, launch_playwright_browser

from youtube.config import (
    _MPV_PROFILE_PATH,
    _PIPE_NAME,
    apply_quality_preset,
    load_config,
    load_json,
    paste_from_clipboard,
)
from media.providers import registry as _provider_registry
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
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    # Attach to root so media.*, session.*, and youtube.* all write to the same file
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        root.addHandler(fh)
    log = logging.getLogger("youtube")
    log.setLevel(logging.DEBUG)
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


def _rect_to_text(rect: Optional[tuple[int, int, int, int]]) -> str:
    if rect is None:
        return "None"
    x, y, w, h = rect
    return f"x={x}, y={y}, w={w}, h={h}"


def _rect_matches(
    got: Optional[tuple[int, int, int, int]],
    want: tuple[int, int, int, int],
    tol: int = 2,
) -> bool:
    if got is None:
        return False
    gx, gy, gw, gh = got
    wx, wy, ww, wh = want
    return (
        abs(gx - wx) <= tol
        and abs(gy - wy) <= tol
        and abs(gw - ww) <= tol
        and abs(gh - wh) <= tol
    )


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
    watch_sec: float = 3.0,
) -> float:
    """Re-apply window + zoom state after a track/video transition."""
    if hwnd is not None:
        target = (x, y, w, h)
        before = None
        try:
            before = get_rect(hwnd)
        except Exception:
            pass
        log.info(
            "transition: reapply window start target=(%s) before=(%s)",
            _rect_to_text(target),
            _rect_to_text(before),
        )
        move_window(hwnd, x, y, w, h, strip_caption=True)
        time.sleep(0.08)
        after = None
        try:
            after = get_rect(hwnd)
        except Exception:
            pass

        if _rect_matches(after, target):
            log.info("transition: reapply window ok after=(%s)", _rect_to_text(after))
        else:
            log.warning(
                "transition: reapply window drift target=(%s) after=(%s); retrying once",
                _rect_to_text(target),
                _rect_to_text(after),
            )
            move_window(hwnd, x, y, w, h, strip_caption=True)
            time.sleep(0.12)
            after_retry = None
            try:
                after_retry = get_rect(hwnd)
            except Exception:
                pass
            if _rect_matches(after_retry, target):
                log.info("transition: reapply window retry ok after=(%s)", _rect_to_text(after_retry))
            else:
                log.error(
                    "transition: reapply window retry failed target=(%s) after=(%s)",
                    _rect_to_text(target),
                    _rect_to_text(after_retry),
                )
    else:
        log.warning("transition: reapply window skipped (hwnd is None)")

    if not ipc_connected:
        log.info("transition: ipc disconnected; zoom/pan reapply skipped")
        return time.monotonic() + max(0.5, watch_sec)

    if zoom_locked and zoom_preset_name:
        for p in load_zoom_presets():
            if p.get("name") == zoom_preset_name:
                ipc.set_property("video-zoom", p.get("zoom", 0.0))
                ipc.set_property("video-pan-x", p.get("pan_x", 0.0))
                ipc.set_property("video-pan-y", p.get("pan_y", 0.0))
                log.info("re-applied locked zoom preset on transition: %s", zoom_preset_name)
                return time.monotonic() + max(0.5, watch_sec)
        log.warning("transition: zoom lock active but preset not found: %s", zoom_preset_name)

    # Fallback: re-apply any previously-set zoom/pan values from IPC cache.
    z = ipc.get_property("video-zoom")
    px = ipc.get_property("video-pan-x")
    py = ipc.get_property("video-pan-y")
    if z is not None or px is not None or py is not None:
        ipc.set_property("video-zoom", z if z is not None else 0.0)
        ipc.set_property("video-pan-x", px if px is not None else 0.0)
        ipc.set_property("video-pan-y", py if py is not None else 0.0)
        log.info("re-applied cached zoom/pan on transition (z=%s px=%s py=%s)", z, px, py)
    else:
        log.info("transition: no cached zoom/pan values to re-apply")
    return time.monotonic() + max(0.5, watch_sec)


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


def _get_valid_hwnd(hwnd: Optional[int], pid: int) -> Optional[int]:
    """Return a valid HWND for mpv, reacquiring by PID when needed."""
    if hwnd is not None:
        try:
            get_rect(hwnd)
            return hwnd
        except Exception:
            pass

    reacquired = find_window(pid, [], [])
    if reacquired is not None:
        log.warning("transition-watch: hwnd reacquired to 0x%x", reacquired)
    return reacquired


def _mpv_exited_at_eof(log_path: str) -> bool:
    """Return True if mpv.log records a natural end-of-file exit."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            return "End of file" in f.read()
    except Exception:
        return False


def _autoplay_countdown(next_url: str, next_title: str, seconds: int = 5) -> Optional[str]:
    """Show a countdown and return next_url when the timer elapses.

    Keys accepted during the countdown:
      N       — play immediately
      C / Q / ESC — cancel autoplay

    Returns next_url to proceed, or None if cancelled.
    """
    # Drain any buffered keypresses that accumulated during playback.
    while msvcrt.kbhit():
        msvcrt.getch()

    label = next_title if next_title else next_url
    print()
    for remaining in range(seconds, 0, -1):
        print(
            f"\r  Next: {label}  —  starting in {remaining}s  "
            "[N=play now  C/Q=cancel]     ",
            end="",
            flush=True,
        )
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b"n", b"N"):
                    print()
                    return next_url
                if ch in (b"c", b"C", b"q", b"Q", b"\x1b"):
                    print("\n  Autoplay cancelled.")
                    return None
            time.sleep(0.05)
    print()
    return next_url


def run() -> int:
    parser = argparse.ArgumentParser(description="Play a YouTube URL on the CRT via mpv.")
    parser.add_argument("--url", help="YouTube URL to play")
    parser.add_argument("--quality", default="best",
                        help="Playback quality preset (default: best)")
    parser.add_argument("--queue-file", metavar="PATH",
                        help="Load queue from text/JSON file")
    parser.add_argument("--add-to-queue", metavar="URL",
                        help="Append URL to runtime/youtube_queue.json and exit")
    parser.add_argument("--browser-dry-run", action="store_true",
                        help="Show what browser launch would do without opening anything")
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
    _provider_registry.setup(cfg)
    mpv_path = cfg["mpv_path"]
    yt_dlp_path = cfg["yt_dlp_path"]
    x, y, w, h = cfg["x"], cfg["y"], cfg["w"], cfg["h"]
    audio_device_token = cfg.get("youtube_audio_device", "").strip()
    quality_presets = cfg.get("youtube_quality_presets", {})
    use_duplex_ipc = bool(cfg.get("youtube_ipc_duplex", False))
    transition_autocorrect_enabled = bool(cfg.get("youtube_transition_autocorrect_enabled", True))
    transition_watch_sec = max(0.5, float(cfg.get("youtube_transition_watch_sec", 3.0)))
    transition_max_attempts = max(0, int(cfg.get("youtube_transition_max_attempts", 6)))
    transition_cooldown_sec = max(0.05, int(cfg.get("youtube_transition_cooldown_ms", 350)) / 1000.0)
    transition_required_stable_hits = max(
        1, int(cfg.get("youtube_transition_required_stable_hits", 2))
    )
    force_final_snap_on_watch_fail = bool(cfg.get("force_final_snap_on_watch_fail", False))
    rect_guard_enabled = bool(cfg.get("youtube_rect_guard_enabled", True))
    rect_guard_interval_sec = max(2.0, float(cfg.get("youtube_rect_guard_interval_sec", 5.0)))
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
            print("Media URL, V=paste from clipboard, or Enter to resume last:")
        else:
            print("Media URL (or V to paste from clipboard):")

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

    # Resolve provider and validate URL
    provider = None
    if url:
        provider = _provider_registry.get_provider_or_generic(url)
        err = provider.validate(url)
        if err:
            log.warning("exit: invalid URL — %s", err)
            print(f"[media] {err}")
            return 1
        log.info("provider selected: %s", provider.name())

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

    if url and provider and provider.supports_title_fetch:
        print("[media] Fetching title...")
        title = provider.fetch_title(url)
        if title:
            print(f"[media] Title: {title}")
        else:
            print("[media] Could not fetch title")
            title = ""
    elif url:
        title = ""
    else:
        title = "(queue)"

    is_playlist = is_queue or (
        url is not None and provider is not None and provider.is_playlist(url)
    )
    if is_playlist and not is_queue:
        print("[media] Playlist URL detected — autoplay enabled.")

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
        resolved = {"subtitle_urls": [], "extra_headers": {}}
        log.info("queue mode: temp playlist %s (%d items)", temp_playlist, len(queue_urls))
    else:
        resolved = provider.resolve_target(url, args.quality)
        target_url = resolved["target_url"]
        # provider may have a tighter answer on is_playlist than URL inspection
        is_playlist = resolved.get("is_playlist", is_playlist)
        log.info(
            "provider=%s resolved target=%s is_playlist=%s",
            provider.name(), target_url, is_playlist,
        )

    # Tier 3: browser-backed provider — skip mpv entirely
    if not resolved.get("requires_mpv", True):
        profile_id = resolved.get("browser_profile", "")
        provider_mode = resolved.get("launch_mode", "browser")
        # Mode precedence: profile mode_override > provider launch_mode > default_mode
        bp_profiles = cfg.get("browser_playback", {}).get("profiles", {})
        mode_override = bp_profiles.get(profile_id, {}).get("mode_override", "")
        if mode_override:
            launch_mode = mode_override
        else:
            launch_mode = provider_mode or cfg.get("browser_playback", {}).get("default_mode", "browser")
        log.info("Tier 3 browser launch: mode=%s profile=%s url=%s",
                 launch_mode, profile_id, url)
        _prev_audio: Optional[str] = None
        if audio_device_token:
            _prev_audio = get_current_audio_device_name()
            set_default_audio_best_effort(audio_device_token)
        try:
            if launch_mode == "playwright":
                rc = launch_playwright_browser(url, cfg, profile_id,
                                               dry_run=args.browser_dry_run)
            else:
                rc = launch_system_browser(url, cfg, profile_id,
                                           dry_run=args.browser_dry_run)
        finally:
            if _prev_audio:
                set_default_audio_best_effort(_prev_audio)
        return rc

    # Episode nav flags (only populated for HiAnime; False/empty for everything else)
    _ep_has_next = bool(resolved.get("has_next", False))
    _ep_has_prev = bool(resolved.get("has_prev", False))
    _ep_next_url = resolved.get("next_episode_url") or ""
    _ep_prev_url = resolved.get("prev_episode_url") or ""
    _ep_next_title = resolved.get("next_episode_title") or ""

    cmd = [
        mpv_path,
        f"--input-ipc-server={_PIPE_NAME}",
        "--no-border",
        "--force-window=yes",
        "--no-keepaspect-window",
    ]

    # yt-dlp hook: queue mode always uses it (queue URLs are YouTube);
    # single-URL mode defers to the provider's uses_ytdl flag.
    if is_queue or (provider and provider.uses_ytdl):
        cmd.append(f"--script-opts=ytdl_hook-ytdl_path={yt_dlp_path}")

    # Provider-specific args (quality presets, playlist flags, --no-ytdl for Tier 2)
    if provider and not is_queue:
        cmd.extend(provider.mpv_extra_args(url, args.quality, cfg))
    elif is_queue:
        cmd = apply_quality_preset(cmd, args.quality, quality_presets)

    # Tier 2: subtitle tracks
    for sub_url in resolved.get("subtitle_urls", []):
        cmd.append(f"--sub-file={sub_url}")

    # Tier 2: HTTP headers required by the CDN
    for key, val in resolved.get("extra_headers", {}).items():
        cmd.append(f"--http-header-fields={key}: {val}")

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

    # Pre-flight: verify executables exist
    if not os.path.isfile(mpv_path):
        log.error("mpv not found at configured path: %s", mpv_path)
        print(f"[youtube] ERROR: mpv not found: {mpv_path}")
        return 1
    if not os.path.isfile(yt_dlp_path):
        log.error("yt-dlp not found at configured path: %s", yt_dlp_path)
        print(f"[youtube] ERROR: yt-dlp not found: {yt_dlp_path}")
        return 1
    log.debug("pre-flight ok: mpv=%s  yt-dlp=%s", mpv_path, yt_dlp_path)

    # Launch mpv — mpv is a GUI process on Windows so stderr isn't useful;
    # use --log-file instead so mpv writes its own internal log to disk.
    _mpv_log_path = os.path.join(_PROJECT_ROOT, "runtime", "mpv.log")
    # Force a fresh file each run so tails only show current-session events.
    with open(_mpv_log_path, "w", encoding="utf-8", errors="replace"):
        pass
    cmd.append(f"--log-file={_mpv_log_path}")
    _mpv_stderr_path = os.path.join(_PROJECT_ROOT, "runtime", "mpv_stderr.log")
    # Keep stderr file fresh per run as well.
    with open(_mpv_stderr_path, "w", encoding="utf-8", errors="replace"):
        pass
    _mpv_stderr_fh = open(_mpv_stderr_path, "w", encoding="utf-8", errors="replace")
    print("[youtube] Launching mpv...")
    log.info("launching mpv: %s", " ".join(str(c) for c in cmd))
    try:
        proc = subprocess.Popen(cmd, stderr=_mpv_stderr_fh)
    except Exception as e:
        _mpv_stderr_fh.close()
        log.exception("failed to launch mpv: %s", e)
        print(f"[youtube] Failed to launch mpv ({mpv_path}): {e}")
        if _prev_audio:
            set_default_audio_best_effort(_prev_audio)
        return 1

    log.info("mpv pid=%d  stderr -> %s", proc.pid, _mpv_stderr_path)
    try:
        print(f"[youtube] Waiting for mpv window (PID {proc.pid})...")
        hwnd = wait_for_window(proc.pid)
        if hwnd is None:
            early_rc = proc.poll()
            if early_rc is not None:
                log.warning(
                    "mpv exited early (code=%d) before window appeared — "
                    "check runtime/mpv.log for yt-dlp errors",
                    early_rc,
                )
                print(f"[youtube] mpv exited early (code={early_rc}) — check runtime/mpv.log")
            else:
                log.warning("mpv window not found within 15s (mpv still running)")
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
        _hianime_skip_to_next = False
        _hianime_skip_to_prev = False
        _last_visible_redraw: float = time.monotonic()
        _last_hidden_status_redraw: float = 0.0
        _transition_watch_active: bool = False
        _transition_watch_until: float = 0.0
        _transition_watch_target: tuple[int, int, int, int] = (x, y, w, h)
        _transition_watch_attempts: int = 0
        _transition_watch_stable_hits: int = 0
        _transition_watch_last_correct_at: float = 0.0
        _transition_watch_budget_exhausted: bool = False
        _last_rect_watch_at: float = 0.0
        _last_rect_guard_at: float = 0.0

        zoom_locked: bool = False
        zoom_preset_name: Optional[str] = None

        layout = show_now_playing(
            title,
            is_playlist,
            zoom_locked=zoom_locked,
            zoom_preset_name=zoom_preset_name,
            telemetry=last_telemetry,
            show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                changed_reasons = []

                wt = get_window_title(hwnd)
                if wt and wt != prev_win_title:
                    prev_win_title = wt
                    new_t = wt[:-6] if wt.endswith(" - mpv") else wt
                    # Ignore raw stream filenames (HLS manifests, raw video files)
                    # that mpv shows as the window title when no metadata is present.
                    _is_stream_filename = new_t.lower().endswith(
                        (".m3u8", ".m3u", ".mp4", ".ts", ".mkv", ".webm", ".mov")
                    )
                    if new_t and new_t != title and not _is_stream_filename:
                        title = new_t
                        log.info("title changed -> %r", title)
                        changed = True
                        changed_reasons.append("title")

                if is_playlist and ipc_connected:
                    pos = ipc.get_property("playlist-pos")
                    count = ipc.get_property("playlist-count")
                    new_pos = (pos + 1) if pos is not None else None
                    new_count = count
                    if new_pos != playlist_pos or new_count != playlist_count:
                        playlist_pos = new_pos
                        playlist_count = new_count
                        changed = True
                        changed_reasons.append("playlist")

                if changed:
                    log.info(
                        "transition detected reasons=%s playlist_pos=%s playlist_count=%s title=%r target_rect=x=%d,y=%d,w=%d,h=%d",
                        ",".join(changed_reasons) if changed_reasons else "unknown",
                        playlist_pos,
                        playlist_count,
                        title,
                        x, y, w, h,
                    )
                    _transition_watch_target = (x, y, w, h)
                    _transition_watch_until = _reapply_video_state(
                        hwnd, x, y, w, h,
                        ipc_connected, ipc,
                        zoom_locked, zoom_preset_name,
                        watch_sec=transition_watch_sec,
                    )
                    _transition_watch_active = True
                    _transition_watch_attempts = 0
                    _transition_watch_stable_hits = 0
                    _transition_watch_last_correct_at = 0.0
                    _transition_watch_budget_exhausted = False
                    _last_rect_watch_at = 0.0
                    if not adjust_mode and not controls_hidden:
                        layout = show_now_playing(
                            title, is_playlist, playlist_pos, playlist_count,
                            zoom_locked, zoom_preset_name,
                            telemetry=last_telemetry,
                            show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
                        )
                        status_row = layout.get("status_row")
                        status_width = layout.get("width")
                        last_status_text = layout.get("status_text")

            if _transition_watch_active and now > _transition_watch_until:
                final = None
                hwnd = _get_valid_hwnd(hwnd, proc.pid)
                if hwnd is not None:
                    try:
                        final = get_rect(hwnd)
                    except Exception:
                        final = None

                result = "failed"
                reason = "timeout_mismatch"
                target = _transition_watch_target
                if _rect_matches(final, target):
                    result = "settled"
                    reason = "timeout_stable"
                elif (
                    force_final_snap_on_watch_fail
                    and not adjust_mode
                    and hwnd is not None
                ):
                    move_window(hwnd, target[0], target[1], target[2], target[3], strip_caption=True)
                    time.sleep(0.08)
                    try:
                        final = get_rect(hwnd)
                    except Exception:
                        final = None
                    if _rect_matches(final, target):
                        result = "settled"
                        reason = "forced_final_snap"
                    else:
                        reason = "forced_final_snap_failed"
                elif _transition_watch_budget_exhausted:
                    reason = "budget_exhausted"

                log.info(
                    "transition-watch-end result=%s attempts=%d stable_hits=%d target=(%s) final=(%s) reason=%s",
                    result,
                    _transition_watch_attempts,
                    _transition_watch_stable_hits,
                    _rect_to_text(target),
                    _rect_to_text(final),
                    reason,
                )
                # Final zoom re-assert: mpv can reset video-zoom during codec
                # initialisation which may finish after the watch window opened.
                if zoom_locked and zoom_preset_name and ipc_connected:
                    for p in load_zoom_presets():
                        if p.get("name") == zoom_preset_name:
                            ipc.set_property("video-zoom",  p.get("zoom",  0.0))
                            ipc.set_property("video-pan-x", p.get("pan_x", 0.0))
                            ipc.set_property("video-pan-y", p.get("pan_y", 0.0))
                            log.info(
                                "transition-watch-end: zoom re-asserted preset=%s",
                                zoom_preset_name,
                            )
                            break
                _transition_watch_active = False
                # Force rect-guard to run immediately after watch ends.
                _last_rect_guard_at = 0.0

            if (
                _transition_watch_active
                and now <= _transition_watch_until
                and (now - _last_rect_watch_at) >= 0.35
            ):
                _last_rect_watch_at = now
                target = _transition_watch_target
                hwnd = _get_valid_hwnd(hwnd, proc.pid)
                if hwnd is None:
                    log.warning("transition-watch: hwnd_unavailable")
                else:
                    current = None
                    try:
                        current = get_rect(hwnd)
                    except Exception:
                        pass
                    if _rect_matches(current, target):
                        _transition_watch_stable_hits += 1
                        log.info(
                            "transition-watch: rect stable hit=%d/%d t+%.2fs current=(%s)",
                            _transition_watch_stable_hits,
                            transition_required_stable_hits,
                            max(0.0, _transition_watch_until - now),
                            _rect_to_text(current),
                        )
                        if _transition_watch_stable_hits >= transition_required_stable_hits:
                            log.info(
                                "transition-watch-end result=settled attempts=%d stable_hits=%d target=(%s) final=(%s) reason=stable_hits",
                                _transition_watch_attempts,
                                _transition_watch_stable_hits,
                                _rect_to_text(target),
                                _rect_to_text(current),
                            )
                            _transition_watch_active = False
                            # Force the rect-guard to run immediately after the
                            # transition settles — mpv can still drift post-codec-init.
                            _last_rect_guard_at = 0.0
                    else:
                        _transition_watch_stable_hits = 0
                        log.warning(
                            "transition-watch: late drift detected target=(%s) current=(%s)",
                            _rect_to_text(target),
                            _rect_to_text(current),
                        )
                        if not transition_autocorrect_enabled:
                            pass
                        elif adjust_mode:
                            log.info("transition-watch: autocorrect skipped (adjust mode active)")
                        elif _transition_watch_attempts >= transition_max_attempts:
                            _transition_watch_budget_exhausted = True
                            log.warning(
                                "transition-watch: autocorrect budget exhausted attempts=%d",
                                _transition_watch_attempts,
                            )
                        elif (now - _transition_watch_last_correct_at) >= transition_cooldown_sec:
                            move_window(
                                hwnd,
                                target[0],
                                target[1],
                                target[2],
                                target[3],
                                strip_caption=True,
                            )
                            _transition_watch_attempts += 1
                            _transition_watch_last_correct_at = now
                            log.warning(
                                "transition-watch: autocorrect attempt=%d target=(%s)",
                                _transition_watch_attempts,
                                _rect_to_text(target),
                            )

            # Continuous low-frequency rect + zoom guard.
            # Catches late post-transition drift that occurs after mpv finishes
            # codec initialisation (which can happen well after the title change
            # that triggered the transition watch).
            if (
                rect_guard_enabled
                and not adjust_mode
                and not _transition_watch_active
                and hwnd is not None
                and (now - _last_rect_guard_at) >= rect_guard_interval_sec
            ):
                _last_rect_guard_at = now
                target = (x, y, w, h)
                current = None
                try:
                    current = get_rect(hwnd)
                except Exception:
                    pass
                if current is not None and not _rect_matches(current, target):
                    log.warning(
                        "rect-guard: drift detected target=(%s) current=(%s); correcting",
                        _rect_to_text(target),
                        _rect_to_text(current),
                    )
                    move_window(hwnd, x, y, w, h, strip_caption=True)
                    # Rect drifted → mpv likely did a post-load reinit; re-apply zoom too.
                    if zoom_locked and zoom_preset_name and ipc_connected:
                        for p in load_zoom_presets():
                            if p.get("name") == zoom_preset_name:
                                ipc.set_property("video-zoom",  p.get("zoom",  0.0))
                                ipc.set_property("video-pan-x", p.get("pan_x", 0.0))
                                ipc.set_property("video-pan-y", p.get("pan_y", 0.0))
                                log.info(
                                    "rect-guard: zoom re-applied preset=%s",
                                    zoom_preset_name,
                                )
                                break
                else:
                    log.debug(
                        "rect-guard: ok target=(%s) current=(%s)",
                        _rect_to_text(target),
                        _rect_to_text(current),
                    )

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
                            show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                    show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                    elif _ep_has_next:
                        ipc.quit()
                        _hianime_skip_to_next = True
                        log.info("hianime: manual skip to next episode")
                        print("\n  Loading next episode...")
                        time.sleep(0.2)
                elif ch in (b"p", b"P"):
                    if is_playlist:
                        ipc.playlist_prev()
                        log.info("playlist: skipped to previous video")
                        print("\n  Previous video.")
                        time.sleep(0.2)
                    elif _ep_has_prev:
                        ipc.quit()
                        _hianime_skip_to_prev = True
                        log.info("hianime: manual skip to previous episode")
                        print("\n  Loading previous episode...")
                        time.sleep(0.2)
                elif ch in (b"a", b"A"):
                    if _transition_watch_active:
                        final = None
                        hwnd = _get_valid_hwnd(hwnd, proc.pid)
                        if hwnd is not None:
                            try:
                                final = get_rect(hwnd)
                            except Exception:
                                final = None
                        log.info(
                            "transition-watch-end result=canceled attempts=%d stable_hits=%d target=(%s) final=(%s) reason=manual_adjust",
                            _transition_watch_attempts,
                            _transition_watch_stable_hits,
                            _rect_to_text(_transition_watch_target),
                            _rect_to_text(final),
                        )
                        _transition_watch_active = False
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"r", b"R"):
                    if _transition_watch_active:
                        log.info("transition-watch: reset reason=manual_snap")
                    x, y, w, h = _snap_to_preset_crt(
                        hwnd, ipc_connected, ipc,
                        x, y, w, h,
                    )
                    _transition_watch_target = (x, y, w, h)
                    _transition_watch_until = now + transition_watch_sec
                    _transition_watch_active = True
                    _transition_watch_attempts = 0
                    _transition_watch_stable_hits = 0
                    _transition_watch_last_correct_at = 0.0
                    _transition_watch_budget_exhausted = False
                    _last_rect_watch_at = 0.0
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
                    )
                    status_row = layout.get("status_row")
                    status_width = layout.get("width")
                    last_status_text = layout.get("status_text")
                elif ch in (b"u", b"U"):
                    if _transition_watch_active:
                        log.info("transition-watch: reset reason=manual_unsnap")
                    x, y, w, h = _unsnap_to_profile_rect(
                        hwnd, ipc_connected, ipc,
                        x, y, w, h,
                    )
                    _transition_watch_target = (x, y, w, h)
                    _transition_watch_until = now + transition_watch_sec
                    _transition_watch_active = True
                    _transition_watch_attempts = 0
                    _transition_watch_stable_hits = 0
                    _transition_watch_last_correct_at = 0.0
                    _transition_watch_budget_exhausted = False
                    _last_rect_watch_at = 0.0
                    layout = show_now_playing(
                        title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name,
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
                        telemetry=last_telemetry, show_advanced_telemetry=show_telemetry_panel, episode_has_next=_ep_has_next, episode_has_prev=_ep_has_prev,
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
        _mpv_stderr_fh.close()
        rc = proc.poll()
        if rc is not None and rc != 0:
            log.warning("mpv exited with code %d", rc)
            print(f"[youtube] mpv exited with code {rc} — check runtime/mpv.log")
            # Dump last 40 lines of mpv.log (--log-file output) into the session log
            try:
                with open(_mpv_log_path, "r", encoding="utf-8", errors="replace") as _f:
                    _lines = _f.readlines()
                if _lines:
                    log.warning("mpv log tail (%d lines total):", len(_lines))
                    for _l in _lines[-40:]:
                        log.warning("  mpv| %s", _l.rstrip())
            except Exception as _e:
                log.warning("could not read mpv.log: %s", _e)
        else:
            log.info("mpv exited cleanly rc=%s", rc)

    except Exception:
        log.exception("unhandled exception in run() — mpv will be terminated")
        raise

    finally:
        try:
            _mpv_stderr_fh.close()
        except Exception:
            pass
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

    # HiAnime episode navigation: manual N/P skip OR natural EOF autoplay.
    _launch_script = os.path.join(_PROJECT_ROOT, "launch_youtube.py")
    if not _quit_flag:
        if _hianime_skip_to_next and _ep_has_next and _ep_next_url:
            # User pressed N — launch next episode immediately, no countdown.
            log.info("autoplay: manual next -> %s", _ep_next_url)
            subprocess.run([sys.executable, _launch_script, "--url", _ep_next_url])
        elif _hianime_skip_to_prev and _ep_has_prev and _ep_prev_url:
            # User pressed P — launch previous episode immediately, no countdown.
            log.info("autoplay: manual prev -> %s", _ep_prev_url)
            subprocess.run([sys.executable, _launch_script, "--url", _ep_prev_url])
        elif _ep_has_next and _ep_next_url and rc == 0 and _mpv_exited_at_eof(_mpv_log_path):
            # Natural EOF — show countdown before advancing.
            log.info("autoplay: eof eligible — next=%s", _ep_next_url)
            _play_next = _autoplay_countdown(_ep_next_url, _ep_next_title)
            if _play_next:
                log.info("autoplay: eof launching %s", _play_next)
                subprocess.run([sys.executable, _launch_script, "--url", _play_next])

    print("[youtube] Done.")
    return 0

