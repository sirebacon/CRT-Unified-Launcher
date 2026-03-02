"""Adjust-mode key handler — extracted from the main loop."""

import logging
import msvcrt
import time
from typing import Optional

from session.window_utils import get_rect, move_window
from youtube.controls import show_adjust_mode, show_adjust_status, show_now_playing
from youtube.config import load_json, _MPV_PROFILE_PATH
from youtube.state import add_zoom_preset
from youtube.player import (
    compute_ipc_fill,
    do_move,
    get_preset_target_rect,
    pick_content_area,
    save_rect_to_profile,
)

log = logging.getLogger("youtube")

_STEPS = [1, 5, 10, 25, 50, 100, 200, 500, 1000]


def handle_adjust_key(
    ch: bytes,
    hwnd: Optional[int],
    ipc_connected: bool,
    ipc,
    title: str,
    x: int,
    y: int,
    w: int,
    h: int,
    step_idx: int,
    prev_rect,
    is_playlist: bool,
    playlist_pos: Optional[int],
    playlist_count: Optional[int],
    zoom_locked: bool = False,
    zoom_preset_name: Optional[str] = None,
) -> dict:
    """Handle one keypress in adjust mode.

    Returns a dict with updated state: adjust_mode, x, y, w, h,
    step_idx, prev_rect, quit.
    """
    result = {
        "adjust_mode": True,
        "x": x, "y": y, "w": w, "h": h,
        "step_idx": step_idx,
        "prev_rect": prev_rect,
        "quit": False,
    }

    step = _STEPS[step_idx]

    if ch == b"\xe0":
        ch2 = msvcrt.getch()
        if hwnd is not None:
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
            x, y, w, h = do_move(hwnd, x, y, w, h, step)
            result.update({"x": x, "y": y, "w": w, "h": h})

    elif ch == b"[":
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            x, y, w, h = do_move(hwnd, x, y, max(1, w - step), h, step)
            result.update({"x": x, "y": y, "w": w, "h": h})

    elif ch == b"]":
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            x, y, w, h = do_move(hwnd, x, y, w + step, h, step)
            result.update({"x": x, "y": y, "w": w, "h": h})

    elif ch == b"-":
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            x, y, w, h = do_move(hwnd, x, y, w, max(1, h - step), step)
            result.update({"x": x, "y": y, "w": w, "h": h})

    elif ch in (b"=", b"+"):
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            x, y, w, h = do_move(hwnd, x, y, w, h + step, step)
            result.update({"x": x, "y": y, "w": w, "h": h})

    elif ch in b"123456789":
        result["step_idx"] = int(ch) - 1
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            show_adjust_status(x, y, w, h, _STEPS[result["step_idx"]])

    elif ch in (b"s", b"S"):
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            if save_rect_to_profile(x, y, w, h):
                print(f"\n  Saved: x={x}, y={y}, w={w}, h={h}")
            show_adjust_status(x, y, w, h, step)
            result.update({"x": x, "y": y, "w": w, "h": h})

    elif ch in (b"r", b"R"):
        if hwnd is not None:
            try:
                log.info("R pressed: snapping to preset target (hwnd=0x%x)", hwnd)
                target_r = get_preset_target_rect()
                if target_r is None:
                    print("\n  Cannot read preset target rect — check crt_presets.json.")
                    time.sleep(2)
                else:
                    tx, ty, tw, th = target_r
                    result["prev_rect"] = get_rect(hwnd)
                    move_window(hwnd, tx, ty, tw, th, strip_caption=True)
                    x, y, w, h = tx, ty, tw, th
                    if ipc_connected:
                        ipc.reset_zoom_pan()
                    log.info("R: snapped to (%d,%d,%d,%d) zoom/pan reset", x, y, w, h)
                    print(f"\n  Snapped to preset: x={x}, y={y}, w={w}, h={h}")
                    result.update({"x": x, "y": y, "w": w, "h": h})
                time.sleep(1.0)
                show_adjust_mode(title)
                if hwnd is not None:
                    show_adjust_status(x, y, w, h, step)
            except Exception as e:
                log.exception("R handler error: %s", e)
                print(f"\n  [error] {e}")
                time.sleep(2)
                show_adjust_mode(title)

    elif ch in (b"f", b"F"):
        if hwnd is not None:
            try:
                log.info("F pressed: IPC fill (hwnd=0x%x)", hwnd)
                target_r = get_preset_target_rect()
                if target_r is None:
                    print("\n  Cannot read preset target rect.")
                    time.sleep(2)
                else:
                    tx, ty, tw, th = target_r
                    result["prev_rect"] = get_rect(hwnd)
                    move_window(hwnd, tx, ty, tw, th, strip_caption=True)
                    x, y, w, h = tx, ty, tw, th
                    if ipc_connected:
                        ipc.reset_zoom_pan()
                    time.sleep(0.3)
                    print("\n  Drag around the actual picture content (no bars)...")
                    content_r = pick_content_area(hwnd)
                    while msvcrt.kbhit():
                        msvcrt.getch()
                    if content_r is not None:
                        zoom, pan_x, pan_y = compute_ipc_fill(hwnd, content_r)
                        if ipc_connected:
                            ipc.set_property("video-zoom", zoom)
                            ipc.set_property("video-pan-x", pan_x)
                            ipc.set_property("video-pan-y", pan_y)
                            log.info("F: zoom=%.3f pan_x=%.3f pan_y=%.3f", zoom, pan_x, pan_y)
                            print(
                                f"\n  Filled: zoom={zoom:.3f}  "
                                f"pan_x={pan_x:.3f}  pan_y={pan_y:.3f}"
                            )
                        else:
                            print("\n  IPC not connected — cannot apply zoom/pan.")
                    else:
                        log.info("F: picker cancelled")
                    result.update({"x": x, "y": y, "w": w, "h": h})
                time.sleep(1.0)
                show_adjust_mode(title)
                if hwnd is not None:
                    show_adjust_status(x, y, w, h, step)
            except Exception as e:
                log.exception("F handler error: %s", e)
                print(f"\n  [error] {e}")
                time.sleep(2)
                show_adjust_mode(title)

    elif ch in (b"z", b"Z"):
        if hwnd is not None:
            try:
                if prev_rect is not None:
                    cur = get_rect(hwnd)
                    x, y, w, h = do_move(hwnd, *prev_rect, step)
                    result.update({"x": x, "y": y, "w": w, "h": h})
                    result["prev_rect"] = cur
                    log.info("Z: reverted to (%d,%d,%d,%d)", x, y, w, h)
                if ipc_connected:
                    ipc.reset_zoom_pan()
                    log.info("Z: zoom/pan reset")
                time.sleep(0.3)
                show_adjust_mode(title)
                show_adjust_status(x, y, w, h, step)
            except Exception as e:
                log.exception("Z handler error: %s", e)
                print(f"\n  [error] {e}")
                time.sleep(1)
                show_adjust_mode(title)
        else:
            print("\n  Nothing to revert.", end="", flush=True)

    elif ch in (b"c", b"C"):
        if ipc_connected:
            ipc.reset_zoom_pan()
            log.info("C: zoom/pan cleared")
            if hwnd is not None:
                x, y, w, h = get_rect(hwnd)
                show_adjust_status(x, y, w, h, step)
                result.update({"x": x, "y": y, "w": w, "h": h})
        else:
            print("\n  IPC not connected.", end="", flush=True)

    elif ch in (b"l", b"L"):
        # Load saved profile rect and apply it
        if hwnd is not None:
            try:
                profile = load_json(_MPV_PROFILE_PATH)
                px, py, pw, ph = profile["x"], profile["y"], profile["w"], profile["h"]
                result["prev_rect"] = get_rect(hwnd)
                x, y, w, h = do_move(hwnd, px, py, pw, ph, step)
                result.update({"x": x, "y": y, "w": w, "h": h})
                log.info("L: loaded profile rect (%d,%d,%d,%d)", x, y, w, h)
                print(f"\n  Loaded profile: x={x}, y={y}, w={w}, h={h}")
                time.sleep(0.5)
                show_adjust_mode(title)
                show_adjust_status(x, y, w, h, step)
            except Exception as e:
                log.exception("L handler error: %s", e)
                print(f"\n  [error] reading profile: {e}")
                time.sleep(1)
                show_adjust_mode(title)

    elif ch in (b"p", b"P"):
        if ipc_connected:
            log.info("P: reading zoom/pan from IPC")
            zoom  = ipc.get_property("video-zoom")
            pan_x = ipc.get_property("video-pan-x")
            pan_y = ipc.get_property("video-pan-y")
            log.info("P: IPC returned zoom=%s pan_x=%s pan_y=%s", zoom, pan_x, pan_y)
            if zoom is not None:
                print("\n  Preset name (Enter = \"default\"): ", end="", flush=True)
                try:
                    name = input().strip() or "default"
                except (EOFError, KeyboardInterrupt):
                    name = "default"
                add_zoom_preset(name, zoom or 0.0, pan_x or 0.0, pan_y or 0.0)
                log.info(
                    "P: zoom preset saved: %r zoom=%.3f pan_x=%.3f pan_y=%.3f",
                    name, zoom, pan_x or 0.0, pan_y or 0.0,
                )
                print(f"  Saved preset \"{name}\".")
                time.sleep(1.0)
            else:
                log.warning("P: get_property returned None — rw_handle unavailable or IPC timeout")
                print("\n  IPC could not read zoom — is video playing?")
                time.sleep(1.0)
        else:
            log.warning("P: IPC not connected")
            print("\n  IPC not connected.")
            time.sleep(1.0)
        show_adjust_mode(title)
        if hwnd is not None:
            x, y, w, h = get_rect(hwnd)
            show_adjust_status(x, y, w, h, step)

    elif ch in (b"a", b"A"):
        result["adjust_mode"] = False
        show_now_playing(title, is_playlist, playlist_pos, playlist_count, zoom_locked, zoom_preset_name)

    elif ch in (b"q", b"Q", b"\x1b"):
        ipc.quit()
        result["quit"] = True

    return result
