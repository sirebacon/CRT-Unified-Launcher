"""Window/monitor helpers, wait-for-window, preset rect, IPC fill, content picker."""

import ctypes
import ctypes.wintypes
import json
import logging
import math
import os
import subprocess
import sys
import time
from typing import Optional, Tuple

from session.window_utils import find_window, get_rect, move_window
from youtube.config import (
    _LOG_PATH,
    _MPV_PROFILE_PATH,
    _PRESETS_PATH,
    _PROJECT_ROOT,
    load_json,
)

log = logging.getLogger("youtube")

# ---- ctypes monitor APIs ----

_MonitorFromWindow = ctypes.windll.user32.MonitorFromWindow
_MonitorFromWindow.restype = ctypes.c_void_p
_MONITOR_DEFAULTTONEAREST = 2


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


def get_monitor_bounds(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
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
        log.exception("get_monitor_bounds failed for hwnd=0x%x: %s", hwnd, e)
        return None


def wait_for_window(pid: int, timeout: float = 15.0) -> Optional[int]:
    """Poll for mpv window by PID. Returns HWND or None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = find_window(pid, [], [])
        if hwnd is not None:
            return hwnd
        time.sleep(0.5)
    return None


def get_preset_target_rect() -> Optional[Tuple[int, int, int, int]]:
    """Derive the usable CRT target rect from the active preset.

    Returns (x, y, w, h) or None on failure.
    """
    try:
        data = load_json(_PRESETS_PATH)
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
        log.exception("get_preset_target_rect failed: %s", e)
        return None


def save_rect_to_profile(x: int, y: int, w: int, h: int) -> bool:
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


def clamp_to_monitor(hwnd: int, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
    """Clamp window rect so it stays fully within the monitor it is on."""
    bounds = get_monitor_bounds(hwnd)
    if bounds is None:
        return x, y, w, h
    ml, mt, mr, mb = bounds
    w = min(w, mr - ml)
    h = min(h, mb - mt)
    x = max(ml, min(x, mr - w))
    y = max(mt, min(y, mb - h))
    return x, y, w, h


def do_move(hwnd: int, x: int, y: int, w: int, h: int, step: int) -> Tuple[int, int, int, int]:
    """Move window and redraw the status line. Returns the applied (x, y, w, h)."""
    from youtube.controls import show_adjust_status
    move_window(hwnd, x, y, w, h, strip_caption=True)
    show_adjust_status(x, y, w, h, step)
    return x, y, w, h


def pick_content_area(hwnd_ref: int) -> Optional[Tuple[int, int, int, int]]:
    """Single-step drag-to-select overlay on the CRT monitor.

    Returns (cx, cy, cw, ch) or None if cancelled/error.
    """
    import json as _json
    log.info("picker: starting (hwnd_ref=0x%x)", hwnd_ref)

    bounds = get_monitor_bounds(hwnd_ref)
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
            data = _json.loads(proc.stdout.strip())
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


def compute_ipc_fill(hwnd: int, content_rect: tuple) -> Tuple[float, float, float]:
    """Compute mpv IPC zoom+pan to fill window height with the selected content.

    Returns (zoom, pan_x, pan_y).
    """
    wx, wy, ww, wh = get_rect(hwnd)
    cx, cy, cw, ch = content_rect

    if ch <= 0 or cw <= 0 or ww <= 0 or wh <= 0:
        return 0.0, 0.0, 0.0

    VIDEO_AR = 16.0 / 9.0
    if ww / wh < VIDEO_AR:
        video_w = float(ww)
        video_h = ww / VIDEO_AR
        bar_x, bar_y = 0.0, (wh - video_h) / 2.0
    else:
        video_h = float(wh)
        video_w = wh * VIDEO_AR
        bar_x, bar_y = (ww - video_w) / 2.0, 0.0

    cx_vid = (cx - wx) - bar_x
    cy_vid = (cy - wy) - bar_y

    scale = wh / ch
    zoom = math.log2(scale)

    zvw = video_w * scale
    zvh = video_h * scale

    cvx = (cx_vid + cw / 2.0) * scale
    cvy = (cy_vid + ch / 2.0) * scale

    pan_x = (cvx - zvw / 2.0) / ww
    pan_y = (cvy - zvh / 2.0) / wh

    log.info(
        "IPC fill: ww=%d wh=%d video_disp=%.0fx%.0f "
        "bar_x=%.0f bar_y=%.0f scale=%.3f zoom=%.3f pan_x=%.3f pan_y=%.3f",
        ww, wh, video_w, video_h, bar_x, bar_y, scale, zoom, pan_x, pan_y,
    )
    return zoom, pan_x, pan_y
