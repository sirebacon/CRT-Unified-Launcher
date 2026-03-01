"""YouTube on CRT — launch mpv with yt-dlp and control via IPC."""

import argparse
import json
import logging
import math
import msvcrt
import os
import subprocess
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_CRT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "crt_config.json")
_MPV_PROFILE_PATH = os.path.join(_PROJECT_ROOT, "profiles", "mpv-session.json")
_PRESETS_PATH = os.path.join(_PROJECT_ROOT, "crt_presets.json")
_PIPE_NAME = r'\\.\pipe\crt-mpv-ipc'
_LOG_PATH = os.path.join(_PROJECT_ROOT, "runtime", "youtube.log")


def _setup_log() -> logging.Logger:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    log = logging.getLogger("youtube")
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        fh = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S",
        ))
        log.addHandler(fh)
    return log


log = _setup_log()

sys.path.insert(0, _PROJECT_ROOT)
import ctypes
import ctypes.wintypes
from session.window_utils import find_window, get_rect, move_window
from session.mpv_ipc import MpvIpc

# Use ctypes directly for monitor APIs — win32gui doesn't consistently expose
# MonitorFromWindow or GetMonitorInfo across all pywin32 installs.
# HMONITOR is a pointer-sized handle; restype must be c_void_p to avoid
# 32-bit truncation on 64-bit Windows.
_MonitorFromWindow = ctypes.windll.user32.MonitorFromWindow
_MonitorFromWindow.restype = ctypes.c_void_p

_MONITOR_DEFAULTTONEAREST = 2  # win32con.MONITOR_DEFAULTTONEAREST


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_int),
        ("top",    ctypes.c_int),
        ("right",  ctypes.c_int),
        ("bottom", ctypes.c_int),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",    ctypes.c_uint),
        ("rcMonitor", _RECT),
        ("rcWork",    _RECT),
        ("dwFlags",   ctypes.c_uint),
    ]


_GetMonitorInfoW = ctypes.windll.user32.GetMonitorInfoW
_GetMonitorInfoW.restype = ctypes.c_bool


def _get_monitor_bounds(hwnd: int):
    """Return (left, top, right, bottom) of the monitor containing hwnd, or None."""
    try:
        monitor = _MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        if not monitor:
            log.warning("MonitorFromWindow returned NULL for hwnd=0x%x", hwnd)
            return None
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _GetMonitorInfoW(monitor, ctypes.byref(mi)):
            log.warning("GetMonitorInfoW failed for hwnd=0x%x", hwnd)
            return None
        r = mi.rcMonitor
        return (r.left, r.top, r.right, r.bottom)
    except Exception as e:
        log.exception("_get_monitor_bounds failed for hwnd=0x%x: %s", hwnd, e)
        return None


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_config():
    """Load mpv_path, yt_dlp_path, and window rect from config files.

    Returns (mpv_path, yt_dlp_path, x, y, w, h).
    """
    try:
        cfg = _load_json(_CRT_CONFIG_PATH)
    except Exception as e:
        print(f"[youtube] Cannot read crt_config.json: {e}")
        sys.exit(1)

    mpv_path = cfg.get("mpv_path", "mpv")
    yt_dlp_path = cfg.get("yt_dlp_path", "yt-dlp")

    try:
        profile = _load_json(_MPV_PROFILE_PATH)
        x, y, w, h = profile["x"], profile["y"], profile["w"], profile["h"]
    except Exception as e:
        print(f"[youtube] Cannot read profiles/mpv-session.json: {e}")
        sys.exit(1)

    return mpv_path, yt_dlp_path, x, y, w, h


