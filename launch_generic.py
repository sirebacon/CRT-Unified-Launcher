"""Session-mode generic launcher.

Loads a profile, attaches to an existing process or launches a new one,
then locks the window to the CRT rect indefinitely until Ctrl+C.

On Ctrl+C: restores the window to the primary monitor and exits cleanly.

Usage:
    python launch_generic.py --profile-file profiles/retroarch-session.json
    python launch_generic.py --profile-file profiles/retroarch-session.json --debug
"""
import argparse
import json
import os
import subprocess
import sys
import time
from typing import List, Optional, Set, Tuple

import win32con
import win32gui
import win32process

try:
    import psutil
except Exception:
    psutil = None


Rect = Tuple[int, int, int, int]
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Session-mode locker. Attaches to or launches an app, "
                    "locks it to CRT rect indefinitely. Ctrl+C restores to primary."
    )
    p.add_argument("--profile-file", required=True, help="Path to a profile JSON file.")
    p.add_argument("--debug", action="store_true", help="Print detailed tracking output.")
    return p.parse_args()


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_rect(profile: dict, cfg: dict) -> Rect:
    li = cfg.get("launcher_integration", {})
    r = cfg.get("retroarch", {})
    return (
        int(profile.get("x", li.get("x", r.get("x", -1211)))),
        int(profile.get("y", li.get("y", r.get("y", 43)))),
        int(profile.get("w", li.get("w", r.get("w", 1057)))),
        int(profile.get("h", li.get("h", r.get("h", 835)))),
    )


def primary_rect(cfg: dict) -> Rect:
    p = cfg.get("launcher_integration", {}).get(
        "primary_on_exit", {"x": 100, "y": 100, "w": 1280, "h": 720}
    )
    return (int(p["x"]), int(p["y"]), int(p["w"]), int(p["h"]))


def find_existing_pid(process_names: List[str]) -> Optional[int]:
    """Return the PID of the first running process matching any name in the list."""
    if psutil is None:
        return None
    target = {n.lower() for n in process_names}
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if proc.info["name"].lower() in target:
                return proc.info["pid"]
        except Exception:
            continue
    return None


def pids_for_root(root_pid: int) -> Set[int]:
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
    hwnds: List[int] = []

    def cb(hwnd, _):
        hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(cb, 0)
    return hwnds


def get_rect(hwnd: int) -> Rect:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t


def find_window(pid: int, class_contains: List[str], title_contains: List[str]) -> Optional[int]:
    pids = pids_for_root(pid)
    class_filters = [x.lower() for x in class_contains if x]
    title_filters = [x.lower() for x in title_contains if x]
    best, best_area = None, -1
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                continue
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


def move_window(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)


def dbg(enabled: bool, msg: str) -> None:
    if enabled:
        print(f"  [dbg] {msg}")


def main() -> int:
    args = parse_args()

    try:
        cfg = load_config()
        profile = load_profile(args.profile_file)
    except Exception as e:
        print(f"[Error] {e}")
        return 1

    slug = os.path.splitext(os.path.basename(args.profile_file))[0]
    exe = profile.get("path", "")
    cwd = profile.get("dir", os.path.dirname(exe) if exe else "")
    x, y, w, h = resolve_rect(profile, cfg)
    px, py, pw, ph = primary_rect(cfg)
    process_names: List[str] = profile.get("process_name", [])
    class_contains: List[str] = profile.get("class_contains", [])
    title_contains: List[str] = profile.get("title_contains", [])
    poll = float(profile.get("poll_slow", 0.4))

    # Attach to existing process or launch a new one.
    pid: Optional[int] = None
    proc = None

    if process_names:
        pid = find_existing_pid(process_names)

    if pid:
        print(f"[{slug}] Found running process (PID {pid}) — attaching.")
        dbg(args.debug, f"Attached to PID {pid}")
    else:
        if not exe or not os.path.exists(exe):
            print(f"[{slug}] Executable not found: {exe}")
            return 1
        print(f"[{slug}] Launching {exe} ...")
        proc = subprocess.Popen([exe], cwd=cwd if cwd else None)
        pid = proc.pid
        dbg(args.debug, f"Spawned PID {pid}")
        print(f"[{slug}] Waiting for window...", end="", flush=True)
        for _ in range(40):
            time.sleep(0.5)
            if find_window(pid, class_contains, title_contains):
                break
            print(".", end="", flush=True)
        print()

    print(f"[{slug}] Locker ACTIVE — locked to ({x}, {y}, {w}x{h}).  Ctrl+C to stop.")

    last_hwnd: Optional[int] = None

    try:
        while True:
            # If we launched it ourselves, exit when it closes.
            if proc is not None and proc.poll() is not None:
                print(f"\n[{slug}] Process exited (code {proc.returncode}).")
                break

            hwnd = find_window(pid, class_contains, title_contains)
            if hwnd:
                if hwnd != last_hwnd:
                    dbg(args.debug, f"Tracking HWND {hwnd}")
                    last_hwnd = hwnd
                try:
                    curr = get_rect(hwnd)
                    if curr != (x, y, w, h):
                        dbg(args.debug, f"Snap {curr} -> ({x},{y},{w},{h})")
                        move_window(hwnd, x, y, w, h)
                except Exception:
                    pass

            time.sleep(poll)

    except KeyboardInterrupt:
        print(f"\n[{slug}] Ctrl+C — restoring to primary monitor...")
        hwnd = find_window(pid, class_contains, title_contains)
        if hwnd:
            move_window(hwnd, px, py, pw, ph)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        print(f"[{slug}] Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
