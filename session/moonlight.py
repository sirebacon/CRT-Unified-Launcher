"""Moonlight process management and window placement."""

import json
import os
import subprocess
import time
from typing import List, Optional, Tuple

from session.display_api import get_crt_display_rect
from session.window_utils import find_window, is_window_fullscreen, move_window

try:
    import psutil
except Exception:
    psutil = None


def moonlight_pids(moonlight_dir: str) -> List[int]:
    pids: List[int] = []
    if psutil is None:
        return pids
    wanted = os.path.normcase(os.path.normpath(moonlight_dir))
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").lower()
            exe = str(proc.info.get("exe") or "")
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "moonlight" not in name and "moonlight" not in cmd.lower():
                continue
            if exe:
                exe_dir = os.path.normcase(os.path.normpath(os.path.dirname(exe)))
                if exe_dir == wanted:
                    pids.append(int(proc.info["pid"]))
            else:
                pids.append(int(proc.info["pid"]))
        except Exception:
            continue
    return pids


def is_moonlight_running(moonlight_dir: str) -> bool:
    if psutil is None:
        return False
    wanted = os.path.normcase(os.path.normpath(moonlight_dir))
    for proc in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").lower()
            exe = str(proc.info.get("exe") or "")
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "moonlight" not in name and "moonlight" not in cmd.lower():
                continue
            if exe:
                exe_dir = os.path.normcase(os.path.normpath(os.path.dirname(exe)))
                if exe_dir == wanted:
                    return True
            else:
                if "moonlight" in cmd.lower():
                    return True
        except Exception:
            continue
    return False


def ensure_moonlight_running(moonlight_exe: str, moonlight_dir: str) -> bool:
    if is_moonlight_running(moonlight_dir):
        print("[re-stack] Moonlight is already running.")
        return True
    if not os.path.exists(moonlight_exe):
        print(f"[re-stack] Moonlight executable not found: {moonlight_exe}")
        return False
    try:
        subprocess.Popen([moonlight_exe], cwd=moonlight_dir)
    except Exception as e:
        print(f"[re-stack] Failed to start Moonlight: {e}")
        return False
    for _ in range(30):
        time.sleep(0.5)
        if is_moonlight_running(moonlight_dir):
            print("[re-stack] Moonlight started.")
            return True
    print("[re-stack] Moonlight did not appear as running in time.")
    return False


def is_moonlight_fullscreen(moonlight_dir: str) -> bool:
    """Return True if the Moonlight window is currently in fullscreen mode.

    Searches all Moonlight PIDs. Returns True as soon as any window is detected
    as fullscreen (title bar gone or window rect matches its monitor).
    """
    for pid in moonlight_pids(moonlight_dir):
        hwnd = find_window(pid, [], ["moonlight"], match_any_pid=False)
        if hwnd is None:
            hwnd = find_window(pid, [], [], match_any_pid=False)
        if hwnd and is_window_fullscreen(hwnd):
            return True
    return False


def is_gameplay_window_visible(title_fragment: str) -> bool:
    """Return True if any visible top-level window title contains title_fragment.

    Used to detect when the gameplay window has appeared (e.g. 'RESIDENT EVIL',
    'RESIDENT EVIL 2', 'NEMISIS') as opposed to the launcher config screen.
    Matching is case-insensitive.
    """
    return find_window(None, [], [title_fragment.lower()]) is not None


def find_moonlight_window(moonlight_dir: str) -> Optional[int]:
    pids = moonlight_pids(moonlight_dir)
    if not pids:
        print("[re-stack] DEBUG moonlight: no Moonlight PIDs found")
        return None
    for pid in pids:
        # 1. Visible window with "moonlight" in title (normal idle state)
        hwnd = find_window(pid, [], ["moonlight"], match_any_pid=False)
        if hwnd:
            return hwnd
        # 2. Any visible window for this PID (streaming changes the title)
        hwnd = find_window(pid, [], [], match_any_pid=False)
        if hwnd:
            return hwnd
        # 3. Minimized/iconic window — fullscreen games often push Moonlight
        #    to the taskbar.  move_window() will restore it before repositioning.
        hwnd = find_window(pid, [], [], match_any_pid=False, include_iconic=True)
        if hwnd:
            try:
                import win32gui as _wg
                title = _wg.GetWindowText(hwnd)
            except Exception:
                title = "?"
            print(f"[re-stack] DEBUG moonlight: found minimized window pid={pid} title={title!r}")
            return hwnd
        print(f"[re-stack] DEBUG moonlight: pid={pid} — no window found (visible or iconic)")
    return None


