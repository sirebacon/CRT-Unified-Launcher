"""Moonlight window position capture and interactive adjuster."""

import json
import msvcrt

import win32gui

from session.re_config import RE_STACK_CONFIG_PATH, MOONLIGHT_DIR
from session.window_utils import find_window, get_rect, move_window


def write_moonlight_rect(config_key: str, x: int, y: int, w: int, h: int) -> bool:
    """Write a Moonlight rect to re_stack_config.json. Returns True on success."""
    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[re-stack] Could not read config: {e}")
        return False
    if "moonlight" not in cfg:
        cfg["moonlight"] = {}
    cfg["moonlight"][config_key] = {"x": x, "y": y, "w": w, "h": h}
    try:
        with open(RE_STACK_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"[re-stack] Could not write config: {e}")
        return False


def capture_moonlight_pos(config_key: str) -> int:
    """Capture the current Moonlight window rect and write it to re_stack_config.json."""
    hwnd = find_window(None, [], ["moonlight"])
    if hwnd is None:
        print("[re-stack] No Moonlight window found — make sure Moonlight is open.")
        return 1
    x, y, w, h = get_rect(hwnd)
    title = win32gui.GetWindowText(hwnd)
    print(f"[re-stack] Moonlight window: {title!r}  x={x}, y={y}, w={w}, h={h}")
    label = "idle (restore)" if config_key == "idle_rect" else "CRT"
    if write_moonlight_rect(config_key, x, y, w, h):
        print(f"[re-stack] Saved as Moonlight {label} rect in re_stack_config.json.")
        return 0
    return 1


def adjust_moonlight() -> int:
    """Interactive keyboard-driven Moonlight window position/size adjuster.

    Move and resize the Moonlight window live, then save the result to config.

    Controls
    --------
    Arrow keys          Move left / right / up / down
    [ / ]               Narrower / wider  (decrease/increase width)
    - / =               Shorter / taller  (decrease/increase height)
    1 – 9               Step size: 1, 5, 10, 25, 50, 100, 200, 500, 1000 px
    i                   Save current position as idle (restore) rect
    c                   Save current position as CRT rect
    q  or  Esc          Quit without saving
    """
    STEPS = [1, 5, 10, 25, 50, 100, 200, 500, 1000]
    step_idx = 2  # default 10 px

    hwnd = find_window(None, [], ["moonlight"])
    if hwnd is None:
        print("No Moonlight window found — make sure Moonlight is open.")
        return 1

    x, y, w, h = get_rect(hwnd)
    title = win32gui.GetWindowText(hwnd)

    print(f"=== Moonlight Window Adjuster  ({title}) ===")
    print("  Arrow keys   move x/y          [ / ]   narrower / wider")
    print("  - / =        shorter / taller  1-9     step size")
    print("  i  save idle rect              c       save CRT rect")
    print("  q / Esc      quit without saving")
    print()

    def _show():
        step = STEPS[step_idx]
        print(
            f"\r  x={x:6d}  y={y:6d}  w={w:6d}  h={h:6d}  step={step:4d}px    ",
            end="",
            flush=True,
        )

    def _apply():
        try:
            move_window(hwnd, x, y, w, h, strip_caption=False)
        except Exception as e:
            print(f"\n  move failed: {e}")

    _show()

    while True:
        ch = msvcrt.getch()

        if ch == b"\xe0":
            # Extended key — read the second byte
            ch2 = msvcrt.getch()
            step = STEPS[step_idx]
            if ch2 == b"H":    y -= step                            # up
            elif ch2 == b"P":  y += step                            # down
            elif ch2 == b"K":  x -= step                            # left
            elif ch2 == b"M":  x += step                            # right
            else:
                continue
            _apply()
            _show()

        elif ch == b"[":
            w = max(1, w - STEPS[step_idx]); _apply(); _show()
        elif ch == b"]":
            w += STEPS[step_idx]; _apply(); _show()
        elif ch == b"-":
            h = max(1, h - STEPS[step_idx]); _apply(); _show()
        elif ch in (b"=", b"+"):
            h += STEPS[step_idx]; _apply(); _show()

        elif ch in b"123456789":
            step_idx = int(ch) - 1
            _show()

        elif ch in (b"i", b"I"):
            print()
            if write_moonlight_rect("idle_rect", x, y, w, h):
                print(f"  Saved idle rect: x={x}, y={y}, w={w}, h={h}")
            _show()

        elif ch in (b"c", b"C"):
            print()
            if write_moonlight_rect("crt_rect", x, y, w, h):
                print(f"  Saved CRT rect:  x={x}, y={y}, w={w}, h={h}")
            _show()

        elif ch in (b"q", b"Q", b"\x1b"):
            print("\n  Quit — no changes saved.")
            break

    return 0
