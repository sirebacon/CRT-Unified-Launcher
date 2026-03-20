"""Window placement lifecycle for Live TV (VLC)."""

from __future__ import annotations

import time
from typing import Optional, Tuple

from session.window_utils import find_window, get_rect, move_window

Rect = Tuple[int, int, int, int]


def wait_for_vlc_window(pid: int, timeout_sec: float = 20.0) -> Optional[int]:
    deadline = time.time() + max(1.0, timeout_sec)
    while time.time() < deadline:
        hwnd = find_window(
            pid=pid,
            class_contains=[],
            title_contains=[],
            match_any_pid=False,
            include_iconic=True,
        )
        if hwnd:
            return hwnd
        time.sleep(0.25)
    return None


def move_to_rect(hwnd: int, rect: Rect) -> None:
    x, y, w, h = rect
    move_window(hwnd, x, y, w, h, strip_caption=False)


def get_rect_text(hwnd: int) -> str:
    try:
        x, y, w, h = get_rect(hwnd)
        return f"x={x}, y={y}, w={w}, h={h}"
    except Exception:
        return "unknown"