def _crt_fallback_rect(crt_config_path: Optional[str]) -> Tuple[int, int, int, int]:
    if crt_config_path:
        try:
            with open(crt_config_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            li = cfg.get("launcher_integration", {})
            return (
                int(li.get("x", -1211)),
                int(li.get("y", 43)),
                int(li.get("w", 1057)),
                int(li.get("h", 835)),
            )
        except Exception:
            pass
    return (-1211, 43, 1057, 835)


def _intersection_area(
    a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0
    return (ix2 - ix1) * (iy2 - iy1)


def _nearest_wrapped_offset(delta: int, span: int) -> int:
    """Normalize an offset to the nearest equivalent position in span-sized steps."""
    if span <= 0:
        return delta
    return delta - round(delta / span) * span


def _maybe_reanchor_crt_rect(
    rect: Tuple[int, int, int, int],
    crt_display_rect: Optional[Tuple[int, int, int, int]],
) -> Tuple[int, int, int, int]:
    """Adjust a saved absolute rect when desktop origin shifts after primary changes.

    The saved Moonlight CRT rect is often tuned relative to the CRT display (small
    x/y offsets to hide edges). When Windows re-roots the desktop, absolute x/y can
    shift by whole-monitor widths/heights. This re-anchors the rect to the current
    CRT monitor if doing so improves overlap with the CRT display bounds.
    """
    if crt_display_rect is None:
        return rect

    rx, ry, rw, rh = rect
    dx, dy, dw, dh = crt_display_rect
    if dw <= 0 or dh <= 0:
        return rect

    current_overlap = _intersection_area(rect, crt_display_rect)
    rel_x = _nearest_wrapped_offset(rx - dx, dw)
    rel_y = _nearest_wrapped_offset(ry - dy, dh)
    candidate = (dx + rel_x, dy + rel_y, rw, rh)
    candidate_overlap = _intersection_area(candidate, crt_display_rect)

    if candidate_overlap > current_overlap:
        print(
            "[re-stack] Re-anchored configured CRT rect to current CRT display origin: "
            f"x={candidate[0]}, y={candidate[1]}, w={candidate[2]}, h={candidate[3]} "
            f"(was x={rx}, y={ry}; CRT x={dx}, y={dy}, w={dw}, h={dh})"
        )
        return candidate

    return rect


def move_moonlight_to_crt(
    crt_tokens: List[str],
    moonlight_dir: str,
    crt_config_path: Optional[str] = None,
    crt_rect: Optional[Tuple[int, int, int, int]] = None,
) -> bool:
    """Move the Moonlight window to the CRT display bounds.

    Resolution order:
      1. crt_rect override from re_stack_config.json moonlight.crt_rect (if set)
      2. Live CRT display bounds via display enumeration
      3. launcher_integration rect from crt_config.json (legacy fallback)
    """
    live_crt_rect = get_crt_display_rect(crt_tokens)
    if crt_rect is not None:
        x, y, w, h = _maybe_reanchor_crt_rect(crt_rect, live_crt_rect)
        print(f"[re-stack] Using configured CRT rect: x={x}, y={y}, w={w}, h={h}")
    else:
        rect = live_crt_rect
        if rect is None:
            x, y, w, h = _crt_fallback_rect(crt_config_path)
            print(
                f"[re-stack] CRT display not detected; using fallback rect: "
                f"x={x}, y={y}, w={w}, h={h}"
            )
        else:
            x, y, w, h = rect

    for _ in range(30):
        hwnd = find_moonlight_window(moonlight_dir)
        if hwnd:
            try:
                move_window(hwnd, x, y, w, h, strip_caption=False)
                print(
                    f"[re-stack] Moonlight moved to CRT display: "
                    f"x={x}, y={y}, w={w}, h={h}"
                )
                return True
            except Exception as e:
                print(f"[re-stack] Failed moving Moonlight window: {e}")
                return False
        time.sleep(0.5)

    print("[re-stack] Could not find Moonlight window to move.")
    return False


def move_moonlight_to_internal(
    internal_tokens: List[str],
    moonlight_dir: str,
    idle_rect: Optional[Tuple[int, int, int, int]] = None,
) -> bool:
    """Move the Moonlight window back to the idle (internal display) position.

    Resolution order:
      1. idle_rect from re_stack_config.json moonlight.idle_rect (if set)
      2. Full bounds of the internal display via display enumeration
    """
    if idle_rect is not None:
        x, y, w, h = idle_rect
        print(f"[re-stack] Using configured idle rect: x={x}, y={y}, w={w}, h={h}")
    else:
        rect = get_crt_display_rect(internal_tokens)
        if rect is None:
            print("[re-stack] Could not detect internal display bounds; Moonlight not moved.")
            return False
        x, y, w, h = rect
    for _ in range(6):
        hwnd = find_moonlight_window(moonlight_dir)
        if hwnd:
            try:
                move_window(hwnd, x, y, w, h, strip_caption=False)
                print(
                    f"[re-stack] Moonlight moved to internal display: "
                    f"x={x}, y={y}, w={w}, h={h}"
                )
                return True
            except Exception as e:
                print(f"[re-stack] Failed moving Moonlight to internal display: {e}")
                return False
        time.sleep(0.5)
    print("[re-stack] Could not find Moonlight window to move to internal display.")
    return False
