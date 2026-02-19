import ctypes
import json
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

import psutil
import win32con
import win32gui
import win32process


Rect = Tuple[int, int, int, int]


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()


def load_config() -> Tuple[Dict, Dict]:
    try:
        with open("crt_config.json", "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"Error loading crt_config.json: {e}")
        sys.exit(1)

    retro = raw.get("retroarch", {})
    integration = raw.get("launcher_integration", {})

    target = {
        "x": integration.get("x", retro.get("x", 0)),
        "y": integration.get("y", retro.get("y", 0)),
        "w": integration.get("w", retro.get("w", 1280)),
        "h": integration.get("h", retro.get("h", 720)),
    }

    defaults = {
        "enabled": integration.get("enabled", True),
        "poll_seconds": float(integration.get("poll_seconds", 0.5)),
        "target_processes": set(
            p.lower()
            for p in integration.get(
                "target_processes",
                [
                    "retroarch.exe",
                    "dolphin.exe",
                    "ppssppwindows64.exe",
                    "ppssppwindows.exe",
                ],
            )
        ),
        "target_parent_processes": set(
            p.lower()
            for p in integration.get(
                "target_parent_processes",
                ["steam.exe", "galaxyclient.exe", "goggalaxy.exe"],
            )
        ),
        "ignore_processes": set(
            p.lower()
            for p in integration.get(
                "ignore_processes",
                [
                    "launchbox.exe",
                    "bigbox.exe",
                    "explorer.exe",
                    "dwm.exe",
                    "applicationframehost.exe",
                    "startmenuexperiencehost.exe",
                    "searchhost.exe",
                ],
            )
        ),
        "primary_on_exit": integration.get(
            "primary_on_exit", {"x": 100, "y": 100, "w": 1280, "h": 720}
        ),
        "keep_cursor_visible": integration.get("keep_cursor_visible", True),
        "debug_retroarch": integration.get("debug_retroarch", False),
    }
    return target, defaults


def get_window_process(hwnd: int) -> Optional[psutil.Process]:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return None
        return psutil.Process(pid)
    except Exception:
        return None


def process_name(proc: Optional[psutil.Process]) -> str:
    if proc is None:
        return ""
    try:
        return proc.name().lower()
    except Exception:
        return ""


def ancestor_names(proc: Optional[psutil.Process], depth: int = 8) -> List[str]:
    names: List[str] = []
    current = proc
    for _ in range(depth):
        if current is None:
            break
        try:
            current = current.parent()
            if current is None:
                break
            names.append(current.name().lower())
        except Exception:
            break
    return names


def get_rect(hwnd: int) -> Rect:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t


def find_retroarch_hwnds() -> List[int]:
    hwnds: List[int] = []
    seen: Set[int] = set()

    def add(hwnd: int) -> None:
        if hwnd and hwnd not in seen:
            seen.add(hwnd)
            hwnds.append(hwnd)

    direct = win32gui.FindWindow("RetroArch", None)
    if direct:
        add(direct)

    for hwnd in enum_windows():
        try:
            if not is_candidate_window(hwnd):
                continue
            cls = win32gui.GetClassName(hwnd).lower()
            title = win32gui.GetWindowText(hwnd).lower()
        except Exception:
            continue

        proc = get_window_process(hwnd)
        pname = process_name(proc)

        if cls == "retroarch" or "retroarch" in title or pname == "retroarch.exe":
            add(hwnd)

    return hwnds


def move_window(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    # Restore first so SetWindowPos works even if window was maximized/fullscreen-ish.
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass

    # Briefly force topmost to break sticky positioning, then return to normal z-order.
    flags = win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, x, y, w, h, flags)
    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, x, y, w, h, flags)


def move_window_retroarch(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    # Keep RetroArch behavior identical to launch_ra.py.
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)
    # LaunchBox can start RetroArch directly into content before we move it.
    # A tiny size pulse forces a viewport recalculation in that path.
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOP, x, y, w + 1, h + 1, win32con.SWP_SHOWWINDOW
    )
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)


