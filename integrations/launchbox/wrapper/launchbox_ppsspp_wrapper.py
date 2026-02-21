import json
import os
import subprocess
import sys
import time
from typing import Optional, Tuple

import win32con
import win32gui
import win32process


Rect = Tuple[int, int, int, int]
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")
SESSION_PROFILE_PATH = os.path.join(PROJECT_ROOT, "profiles", "ppsspp-session.json")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    # Rect comes from ppsspp-session.json — single source of truth shared with session watcher.
    with open(SESSION_PROFILE_PATH, "r", encoding="utf-8-sig") as f:
        profile = json.load(f)
    cfg.setdefault("ppsspp", {})
    cfg["ppsspp"]["x"] = profile["x"]
    cfg["ppsspp"]["y"] = profile["y"]
    cfg["ppsspp"]["w"] = profile["w"]
    cfg["ppsspp"]["h"] = profile["h"]
    return cfg


def resolve_ppsspp_exe(cfg: dict) -> Tuple[str, str]:
    p = cfg.get("ppsspp", {})
    configured = p.get("path")
    if configured and os.path.exists(configured):
        return configured, p.get("dir", os.path.dirname(configured))

    candidates = [
        r"D:\Emulators\PPSSPPWindowsGold\PPSSPPWindows64.exe",
        r"D:\Emulators\PPSSPPWindowsGold\PPSSPPWindows.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            return exe, os.path.dirname(exe)
    raise FileNotFoundError("PPSSPP executable not found in configured path or defaults.")


def target_rect(cfg: dict) -> Tuple[int, int, int, int]:
    p = cfg.get("ppsspp", {})
    return (
        int(p["x"]),
        int(p["y"]),
        int(p["w"]),
        int(p["h"]),
    )


def enum_windows():
    hwnds = []

    def callback(hwnd: int, _lparam: int):
        hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(callback, 0)
    return hwnds


def get_rect(hwnd: int) -> Rect:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t


def find_window_for_pid(pid: int) -> Optional[int]:
    best = None
    best_area = -1
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                continue
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid != pid:
                continue
            l, t, w, h = get_rect(hwnd)
            area = w * h
            if area > best_area:
                best = hwnd
                best_area = area
        except Exception:
            continue
    return best


def move_window(hwnd: int, x: int, y: int, w: int, h: int, pulse: bool) -> None:
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)
    if pulse:
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, x, y, w + 1, h + 1, win32con.SWP_SHOWWINDOW
        )
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)


def main() -> int:
    cfg = load_config()
    exe, cwd = resolve_ppsspp_exe(cfg)
    x, y, w, h = target_rect(cfg)

    args = [exe, *sys.argv[1:]]
    proc = subprocess.Popen(args, cwd=cwd)

    start = time.time()
    pulsed = False
    max_lock_seconds = 12.0
    settle_seconds = 2.0
    lock_active = True
    last_not_target = time.time()

    while proc.poll() is None:
        elapsed = time.time() - start
        if lock_active and elapsed <= max_lock_seconds:
            hwnd = find_window_for_pid(proc.pid)
            if hwnd:
                try:
                    l, t, cw, ch = get_rect(hwnd)
                    if (l, t, cw, ch) != (x, y, w, h):
                        last_not_target = time.time()
                        pulse = (not pulsed) and (elapsed < 8.0)
                        move_window(hwnd, x, y, w, h, pulse)
                        if pulse:
                            pulsed = True
                    elif (time.time() - last_not_target) >= settle_seconds:
                        lock_active = False
                except Exception:
                    pass
        time.sleep(0.1 if elapsed < 8.0 else 0.4)

    return proc.returncode if proc.returncode is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())

