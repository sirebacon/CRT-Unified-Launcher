"""Window diagnostics/recovery commands for crt_tools (Phase 2 scaffold)."""

import time
from typing import Any, Dict, List, Optional, Tuple

from session.display_api import enumerate_attached_displays, find_display_by_token
from session.re_config import CRT_DISPLAY_TOKEN, RE_PRIMARY_DISPLAY_TOKEN, RESTORE_PRIMARY_DISPLAY_TOKEN
from session.window_utils import enum_windows, find_window, get_rect, is_window_fullscreen, move_window

# Label -> config token for display identification in window list
_DISPLAY_LABELS = [
    ("vdd", RE_PRIMARY_DISPLAY_TOKEN),
    ("crt", CRT_DISPLAY_TOKEN),
    ("internal", RESTORE_PRIMARY_DISPLAY_TOKEN),
]

try:
    import psutil
    import win32api
    import win32con
    import win32gui
    import win32process
except Exception:
    psutil = None
    win32api = None
    win32con = None
    win32gui = None
    win32process = None


def _display_rect_for_token(token: str) -> Optional[Tuple[int, int, int, int]]:
    if win32api is None or win32con is None:
        return None
    d = find_display_by_token(token)
    if not d:
        return None
    dev_name = d.get("device_name")
    if not dev_name:
        return None
    dm = win32api.EnumDisplaySettings(dev_name, win32con.ENUM_CURRENT_SETTINGS)
    x, y = d.get("position", (0, 0))
    return (int(x), int(y), int(dm.PelsWidth), int(dm.PelsHeight))


def _all_display_rects() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if win32api is None or win32con is None:
        return rows
    for d in enumerate_attached_displays():
        try:
            dm = win32api.EnumDisplaySettings(d["device_name"], win32con.ENUM_CURRENT_SETTINGS)
            x, y = d.get("position", (0, 0))
            rows.append(
                {
                    "device_name": d.get("device_name", ""),
                    "device_string": d.get("device_string", ""),
                    "monitor_strings": d.get("monitor_strings", []),
                    "x": int(x),
                    "y": int(y),
                    "w": int(dm.PelsWidth),
                    "h": int(dm.PelsHeight),
                }
            )
        except Exception:
            continue
    return rows


