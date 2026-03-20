"""Adjust-mode controls for Live TV window placement."""

from __future__ import annotations

import msvcrt
import os
from typing import Dict

from media.live_tv.config import save_live_tv_rect_local
from session.window_utils import get_rect, move_window

_STEPS = [1, 5, 10, 25, 50, 100, 200, 500, 1000]


def show_adjust_mode() -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print("========================================")
    print("         ADJUST WINDOW (Live TV)")
    print("========================================")
    print("  Arrow keys   Move left/right/up/down")
    print("  [ / ]        Narrower / Wider")
    print("  - / =        Shorter / Taller")
    print("  1 - 9        Step size (1..1000 px)")
    print("  [R]          Snap to CRT rect")
    print("  [M]          Move to main rect")
    print("  [S]          Save current rect to crt_config.local.json")
    print("  [A]          Back to playback controls")
    print("  [Q]          Quit session")
    print("========================================")


def show_adjust_status(x: int, y: int, w: int, h: int, step_idx: int) -> None:
    step = _STEPS[step_idx]
    print(
        f"\r  x={x:6d}  y={y:6d}  w={w:6d}  h={h:6d}  step={step:4d}px    ",
        end="",
        flush=True,
    )


def handle_adjust_key(ch: bytes, hwnd: int, state: Dict) -> Dict:
    x, y, w, h = state["rect"]
    step_idx = state["step_idx"]
    crt_rect = state["crt_rect"]
    main_rect = state["main_rect"]
    step = _STEPS[step_idx]

    result = {
        "adjust_mode": True,
        "quit": False,
        "rect": (x, y, w, h),
        "step_idx": step_idx,
        "saved": False,
    }

    if ch == b"\xe0":
        ch2 = msvcrt.getch()
        x, y, w, h = get_rect(hwnd)
        if ch2 == b"H":
            y -= step
        elif ch2 == b"P":
            y += step
        elif ch2 == b"K":
            x -= step
        elif ch2 == b"M":
            x += step
        else:
            return result
        move_window(hwnd, x, y, w, h, strip_caption=False)
        result["rect"] = (x, y, w, h)
        return result

    if ch == b"[":
        x, y, w, h = get_rect(hwnd)
        w = max(1, w - step)
        move_window(hwnd, x, y, w, h, strip_caption=False)
        result["rect"] = (x, y, w, h)
        return result

    if ch == b"]":
        x, y, w, h = get_rect(hwnd)
        w = max(1, w + step)
        move_window(hwnd, x, y, w, h, strip_caption=False)
        result["rect"] = (x, y, w, h)
        return result

    if ch == b"-":
        x, y, w, h = get_rect(hwnd)
        h = max(1, h - step)
        move_window(hwnd, x, y, w, h, strip_caption=False)
        result["rect"] = (x, y, w, h)
        return result

    if ch in (b"=", b"+"):
        x, y, w, h = get_rect(hwnd)
        h = max(1, h + step)
        move_window(hwnd, x, y, w, h, strip_caption=False)
        result["rect"] = (x, y, w, h)
        return result

    if ch in b"123456789":
        result["step_idx"] = int(ch) - 1
        return result

    if ch in (b"r", b"R"):
        move_window(hwnd, *crt_rect, strip_caption=False)
        result["rect"] = crt_rect
        return result

    if ch in (b"m", b"M"):
        move_window(hwnd, *main_rect, strip_caption=False)
        result["rect"] = main_rect
        return result

    if ch in (b"s", b"S"):
        x, y, w, h = get_rect(hwnd)
        save_live_tv_rect_local((x, y, w, h))
        result["rect"] = (x, y, w, h)
        result["saved"] = True
        return result

    if ch in (b"a", b"A"):
        result["adjust_mode"] = False
        return result

    if ch in (b"q", b"Q", b"\x1b"):
        result["quit"] = True
        return result

    return result

