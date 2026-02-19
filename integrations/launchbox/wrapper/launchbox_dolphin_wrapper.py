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


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_dolphin_exe(cfg: dict) -> Tuple[str, str]:
    d = cfg.get("dolphin", {})
    configured = d.get("path")
    if configured and os.path.exists(configured):
        return configured, d.get("dir", os.path.dirname(configured))

    default = r"D:\Dolphin-x64\Dolphin.exe"
    if os.path.exists(default):
        return default, os.path.dirname(default)
    raise FileNotFoundError("Dolphin executable not found in configured path or defaults.")


def target_rect(cfg: dict) -> Tuple[int, int, int, int]:
    li = cfg.get("launcher_integration", {})
    r = cfg.get("retroarch", {})
    return (
        int(li.get("x", r.get("x", -1211))),
        int(li.get("y", r.get("y", 43))),
        int(li.get("w", r.get("w", 1057))),
        int(li.get("h", r.get("h", 835))),
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
    exe, cwd = resolve_dolphin_exe(cfg)
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