def _intersection_area(
    a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy


def _display_label_for_rect(rect: Tuple[int, int, int, int]) -> str:
    best = None
    best_area = -1
    for d in _all_display_rects():
        area = _intersection_area(rect, (d["x"], d["y"], d["w"], d["h"]))
        if area > best_area:
            best = d
            best_area = area
    if not best or best_area <= 0:
        return "none"
    text = " ".join(
        [str(best.get("device_name", "")), str(best.get("device_string", ""))]
        + [str(x) for x in (best.get("monitor_strings") or [])]
    ).lower()
    for label, token in _DISPLAY_LABELS:
        if token.lower() in text:
            return label
    return str(best.get("device_name", "unknown"))


def _state_for_hwnd(hwnd: int) -> str:
    if win32gui is None:
        return "unknown"
    try:
        if win32gui.IsIconic(hwnd):
            return "minimized"
        if win32gui.IsZoomed(hwnd):
            return "maximized"
        if is_window_fullscreen(hwnd):
            return "fullscreen"
    except Exception:
        return "unknown"
    return "normal"


def _process_name_for_pid(pid: int) -> str:
    if psutil is None:
        return ""
    try:
        return psutil.Process(pid).name()
    except Exception:
        return ""


def window_list(filter_text: Optional[str] = None) -> Dict[str, Any]:
    if win32gui is None or win32process is None:
        return {"rows": [], "error": "pywin32 window APIs unavailable"}
    filt = (filter_text or "").lower()
    rows: List[Dict[str, Any]] = []
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd):
                continue
            title = win32gui.GetWindowText(hwnd) or ""
            cls = win32gui.GetClassName(hwnd) or ""
            if filt and filt not in title.lower():
                # also allow process name matching
                _, pid_tmp = win32process.GetWindowThreadProcessId(hwnd)
                pname = _process_name_for_pid(pid_tmp)
                if filt not in pname.lower():
                    continue
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            x, y, w, h = get_rect(hwnd)
            rows.append(
                {
                    "hwnd": hwnd,
                    "title": title,
                    "class": cls,
                    "pid": int(pid),
                    "process": _process_name_for_pid(pid),
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "state": _state_for_hwnd(hwnd),
                    "display": _display_label_for_rect((x, y, w, h)),
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda r: (r["title"].lower(), r["hwnd"]))
    return {"rows": rows}


def print_window_list(data: Dict[str, Any]) -> int:
    if data.get("error"):
        print(f"[tools] FAIL: window list -- {data['error']}")
        return 1
    rows = data.get("rows", [])
    if not rows:
        print("[tools] PASS: window list -- no matching visible windows")
        return 0
    print("Visible top-level windows")
    print()
    print(
        f"{'HWND':<10} {'PID':<7} {'Process':<20} {'Class':<20} "
        f"{'Rect':<32} {'Display':<10} State  Title"
    )
    for r in rows:
        rect = f"x={r['x']} y={r['y']} w={r['w']} h={r['h']}"
        title = (r["title"] or "").replace("\r", " ").replace("\n", " ")
        print(
            f"0x{r['hwnd']:08X} {r['pid']:<7} {r['process'][:20]:<20} {r['class'][:20]:<20} "
            f"{rect:<32} {r.get('display','?'):<10} {r['state']:<9} {title}"
        )
    return 0


def window_move(
    title: str,
    display_token: Optional[str] = None,
    rect: Optional[Tuple[int, int, int, int]] = None,
    force: bool = False,
) -> int:
    hwnd = find_window(None, [], [title.lower()], match_any_pid=True, include_iconic=True)
    if hwnd is None:
        print(f"[tools] FAIL: window move -- no window found for title fragment: {title!r}")
        return 1

    target_rect = rect
    if target_rect is None and display_token:
        target_rect = _display_rect_for_token(display_token)
        if target_rect is None:
            print(f"[tools] FAIL: window move -- display token not found: {display_token!r}")
            return 1
    if target_rect is None:
        print("[tools] FAIL: window move -- specify --display or --rect")
        return 1

    try:
        curr = get_rect(hwnd)
        if win32gui is not None:
            title_text = win32gui.GetWindowText(hwnd)
        else:
            title_text = title
    except Exception:
        curr = None
        title_text = title

    x, y, w, h = target_rect
    print(f"Window: {title_text!r} (HWND 0x{hwnd:08X})")
    if curr:
        print(f"Current: x={curr[0]} y={curr[1]} w={curr[2]} h={curr[3]}")
    print(f"Target : x={x} y={y} w={w} h={h}")

    if not force:
        ans = input("Apply move? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("[tools] PASS: window move -- cancelled")
            return 0
    try:
        move_window(hwnd, x, y, w, h, strip_caption=False)
        time.sleep(0.05)
        new_rect = get_rect(hwnd)
        print(
            f"[tools] PASS: window move -- moved to x={new_rect[0]} y={new_rect[1]} "
            f"w={new_rect[2]} h={new_rect[3]}"
        )
        return 0
    except Exception as e:
        print(f"[tools] FAIL: window move -- {e}")
        return 1


def window_restore(force: bool = False) -> int:
    """Move Moonlight back to the configured idle rect (or live internal display bounds)."""
    from session.moonlight import move_moonlight_to_internal
    from session.re_config import MOONLIGHT_DIR, MOONLIGHT_IDLE_RECT, REQUIRED_DISPLAY_GROUPS

    internal_tokens = REQUIRED_DISPLAY_GROUPS.get("internal_display", [])
    idle_rect = MOONLIGHT_IDLE_RECT

    print("Window restore:")
    if idle_rect:
        print(f"  Moonlight -> idle_rect: x={idle_rect[0]} y={idle_rect[1]} w={idle_rect[2]} h={idle_rect[3]}")
    else:
        print("  Moonlight -> live internal display bounds (no idle_rect configured)")

    if not force:
        ans = input("Apply? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("[tools] PASS: window restore -- cancelled")
            return 0

    ok = move_moonlight_to_internal(internal_tokens, MOONLIGHT_DIR, idle_rect=idle_rect)
    if ok:
        print("[tools] PASS: window restore -- Moonlight moved to idle position")
        return 0
    print("[tools] FAIL: window restore -- could not find or move Moonlight window")
    return 1


def window_watch(title: str, interval: float = 1.0) -> int:
    print(f'Watching window title fragment: "{title}"  (Ctrl+C to stop)')
    last_rect: Optional[Tuple[int, int, int, int]] = None
    last_display: Optional[str] = None
    while True:
        hwnd = find_window(None, [], [title.lower()], match_any_pid=True, include_iconic=True)
        if hwnd is None:
            print("[tools] window watch -- no matching window visible", end="\r")
            time.sleep(max(0.1, interval))
            continue
        try:
            rect = get_rect(hwnd)
            state = _state_for_hwnd(hwnd)
            disp = _display_label_for_rect(rect)
            moved = " [MOVED]" if (last_rect != rect or last_display != disp) else ""
            line = (
                f"HWND=0x{hwnd:08X}  x={rect[0]} y={rect[1]} w={rect[2]} h={rect[3]}  "
                f"display={disp}  state={state}{moved}"
            )
            print(line + " " * 12, end="\r")
            last_rect = rect
            last_display = disp
        except Exception as e:
            print(f"[tools] FAIL: window watch -- {e}")
            return 1
        time.sleep(max(0.1, interval))
