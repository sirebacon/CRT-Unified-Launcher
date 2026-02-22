"""Moonlight process management and window placement."""

import json
import os
import subprocess
import time
from typing import List, Optional, Tuple

from session.display_api import get_crt_display_rect
from session.window_utils import find_window, move_window

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


def find_moonlight_window(moonlight_dir: str) -> Optional[int]:
    for pid in moonlight_pids(moonlight_dir):
        hwnd = find_window(pid, [], ["moonlight"], match_any_pid=False)
        if hwnd:
            return hwnd
        hwnd = find_window(pid, [], [], match_any_pid=False)
        if hwnd:
            return hwnd
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


def move_moonlight_to_crt(
    crt_tokens: List[str],
    moonlight_dir: str,
    crt_config_path: Optional[str] = None,
) -> bool:
    """Move the Moonlight window to the CRT display bounds.

    Detects CRT position/size via live display enumeration. Falls back to
    crt_config_path launcher_integration rect if enumeration fails.
    """
    rect = get_crt_display_rect(crt_tokens)
    if rect is None:
        x, y, w, h = _crt_fallback_rect(crt_config_path)
        print(
            f"[re-stack] CRT display not detected; using configured rect: "
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
