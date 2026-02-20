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
SESSION_PROFILE_PATH = os.path.join(PROJECT_ROOT, "profiles", "retroarch-session.json")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)["retroarch"]
    # Rect comes from retroarch-session.json so there is a single source of truth
    # shared with the session watcher. Executable/dir/config remain in crt_config.json.
    with open(SESSION_PROFILE_PATH, "r", encoding="utf-8-sig") as f:
        profile = json.load(f)
    cfg["x"] = profile["x"]
    cfg["y"] = profile["y"]
    cfg["w"] = profile["w"]
    cfg["h"] = profile["h"]
    return cfg


def has_config_arg(argv) -> bool:
    for arg in argv:
        if arg == "--config":
            return True
        if arg.startswith("--config="):
            return True
        if arg == "-c":
            return True
        if arg == "--appendconfig":
            return True
        if arg.startswith("--appendconfig="):
            return True
    return False


def get_rect(hwnd: int) -> Rect:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t


def enum_windows():
    hwnds = []

    def callback(hwnd: int, _lparam: int):
        hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(callback, 0)
    return hwnds


def find_hwnd_for_pid(pid: int) -> Optional[int]:
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd):
                continue
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid != pid:
                continue
            if win32gui.GetClassName(hwnd) == "RetroArch":
                return hwnd
        except Exception:
            continue
    return None


def move_window(hwnd: int, x: int, y: int, w: int, h: int, pulse: bool) -> None:
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)
    if pulse:
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, x, y, w + 1, h + 1, win32con.SWP_SHOWWINDOW
        )
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)


def main() -> int:
    cfg = load_config()
    crt_cfg = cfg.get("launchbox_config", r"D:\Emulators\RetroArch-Win64\retroarch_crt.cfg")
    passthrough = list(sys.argv[1:])

    args = [cfg["path"]]
    if os.path.exists(crt_cfg) and not has_config_arg(passthrough):
        args.extend(["--config", crt_cfg])
    args.extend(passthrough)

    proc = subprocess.Popen(args, cwd=cfg["dir"])
    start = time.time()
    pulsed = False
    max_lock_seconds = 15.0
    settle_seconds = 2.0
    lock_active = True
    last_not_target = time.time()

    while proc.poll() is None:
        elapsed = time.time() - start
        if lock_active and elapsed <= max_lock_seconds:
            hwnd = find_hwnd_for_pid(proc.pid)
            if hwnd:
                try:
                    rect = get_rect(hwnd)
                    target = (cfg["x"], cfg["y"], cfg["w"], cfg["h"])
                    curr = (rect[0], rect[1], rect[2], rect[3])
                    if curr != target:
                        last_not_target = time.time()
                        pulse = (not pulsed) and (elapsed < 10.0)
                        move_window(hwnd, cfg["x"], cfg["y"], cfg["w"], cfg["h"], pulse)
                        if pulse:
                            pulsed = True
                    else:
                        if (time.time() - last_not_target) >= settle_seconds:
                            lock_active = False
                except Exception:
                    pass
        time.sleep(0.1 if elapsed < 10.0 else 0.5)

    return proc.returncode if proc.returncode is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())

