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
STOP_ENFORCE_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_pcsx2_exe(cfg: dict) -> Tuple[str, str]:
    p = cfg.get("pcsx2", {})
    configured = p.get("path")
    if configured and os.path.exists(configured):
        return configured, p.get("dir", os.path.dirname(configured))

    candidates = [
        r"D:\Pcsx2\pcsx2-qt.exe",
        r"D:\Pcsx2\pcsx2.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            return exe, os.path.dirname(exe)
    raise FileNotFoundError("PCSX2 executable not found in configured path or defaults.")


def target_rect(cfg: dict) -> Tuple[int, int, int, int]:
    li = cfg.get("launcher_integration", {})
    r = cfg.get("retroarch", {})
    p = cfg.get("pcsx2", {})
    return (
        int(p.get("x", li.get("x", r.get("x", -1211)))),
        int(p.get("y", li.get("y", r.get("y", 43)))),
        int(p.get("w", li.get("w", r.get("w", 1057)))),
        int(p.get("h", li.get("h", r.get("h", 835)))),
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
    exe, cwd = resolve_pcsx2_exe(cfg)
    x, y, w, h = target_rect(cfg)
    primary = cfg.get("launcher_integration", {}).get(
        "primary_on_exit", {"x": 100, "y": 100, "w": 1280, "h": 720}
    )
    px, py, pw, ph = (
        int(primary.get("x", 100)),
        int(primary.get("y", 100)),
        int(primary.get("w", 1280)),
        int(primary.get("h", 720)),
    )

    args = [exe, *sys.argv[1:]]
    proc = subprocess.Popen(args, cwd=cwd)

    start = time.time()
    pulsed = False
    # PCSX2 can rebuild/reposition its window multiple times while content loads.
    # Keep startup lock active longer so it cannot drift back to primary mid-load.
    max_lock_seconds = 120.0
    lock_active = True

    while proc.poll() is None:
        elapsed = time.time() - start
        if os.path.exists(STOP_ENFORCE_FLAG):
            lock_active = False
        if lock_active and elapsed <= max_lock_seconds:
            hwnd = find_window_for_pid(proc.pid)
            if hwnd:
                try:
                    l, t, cw, ch = get_rect(hwnd)
                    # If watcher moved PCSX2 back to primary on Ctrl+C, stop enforcing CRT.
                    if (l, t, cw, ch) == (px, py, pw, ph):
                        lock_active = False
                        continue
                    if (l, t, cw, ch) != (x, y, w, h):
                        pulse = (not pulsed) and (elapsed < 8.0)
                        move_window(hwnd, x, y, w, h, pulse)
                        if pulse:
                            pulsed = True
                except Exception:
                    pass
        time.sleep(0.1 if elapsed < 8.0 else 0.4)

    return proc.returncode if proc.returncode is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
