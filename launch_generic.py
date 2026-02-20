"""Session-mode generic launcher.

Loads a profile, attaches to an existing process or launches a new one,
then locks the window to the CRT rect indefinitely until Ctrl+C.

On Ctrl+C: restores the window to the primary monitor and exits cleanly.

Usage:
    python launch_generic.py --profile-file profiles/retroarch-session.json
    python launch_generic.py --profile-file profiles/retroarch-session.json --debug
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from typing import List, Optional

import win32gui

from session.window_utils import Rect, find_existing_pids, find_window, get_rect, move_window


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")


def _apply_dpi_awareness(profile_path: str) -> None:
    """Read dpi_aware from the profile and set process DPI awareness if requested.

    Must be called before any window API call. Reads only the dpi_aware key so
    the full profile load can happen normally afterward.
    """
    try:
        with open(profile_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if data.get("dpi_aware"):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
    except Exception:
        pass


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


def dbg(enabled: bool, msg: str) -> None:
    if enabled:
        print(f"  [dbg] {msg}")


def main() -> int:
    args = parse_args()
    _apply_dpi_awareness(args.profile_file)

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
    strip_caption: bool = bool(profile.get("strip_caption", False))
    match_any_pid: bool = bool(profile.get("match_any_pid", False))

    # Attach to existing process or launch a new one.
    pid: Optional[int] = None
    proc = None

    if process_names:
        candidate_pids = find_existing_pids(process_names)
        for cand_pid in candidate_pids:
            if find_window(cand_pid, class_contains, title_contains):
                pid = cand_pid
                break
        if pid is None and candidate_pids:
            pid = candidate_pids[0]

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
            if find_window(pid, class_contains, title_contains, match_any_pid):
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

            hwnd = find_window(pid, class_contains, title_contains, match_any_pid)
            if hwnd:
                if hwnd != last_hwnd:
                    dbg(args.debug, f"Tracking HWND {hwnd}")
                    last_hwnd = hwnd
                try:
                    curr = get_rect(hwnd)
                    if curr != (x, y, w, h):
                        dbg(args.debug, f"Snap {curr} -> ({x},{y},{w},{h})")
                        move_window(hwnd, x, y, w, h, strip_caption)
                except Exception:
                    pass
            elif args.debug:
                dbg(args.debug, "No matching window found for attached PID yet.")

            time.sleep(poll)

    except KeyboardInterrupt:
        print(f"\n[{slug}] Ctrl+C — restoring to primary monitor...")
        hwnd = find_window(pid, class_contains, title_contains, match_any_pid)
        if hwnd:
            move_window(hwnd, px, py, pw, ph, strip_caption=False)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        print(f"[{slug}] Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
