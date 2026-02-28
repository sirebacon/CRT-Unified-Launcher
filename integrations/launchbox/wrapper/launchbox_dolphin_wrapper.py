import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional, Tuple

import win32con
import win32gui
import win32process


Rect = Tuple[int, int, int, int]
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")
SESSION_PROFILE_PATH = os.path.join(PROJECT_ROOT, "profiles", "dolphin-session.json")
STOP_ENFORCE_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")
DEBUG_LOG_PATH = os.path.join(PROJECT_ROOT, "dolphin_wrapper_debug.log")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    # Rect comes from dolphin-session.json — single source of truth shared with session watcher.
    with open(SESSION_PROFILE_PATH, "r", encoding="utf-8-sig") as f:
        profile = json.load(f)
    cfg.setdefault("dolphin", {})
    cfg["dolphin"]["x"] = profile["x"]
    cfg["dolphin"]["y"] = profile["y"]
    cfg["dolphin"]["w"] = profile["w"]
    cfg["dolphin"]["h"] = profile["h"]
    return cfg


def resolve_dolphin_exe(cfg: dict) -> Tuple[str, str]:
    d = cfg.get("dolphin", {})
    configured = d.get("path")
    if configured and os.path.exists(configured):
        return configured, d.get("dir", os.path.dirname(configured))

    default = r"D:\Emulators\Dolphin-x64\Dolphin.exe"
    if os.path.exists(default):
        return default, os.path.dirname(default)
    raise FileNotFoundError("Dolphin executable not found in configured path or defaults.")


def target_rect(cfg: dict) -> Tuple[int, int, int, int]:
    d = cfg.get("dolphin", {})
    return (
        int(d["x"]),
        int(d["y"]),
        int(d["w"]),
        int(d["h"]),
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


def log_debug(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] {message}\n"
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(f"[DolphinWrapper] {message}")


def main() -> int:
    cfg = load_config()
    exe, cwd = resolve_dolphin_exe(cfg)
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

    # Ignore stale stop flags from previous sessions.
    try:
        if os.path.exists(STOP_ENFORCE_FLAG):
            os.remove(STOP_ENFORCE_FLAG)
            log_debug(f"Removed stale stop flag: {STOP_ENFORCE_FLAG}")
    except Exception:
        pass

    # Force windowed mode. Strip any Dolphin.Display.Fullscreen override LaunchBox may pass
    # so the wrapper's Fullscreen=False is always the last word, regardless of arg order.
    passthrough = []
    incoming = sys.argv[1:]
    i = 0
    while i < len(incoming):
        if (
            incoming[i] == "-C"
            and i + 1 < len(incoming)
            and incoming[i + 1].lower().startswith("dolphin.display.fullscreen=")
        ):
            i += 2  # skip the conflicting pair
        else:
            passthrough.append(incoming[i])
            i += 1
    args = [exe, "-C", "Dolphin.Display.Fullscreen=False", *passthrough]
    log_debug(f"Launch args: {args}")
    log_debug(f"Target rect: x={x}, y={y}, w={w}, h={h}")
    log_debug(f"Primary rect: x={px}, y={py}, w={pw}, h={ph}")
    proc = subprocess.Popen(args, cwd=cwd)
    log_debug(f"Spawned Dolphin PID: {proc.pid}")

    start = time.time()
    pulsed = False
    # Keep lock active while game loads; Dolphin can resize/rebuild windows mid-startup.
    max_lock_seconds = 120.0
    lock_active = True
    last_rect: Optional[Rect] = None
    last_hwnd: Optional[int] = None
    last_miss_log = 0.0
    while proc.poll() is None:
        elapsed = time.time() - start
        if os.path.exists(STOP_ENFORCE_FLAG):
            if lock_active:
                log_debug("Stop flag detected; disabling enforcement.")
            lock_active = False
        if lock_active and elapsed <= max_lock_seconds:
            hwnd = find_window_for_pid(proc.pid)
            if hwnd:
                if last_hwnd != hwnd:
                    log_debug(f"Tracking HWND: {hwnd}")
                    last_hwnd = hwnd
                try:
                    l, t, cw, ch = get_rect(hwnd)
                    curr_rect = (l, t, cw, ch)
                    if last_rect != curr_rect:
                        log_debug(f"Current rect: x={l}, y={t}, w={cw}, h={ch}")
                        last_rect = curr_rect
                    # If watcher moved Dolphin back to primary on Ctrl+C, stop enforcing CRT.
                    if curr_rect == (px, py, pw, ph):
                        log_debug("Window moved to primary rect; disabling enforcement.")
                        lock_active = False
                        continue
                    if curr_rect != (x, y, w, h):
                        pulse = (not pulsed) and (elapsed < 8.0)
                        log_debug(
                            "Applying target rect "
                            f"(pulse={pulse}): x={x}, y={y}, w={w}, h={h}"
                        )
                        move_window(hwnd, x, y, w, h, pulse)
                        if pulse:
                            pulsed = True
                except Exception:
                    log_debug("Exception while reading/moving window; continuing.")
                    pass
            elif (elapsed - last_miss_log) >= 2.0:
                log_debug("No Dolphin HWND found for PID yet.")
                last_miss_log = elapsed
        time.sleep(0.1 if elapsed < 8.0 else 0.4)

    rc = proc.returncode if proc.returncode is not None else 0
    log_debug(f"Dolphin process exited with code: {rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

