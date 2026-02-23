"""Calibration commands for crt_tools (Phase 3)."""

import json
from typing import Optional, Tuple

from session.display_api import find_display_by_token
from session.moonlight_adjuster import adjust_moonlight, capture_moonlight_pos
from session.re_config import CRT_DISPLAY_TOKEN, RE_STACK_CONFIG_PATH
from session.window_utils import find_window, get_rect

try:
    import win32api
    import win32con
    import win32gui
except Exception:
    win32api = None
    win32con = None
    win32gui = None


def _display_rect_from_token(token: str) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) for the display identified by token, or None."""
    if win32api is None or win32con is None:
        return None
    d = find_display_by_token(token)
    if not d:
        return None
    try:
        dm = win32api.EnumDisplaySettings(d["device_name"], win32con.ENUM_CURRENT_SETTINGS)
        x, y = d.get("position", (0, 0))
        return (int(x), int(y), int(dm.PelsWidth), int(dm.PelsHeight))
    except Exception:
        return None


def _overlap_ratio(
    win_rect: Tuple[int, int, int, int],
    disp_rect: Tuple[int, int, int, int],
) -> float:
    """Return the fraction of window area that overlaps with the display rect (0.0-1.0)."""
    wx, wy, ww, wh = win_rect
    dx, dy, dw, dh = disp_rect
    ix = max(0, min(wx + ww, dx + dw) - max(wx, dx))
    iy = max(0, min(wy + wh, dy + dh) - max(wy, dy))
    win_area = ww * wh
    if win_area <= 0:
        return 0.0
    return (ix * iy) / win_area


def _write_crt_calibration(x_offset: int, y_offset: int, w_delta: int, h_delta: int) -> bool:
    """Write crt_calibration offsets to re_stack_config.json. Returns True on success."""
    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[tools] FAIL: calibrate set-crt-offsets -- could not read config: {e}")
        return False
    cfg["crt_calibration"] = {
        "mode": "relative_to_crt",
        "x_offset": x_offset,
        "y_offset": y_offset,
        "w_delta": w_delta,
        "h_delta": h_delta,
    }
    try:
        with open(RE_STACK_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"[tools] FAIL: calibrate set-crt-offsets -- could not write config: {e}")
        return False


def calibrate_adjust() -> int:
    """Run the interactive Moonlight window adjuster. Moonlight must be running."""
    return adjust_moonlight()


def calibrate_set_crt() -> int:
    """Capture current Moonlight window rect and save as crt_rect in re_stack_config.json."""
    return capture_moonlight_pos("crt_rect")


def calibrate_set_idle() -> int:
    """Capture current Moonlight window rect and save as idle_rect in re_stack_config.json."""
    return capture_moonlight_pos("idle_rect")


def calibrate_overlap(
    window_title: str,
    display_token: str,
    threshold: float = 0.95,
) -> int:
    """Report the overlap ratio between a window and a display, relative to window area."""
    hwnd = find_window(None, [], [window_title.lower()], match_any_pid=True, include_iconic=True)
    if hwnd is None:
        print(f"[tools] FAIL: calibrate overlap -- no window found for: {window_title!r}")
        return 1

    win_rect = get_rect(hwnd)
    win_title = win32gui.GetWindowText(hwnd) if win32gui is not None else window_title

    disp_rect = _display_rect_from_token(display_token)
    if disp_rect is None:
        print(f"[tools] FAIL: calibrate overlap -- display token not found: {display_token!r}")
        return 1

    d = find_display_by_token(display_token)
    mons = " ".join(d.get("monitor_strings") or []) if d else ""
    disp_label = f"{d.get('device_string', '')} {mons}".strip() if d else display_token

    ratio = _overlap_ratio(win_rect, disp_rect)
    wx, wy, ww, wh = win_rect
    dx, dy, dw, dh = disp_rect
    win_area = ww * wh
    ix = max(0, min(wx + ww, dx + dw) - max(wx, dx))
    iy = max(0, min(wy + wh, dy + dh) - max(wy, dy))
    overlap_area = ix * iy

    print(f"Window  : {win_title!r}  x={wx}  y={wy}  w={ww}  h={wh}  (HWND 0x{hwnd:08X})")
    print(f"Display : {disp_label}  x={dx}  y={dy}  w={dw}  h={dh}")
    print()
    print(f"Window area   : {win_area:,} px")
    print(f"Overlap area  : {overlap_area:,} px")
    print(f"Overlap ratio : {ratio:.3f}  (threshold: {threshold})", end="")

    if ratio >= threshold:
        print("  OK")
        return 0

    print("  BELOW THRESHOLD")
    if wx < dx:
        print(f"  Window is {dx - wx}px left of display left edge")
    if wx + ww > dx + dw:
        print(f"  Window extends {wx + ww - (dx + dw)}px past display right edge")
    if wy < dy:
        print(f"  Window is {dy - wy}px above display top edge")
    if wy + wh > dy + dh:
        print(f"  Window extends {wy + wh - (dy + dh)}px below display bottom edge")
    print()
    print("  Run 'calibrate adjust' or 'calibrate set-crt-offsets' to recalibrate.")
    return 1


def calibrate_set_crt_offsets(from_current: bool = False) -> int:
    """Compute and save CRT calibration as relative offsets from the live CRT display bounds.

    Offsets are stored in re_stack_config.json under 'crt_calibration' and can be used
    to reconstruct the correct Moonlight window position even after a topology change
    shifts the virtual desktop origin.

    With --from-current: reads the current Moonlight window rect immediately.
    Without --from-current: opens the interactive adjuster first so you can position
    the window, then reads the final position on exit.
    """
    if not from_current:
        print("Opening Moonlight adjuster -- position the window, then quit the adjuster.")
        print("Offsets will be computed from the final window position.")
        print()
        result = adjust_moonlight()
        if result != 0:
            return result

    hwnd = find_window(None, [], ["moonlight"], match_any_pid=True, include_iconic=True)
    if hwnd is None:
        print("[tools] FAIL: calibrate set-crt-offsets -- no Moonlight window found")
        return 1

    if win32gui is not None:
        win_title = win32gui.GetWindowText(hwnd)
    else:
        win_title = "Moonlight"

    win_rect = get_rect(hwnd)
    disp_rect = _display_rect_from_token(CRT_DISPLAY_TOKEN)
    if disp_rect is None:
        print(
            f"[tools] FAIL: calibrate set-crt-offsets -- CRT display not found "
            f"(token: {CRT_DISPLAY_TOKEN!r})"
        )
        return 1

    wx, wy, ww, wh = win_rect
    dx, dy, dw, dh = disp_rect
    x_offset = wx - dx
    y_offset = wy - dy
    w_delta = ww - dw
    h_delta = wh - dh

    print(f"Window  : {win_title!r}  x={wx}  y={wy}  w={ww}  h={wh}")
    print(f"CRT display : x={dx}  y={dy}  w={dw}  h={dh}")
    print()
    print("Computed offsets:")
    print(f"  x_offset : {x_offset:+d}  (window x - display x)")
    print(f"  y_offset : {y_offset:+d}  (window y - display y)")
    print(f"  w_delta  : {w_delta:+d}  (window w - display w)")
    print(f"  h_delta  : {h_delta:+d}  (window h - display h)")
    print()

    if _write_crt_calibration(x_offset, y_offset, w_delta, h_delta):
        print("[tools] PASS: calibrate set-crt-offsets -- saved to re_stack_config.json")
        return 0
    return 1