def _fetch_title(yt_dlp_path: str, url: str) -> str:
    """Fetch video title via yt-dlp. Returns title string or empty string on failure."""
    try:
        result = subprocess.run(
            [yt_dlp_path, "--get-title", "--no-playlist", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _wait_for_window(pid: int, timeout: float = 15.0):
    """Poll for mpv window by PID. Returns HWND or None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = find_window(pid, [], [])
        if hwnd is not None:
            return hwnd
        time.sleep(0.5)
    return None


def _show_now_playing(title: str) -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
    print("========================================")
    print("        NOW PLAYING (YouTube/CRT)")
    print("========================================")
    if title:
        print(f"  {title}")
        print()
    print("  [Space]   Pause / Resume")
    print("  [<- ->]   Seek -10s / +10s")
    print("  [^ v]     Volume +5 / -5")
    print("  [M]       Mute")
    print("  [A]       Adjust window position/size")
    print("  [Q]       Quit")
    print("========================================")
    print()


def _show_adjust_mode(title: str) -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
    print("========================================")
    print("        ADJUST WINDOW (YouTube/CRT)")
    print("========================================")
    if title:
        print(f"  {title}")
        print()
    print("  Arrow keys   Move left/right/up/down")
    print("  [ / ]        Narrower / Wider")
    print("  - / =        Shorter / Taller")
    print("  1 - 9        Step size (1/5/10/25/50/100/200/500/1000 px)")
    print("  [S]          Save rect to profile")
    print("  [R]          Snap to preset CRT area (clears zoom/pan)")
    print("  [F]          Fill CRT with content via zoom (drag to pick on CRT)")
    print("  [C]          Clear zoom/pan (show unzoomed video)")
    print("  [Z]          Revert last R / F (also clears zoom/pan)")
    print("  [A]          Back to player controls")
    print("========================================")


def _show_adjust_status(x: int, y: int, w: int, h: int, step: int) -> None:
    print(
        f"\r  x={x:6d}  y={y:6d}  w={w:6d}  h={h:6d}  step={step:4d}px    ",
        end="",
        flush=True,
    )


def _save_rect_to_profile(x: int, y: int, w: int, h: int) -> bool:
    """Write x/y/w/h back to profiles/mpv-session.json. Returns True on success."""
    try:
        with open(_MPV_PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)
        profile["x"] = x
        profile["y"] = y
        profile["w"] = w
        profile["h"] = h
        with open(_MPV_PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
            f.write("\n")
        return True
    except Exception as e:
        print(f"\n[youtube] Could not save profile: {e}")
        return False


def _clamp_to_monitor(hwnd: int, x: int, y: int, w: int, h: int):
    """Clamp window rect so it stays fully within the monitor it is on."""
    bounds = _get_monitor_bounds(hwnd)
    if bounds is None:
        return x, y, w, h
    ml, mt, mr, mb = bounds
    w = min(w, mr - ml)
    h = min(h, mb - mt)
    x = max(ml, min(x, mr - w))
    y = max(mt, min(y, mb - h))
    return x, y, w, h


def _do_move(hwnd: int, x: int, y: int, w: int, h: int, step: int) -> tuple:
    """Move window and redraw the status line. Returns the applied (x, y, w, h)."""
    move_window(hwnd, x, y, w, h, strip_caption=True)
    _show_adjust_status(x, y, w, h, step)
    return x, y, w, h


def _get_preset_target_rect():
    """Derive the usable CRT target rect from the active preset.

    Takes the intersection of all emulator_rects in the active preset —
    the area that every emulator has been confirmed to display within.

    Returns (x, y, w, h) or None on failure.
    """
    try:
        data = _load_json(_PRESETS_PATH)
        active = data.get("active", "")
        preset = data.get("presets", {}).get(active, {})
        rects = preset.get("emulator_rects", {})
        if not rects:
            log.warning("preset '%s' has no emulator_rects", active)
            return None
        lefts   = [r["x"]           for r in rects.values()]
        tops    = [r["y"]           for r in rects.values()]
        rights  = [r["x"] + r["w"] for r in rects.values()]
        bottoms = [r["y"] + r["h"] for r in rects.values()]
        x = max(lefts)
        y = max(tops)
        w = min(rights)  - x
        h = min(bottoms) - y
        if w <= 0 or h <= 0:
            log.warning("preset '%s' intersection is empty", active)
            return None
        log.info("preset target rect: x=%d y=%d w=%d h=%d (preset '%s')", x, y, w, h, active)
        return (x, y, w, h)
    except Exception as e:
        log.exception("_get_preset_target_rect failed: %s", e)
        return None


def _pick_content_area(hwnd_ref: int):
    """Single-step drag-to-select overlay on the CRT monitor.

    Runs the picker in a subprocess to keep its tkinter event loop fully
    isolated from this process's keyboard loop.

    The user drags a cyan rectangle around the actual video content (no
    black bars). The target CRT area is derived automatically from the
    active preset via _get_preset_target_rect().

    Returns (cx, cy, cw, ch) or None if cancelled/error.
    """
    log.info("picker: starting (hwnd_ref=0x%x)", hwnd_ref)

    bounds = _get_monitor_bounds(hwnd_ref)
    if bounds is None:
        log.error("picker: cannot read monitor bounds")
        print("\n[youtube] Cannot read monitor bounds.")
        return None
    ml, mt, mr, mb = bounds
    log.info("picker: monitor bounds ml=%d mt=%d mr=%d mb=%d", ml, mt, mr, mb)

    picker = os.path.join(_PROJECT_ROOT, "session", "_region_picker.py")
    if not os.path.exists(picker):
        log.error("picker: script missing at %s", picker)
        print(f"\n[youtube] Picker script missing: {picker}")
        return None

    cmd = [sys.executable, picker, str(ml), str(mt), str(mr), str(mb), _LOG_PATH]
    log.info("picker: launching subprocess: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log.info("picker: subprocess exited rc=%d", proc.returncode)
        if proc.stderr.strip():
            log.debug("picker: stderr=%r", proc.stderr.strip())
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            content = tuple(data["content"])
            log.info("picker: content=%s", content)
            return content
        log.info("picker: no result (cancelled or error)")
    except subprocess.TimeoutExpired:
        log.error("picker: subprocess timed out")
        print("\n[youtube] Region picker timed out.")
    except Exception as e:
        log.exception("picker: unexpected error: %s", e)
        print(f"\n[youtube] Region picker error: {e}")

    return None


def _compute_ipc_fill(hwnd: int, content_rect: tuple) -> tuple:
    """Compute mpv IPC zoom+pan to fill the window height with the selected content.

    Assumes the window is already at the target display rect.  Assumes 16:9
    video (standard for YouTube); the calculation degrades gracefully for
    other aspect ratios (slight vertical pan offset at most).

    Returns (zoom, pan_x, pan_y) for the video-zoom / video-pan-x /
    video-pan-y IPC properties.  zoom is mpv's log-base-2 scale (actual
    scale factor = 2**zoom).

    How it works
    ------------
    mpv letterboxes the video within the window.  For a 16:9 video in a
    window narrower than 16:9, the video is width-fitted with black bars at
    the top and bottom.  We compute:
      scale = window_h / content_h          (fills height exactly)
      zoom  = log2(scale)
    Then we pan so that the content centre aligns with the window centre.
    Since scale = window_h / content_h, the scaled content fills the full
    window height, so centering vertically puts content_top at window_top.
    Horizontally the scaled content may be slightly wider than the window
    (CRT overscan) — equal amounts are hidden on each side.
    """
    wx, wy, ww, wh = get_rect(hwnd)
    cx, cy, cw, ch = content_rect

    if ch <= 0 or cw <= 0 or ww <= 0 or wh <= 0:
        return 0.0, 0.0, 0.0

    # Letterbox geometry — assumes 16:9 video (standard for YouTube).
    VIDEO_AR = 16.0 / 9.0
    if ww / wh < VIDEO_AR:
        # Width-fitted: video spans the full window width, bars top/bottom.
        video_w = float(ww)
        video_h = ww / VIDEO_AR
        bar_x, bar_y = 0.0, (wh - video_h) / 2.0
    else:
        # Height-fitted: video spans the full window height, bars left/right.
        video_h = float(wh)
        video_w = wh * VIDEO_AR
        bar_x, bar_y = (ww - video_w) / 2.0, 0.0

    # Content position in rendered-video coords (origin = video top-left).
    cx_vid = (cx - wx) - bar_x
    cy_vid = (cy - wy) - bar_y

    # Uniform scale so content height fills the window height exactly.
    scale = wh / ch
    zoom = math.log2(scale)

    # Zoomed video dimensions (after applying the scale factor).
    zvw = video_w * scale
    zvh = video_h * scale

    # Content centre in the zoomed video.
    cvx = (cx_vid + cw / 2.0) * scale
    cvy = (cy_vid + ch / 2.0) * scale

    # Pan to place the content centre at the window centre.
    # mpv pan unit = fraction of window dimension.
    # Negative pan shifts viewport toward top-left (showing bottom-right video).
    pan_x = (cvx - zvw / 2.0) / ww
    pan_y = (cvy - zvh / 2.0) / wh

    log.info(
        "IPC fill: ww=%d wh=%d video_disp=%.0fx%.0f "
        "bar_x=%.0f bar_y=%.0f scale=%.3f zoom=%.3f pan_x=%.3f pan_y=%.3f",
        ww, wh, video_w, video_h, bar_x, bar_y, scale, zoom, pan_x, pan_y,
    )
    return zoom, pan_x, pan_y


def main() -> int:
    parser = argparse.ArgumentParser(description="Play a YouTube URL on the CRT via mpv.")
    parser.add_argument("--url", help="YouTube URL to play")
    args = parser.parse_args()

    url = args.url
    if not url:
        try:
            url = input("YouTube URL: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0

    if not url:
        print("[youtube] No URL provided.")
        return 1

    log.info("=== session start url=%s", url)
    mpv_path, yt_dlp_path, x, y, w, h = _load_config()
    log.info("config: mpv=%s yt_dlp=%s rect=(%d,%d,%d,%d)", mpv_path, yt_dlp_path, x, y, w, h)

    print("[youtube] Fetching title...")
    title = _fetch_title(yt_dlp_path, url)
    if title:
        print(f"[youtube] Title: {title}")
    log.info("title: %r", title)

    cmd = [
        mpv_path,
        f"--input-ipc-server={_PIPE_NAME}",
        "--no-border",
        "--force-window=yes",
        "--no-keepaspect-window",   # prevent mpv from auto-resizing on external SetWindowPos
        f"--script-opts=ytdl_hook-ytdl_path={yt_dlp_path}",
        url,
    ]

    print("[youtube] Launching mpv...")
    log.info("launching mpv: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd)
    except Exception as e:
        log.exception("failed to launch mpv: %s", e)
        print(f"[youtube] Failed to launch mpv: {e}")
        return 1

    log.info("mpv pid=%d", proc.pid)
    try:
        print(f"[youtube] Waiting for mpv window (PID {proc.pid})...")
        hwnd = _wait_for_window(proc.pid)
        if hwnd is None:
            log.warning("mpv window not found within 15s")
            print("[youtube] mpv window not found within 15s — continuing without window move.")
        else:
            log.info("mpv window hwnd=0x%x  moving to (%d,%d,%d,%d)", hwnd, x, y, w, h)
            print(f"[youtube] Window found. Moving to CRT rect ({x}, {y}, {w}x{h})...")
            move_window(hwnd, x, y, w, h, strip_caption=True)

        ipc = MpvIpc()
        ipc_connected = ipc.connect(retries=10, delay=0.5)
        if not ipc_connected:
            log.warning("IPC connection failed")
            print("[youtube] WARNING: IPC connection failed — keyboard control unavailable.")
        else:
            log.info("IPC connected")

        _show_now_playing(title)

        _STEPS = [1, 5, 10, 25, 50, 100, 200, 500, 1000]
        adjust_mode = False
        step_idx = 2  # default 10 px
        prev_rect = None  # saved before last R fit, restored with Z

        while proc.poll() is None:
            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue
            ch = msvcrt.getch()

            # --- Adjust mode ---
            if adjust_mode:
                if ch == b"\xe0":
                    ch2 = msvcrt.getch()
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        step = _STEPS[step_idx]
                        if ch2 == b"H":    y -= step          # up
                        elif ch2 == b"P":  y += step          # down
                        elif ch2 == b"K":  x -= step          # left
                        elif ch2 == b"M":  x += step          # right
                        else:
                            continue
                        x, y, w, h = _do_move(hwnd, x, y, w, h, step)
                elif ch == b"[":
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        x, y, w, h = _do_move(hwnd, x, y, max(1, w - _STEPS[step_idx]), h, _STEPS[step_idx])
                elif ch == b"]":
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        x, y, w, h = _do_move(hwnd, x, y, w + _STEPS[step_idx], h, _STEPS[step_idx])
                elif ch == b"-":
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        x, y, w, h = _do_move(hwnd, x, y, w, max(1, h - _STEPS[step_idx]), _STEPS[step_idx])
                elif ch in (b"=", b"+"):
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        x, y, w, h = _do_move(hwnd, x, y, w, h + _STEPS[step_idx], _STEPS[step_idx])
                elif ch in b"123456789":
                    step_idx = int(ch) - 1
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        _show_adjust_status(x, y, w, h, _STEPS[step_idx])
                elif ch in (b"s", b"S"):
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                        if _save_rect_to_profile(x, y, w, h):
                            print(f"\n  Saved: x={x}, y={y}, w={w}, h={h}")
                        _show_adjust_status(x, y, w, h, _STEPS[step_idx])
                elif ch in (b"r", b"R"):
                    if hwnd is not None:
                      try:
                        log.info("R pressed: snapping to preset target (hwnd=0x%x)", hwnd)
                        target_r = _get_preset_target_rect()
                        if target_r is None:
                            print("\n  Cannot read preset target rect — check crt_presets.json.")
                            time.sleep(2)
                        else:
                            tx, ty, tw, th = target_r
                            prev_rect = get_rect(hwnd)  # save for Z revert
                            move_window(hwnd, tx, ty, tw, th, strip_caption=True)
                            x, y, w, h = tx, ty, tw, th
                            if ipc_connected:
                                ipc.reset_zoom_pan()
                            log.info("R: snapped to (%d,%d,%d,%d) zoom/pan reset", x, y, w, h)
                            print(f"\n  Snapped to preset: x={x}, y={y}, w={w}, h={h}")
                        time.sleep(1.0)
                        _show_adjust_mode(title)
                        if hwnd is not None:
                            _show_adjust_status(x, y, w, h, _STEPS[step_idx])
                      except Exception as _e:
                        log.exception("R handler error: %s", _e)
                        print(f"\n  [error] {_e}")
                        time.sleep(2)
                        _show_adjust_mode(title)
                elif ch in (b"f", b"F"):
                    if hwnd is not None:
                      try:
                        log.info("F pressed: IPC fill (hwnd=0x%x)", hwnd)
                        target_r = _get_preset_target_rect()
                        if target_r is None:
                            print("\n  Cannot read preset target rect.")
                            time.sleep(2)
                        else:
                            tx, ty, tw, th = target_r
                            # Snap window to target and reset zoom so the picker
                            # overlay shows the unzoomed letterboxed video.
                            prev_rect = get_rect(hwnd)
                            move_window(hwnd, tx, ty, tw, th, strip_caption=True)
                            x, y, w, h = tx, ty, tw, th
                            if ipc_connected:
                                ipc.reset_zoom_pan()
                            time.sleep(0.3)  # let mpv settle before picker
                            print("\n  Drag around the actual picture content (no bars)...")
                            content_r = _pick_content_area(hwnd)
                            while msvcrt.kbhit():
                                msvcrt.getch()
                            if content_r is not None:
                                zoom, pan_x, pan_y = _compute_ipc_fill(hwnd, content_r)
                                if ipc_connected:
                                    ipc.set_property("video-zoom", zoom)
                                    ipc.set_property("video-pan-x", pan_x)
                                    ipc.set_property("video-pan-y", pan_y)
                                    log.info("F: zoom=%.3f pan_x=%.3f pan_y=%.3f", zoom, pan_x, pan_y)
                                    print(f"\n  Filled: zoom={zoom:.3f}  pan_x={pan_x:.3f}  pan_y={pan_y:.3f}")
                                else:
                                    print("\n  IPC not connected — cannot apply zoom/pan.")
                            else:
                                log.info("F: picker cancelled")
                        time.sleep(1.0)
                        _show_adjust_mode(title)
                        if hwnd is not None:
                            _show_adjust_status(x, y, w, h, _STEPS[step_idx])
                      except Exception as _e:
                        log.exception("F handler error: %s", _e)
                        print(f"\n  [error] {_e}")
                        time.sleep(2)
                        _show_adjust_mode(title)
                elif ch in (b"z", b"Z"):
                    if hwnd is not None:
                        if prev_rect is not None:
                            cur = get_rect(hwnd)
                            log.info("Z: reverting to %s", prev_rect)
                            x, y, w, h = _do_move(hwnd, *prev_rect, _STEPS[step_idx])
                            prev_rect = cur  # allow toggling back with Z again
                        if ipc_connected:
                            ipc.reset_zoom_pan()
                            log.info("Z: zoom/pan reset")
                    else:
                        print("\n  Nothing to revert.", end="", flush=True)
                elif ch in (b"c", b"C"):
                    if ipc_connected:
                        ipc.reset_zoom_pan()
                        log.info("C: zoom/pan cleared")
                        if hwnd is not None:
                            x, y, w, h = get_rect(hwnd)
                            _show_adjust_status(x, y, w, h, _STEPS[step_idx])
                    else:
                        print("\n  IPC not connected.", end="", flush=True)
                elif ch in (b"a", b"A"):
                    adjust_mode = False
                    _show_now_playing(title)
                elif ch in (b"q", b"Q", b"\x1b"):
                    ipc.quit()
                    break

            # --- Player mode ---
            else:
                if ch == b"\xe0":
                    ch2 = msvcrt.getch()
                    if ch2 == b"K":    # Left arrow — seek -10s
                        ipc.seek(-10)
                    elif ch2 == b"M":  # Right arrow — seek +10s
                        ipc.seek(10)
                    elif ch2 == b"H":  # Up arrow — volume +5
                        ipc.add_volume(5)
                    elif ch2 == b"P":  # Down arrow — volume -5
                        ipc.add_volume(-5)
                elif ch == b" ":
                    ipc.toggle_pause()
                elif ch in (b"m", b"M"):
                    ipc.toggle_mute()
                elif ch in (b"a", b"A"):
                    adjust_mode = True
                    if hwnd is not None:
                        x, y, w, h = get_rect(hwnd)
                    _show_adjust_mode(title)
                    if hwnd is not None:
                        _show_adjust_status(x, y, w, h, _STEPS[step_idx])
                elif ch in (b"q", b"Q", b"\x1b"):
                    ipc.quit()
                    break

        ipc.close()
        log.info("mpv exited with rc=%s", proc.poll())

    finally:
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


if __name__ == "__main__":
    sys.exit(main())