def force_cursor_visible() -> None:
    # ShowCursor uses an internal counter; call enough times to force visibility.
    try:
        for _ in range(10):
            if ctypes.windll.user32.ShowCursor(True) >= 0:
                break
    except Exception:
        pass


def is_candidate_window(hwnd: int) -> bool:
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        return False
    if win32gui.IsIconic(hwnd):
        return False
    try:
        class_name = win32gui.GetClassName(hwnd)
    except Exception:
        return False
    if class_name in {"Shell_TrayWnd", "Progman", "WorkerW"}:
        return False
    l, t, w, h = get_rect(hwnd)
    if w < 320 or h < 240:
        return False
    return True


def should_move(hwnd: int, cfg: Dict) -> bool:
    if not is_candidate_window(hwnd):
        return False

    proc = get_window_process(hwnd)
    name = process_name(proc)
    if not name:
        return False
    if name in cfg["ignore_processes"]:
        return False
    if name in cfg["target_processes"]:
        return True

    for parent in ancestor_names(proc):
        if parent in cfg["target_parent_processes"] and name not in cfg["ignore_processes"]:
            return True
    return False


def enum_windows() -> List[int]:
    results: List[int] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        results.append(hwnd)
        return True

    win32gui.EnumWindows(callback, 0)
    return results


def windows_for_pid(pid: int) -> List[int]:
    matches: List[int] = []
    for hwnd in enum_windows():
        try:
            if not is_candidate_window(hwnd):
                continue
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid:
                matches.append(hwnd)
        except Exception:
            continue
    return matches


def find_retroarch_hwnds_by_pid() -> List[int]:
    hwnds: List[int] = []
    seen: Set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name != "retroarch.exe":
                continue
            for hwnd in windows_for_pid(int(proc.info["pid"])):
                if hwnd not in seen:
                    seen.add(hwnd)
                    hwnds.append(hwnd)
        except Exception:
            continue
    return hwnds


def main() -> None:
    set_dpi_aware()
    target, cfg = load_config()

    if not cfg["enabled"]:
        print("launcher_integration is disabled in crt_config.json")
        return

    print("LaunchBox/BigBox CRT watcher active")
    print(f"Target CRT: {target['x']}, {target['y']} {target['w']}x{target['h']}")
    print("Press Ctrl+C to stop.")

    moved: Dict[int, Rect] = {}
    poll = max(0.1, cfg["poll_seconds"])

    try:
        while True:
            if cfg.get("keep_cursor_visible", True):
                force_cursor_visible()

            for hwnd in enum_windows():
                if not should_move(hwnd, cfg):
                    continue

                try:
                    curr = get_rect(hwnd)
                except Exception:
                    continue

                if hwnd not in moved:
                    moved[hwnd] = curr

                if (
                    curr[0] != target["x"]
                    or curr[1] != target["y"]
                    or curr[2] != target["w"]
                    or curr[3] != target["h"]
                ):
                    move_window(hwnd, target["x"], target["y"], target["w"], target["h"])
            time.sleep(poll)
    except KeyboardInterrupt:
        primary = cfg["primary_on_exit"]
        print("\nStopping watcher. Returning moved windows to primary monitor...")
        if cfg.get("keep_cursor_visible", True):
            force_cursor_visible()

        # Also return any active RetroArch windows to primary.
        retro_hwnds = find_retroarch_hwnds_by_pid()
        if not retro_hwnds:
            retro_hwnds = find_retroarch_hwnds()
        for hwnd in retro_hwnds:
            try:
                if win32gui.IsWindow(hwnd):
                    move_window(
                        hwnd,
                        int(primary["x"]),
                        int(primary["y"]),
                        int(primary["w"]),
                        int(primary["h"]),
                    )
            except Exception:
                continue

        for hwnd, _orig in list(moved.items()):
            try:
                if win32gui.IsWindow(hwnd):
                    move_window(
                        hwnd,
                        int(primary["x"]),
                        int(primary["y"]),
                        int(primary["w"]),
                        int(primary["h"]),
                    )
            except Exception:
                continue


if __name__ == "__main__":
    main()
