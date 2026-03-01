"""Shared Win32 window helpers used across session launchers."""
import time
from typing import List, Optional, Set, Tuple

import win32con
import win32gui
import win32process

try:
    import psutil
except ImportError:
    psutil = None


Rect = Tuple[int, int, int, int]


def find_existing_pids(process_names: List[str]) -> List[int]:
    """Return running PIDs whose process name matches any entry in process_names."""
    if psutil is None:
        return []
    target = {n.lower() for n in process_names}
    pids: List[int] = []
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if proc.info["name"].lower() in target:
                pids.append(proc.info["pid"])
        except Exception:
            continue
    return pids


def pids_for_root(root_pid: int) -> Set[int]:
    """Return the PID set of root_pid and all its descendants."""
    pids = {root_pid}
    if psutil is None:
        return pids
    try:
        for child in psutil.Process(root_pid).children(recursive=True):
            pids.add(child.pid)
    except Exception:
        pass
    return pids


def enum_windows() -> List[int]:
    """Return a list of all top-level window handles."""
    hwnds: List[int] = []

    def cb(hwnd, _):
        hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(cb, 0)
    return hwnds


def get_rect(hwnd: int) -> Rect:
    """Return (left, top, width, height) for the given window."""
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t


def get_window_title(hwnd: int) -> str:
    """Return the window title text for the given HWND."""
    try:
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return ""


def find_window(
    pid: Optional[int],
    class_contains: List[str],
    title_contains: List[str],
    match_any_pid: bool = False,
    include_iconic: bool = False,
) -> Optional[int]:
    """Find the largest visible window matching the given filters.

    If pid is given and match_any_pid is False, only windows whose thread PID
    belongs to the pid's process tree are considered.  If match_any_pid is True
    the PID filter is skipped entirely.

    Set include_iconic=True to also consider minimized (taskbar) windows —
    useful when a fullscreen game pushes the target window to the taskbar.

    Returns the HWND of the best match, or None.
    """
    pids = pids_for_root(pid) if (pid is not None and not match_any_pid) else None
    class_filters = [x.lower() for x in class_contains if x]
    title_filters = [x.lower() for x in title_contains if x]
    best, best_area = None, -1
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd):
                continue
            if not include_iconic and win32gui.IsIconic(hwnd):
                continue
            if pids is not None:
                _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                if win_pid not in pids:
                    continue
            cls = win32gui.GetClassName(hwnd).lower()
            title = win32gui.GetWindowText(hwnd).lower()
            if class_filters and not any(f in cls for f in class_filters):
                continue
            if title_filters and not any(f in title for f in title_filters):
                continue
            l, t, w, h = get_rect(hwnd)
            area = w * h
            if area > best_area:
                best, best_area = hwnd, area
        except Exception:
            continue
    return best


def is_window_fullscreen(hwnd: int) -> bool:
    """Return True if the window appears to be in fullscreen or borderless mode.

    Checks two signals (either is sufficient):
    1. WS_CAPTION absent from the window style — fullscreen strips the title bar.
    2. Window rect matches the monitor it is on exactly.
    """
    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if not (style & win32con.WS_CAPTION):
            return True
    except Exception:
        pass
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        monitor = win32gui.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        info = win32gui.GetMonitorInfo(monitor)
        ml, mt, mr, mb = info["Monitor"]
        if l == ml and t == mt and r == mr and b == mb:
            return True
    except Exception:
        pass
    return False


def move_window(
    hwnd: int, x: int, y: int, w: int, h: int, strip_caption: bool = False
) -> None:
    """Move and resize a window.  Restores maximised windows first.

    If strip_caption is True, removes WS_CAPTION from the window style before
    repositioning so the frame does not consume space inside the given rect.
    """
    try:
        if win32gui.IsIconic(hwnd):
            # Minimized (taskbar) — restore before repositioning.
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.15)
        elif win32gui.IsZoomed(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    if strip_caption:
        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            if style & win32con.WS_CAPTION:
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style & ~win32con.WS_CAPTION)
        except Exception:
            pass
    flags = win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, flags)
