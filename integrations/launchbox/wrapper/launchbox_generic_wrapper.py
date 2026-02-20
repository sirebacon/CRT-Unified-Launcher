import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Iterable, List, Optional, Set, Tuple

import win32con
import win32gui
import win32process

try:
    import psutil
except Exception:
    psutil = None


Rect = Tuple[int, int, int, int]
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")
STOP_ENFORCE_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generic LaunchBox CRT wrapper.")
    p.add_argument("--config-key", required=True, help="Key in crt_config.json (e.g. dolphin, ppsspp, pcsx2).")
    p.add_argument("--fallback-exe", action="append", default=[], help="Fallback exe path if config path is missing.")
    p.add_argument("--arg-pre", action="append", default=[], help="Arguments to prepend before LaunchBox passthrough args.")
    p.add_argument("--set", dest="set_values", action="append", default=[], help="Adds '-C KEY=VALUE' (repeatable).")
    p.add_argument("--max-lock-seconds", type=float, default=120.0, help="How long to enforce target rect.")
    p.add_argument("--fast-seconds", type=float, default=8.0, help="Fast poll period duration.")
    p.add_argument("--poll-fast", type=float, default=0.1, help="Poll interval during fast period.")
    p.add_argument("--poll-slow", type=float, default=0.4, help="Poll interval after fast period.")
    p.add_argument("--class-contains", action="append", default=[], help="Window class substring filter (repeatable).")
    p.add_argument("--title-contains", action="append", default=[], help="Window title substring filter (repeatable).")
    p.add_argument("--process-name", action="append", default=[], help="Extra process name filter for child windows.")
    p.add_argument("--debug", action="store_true", help="Enable debug logs to stdout and log file.")
    p.add_argument("--debug-log", default="", help="Custom debug log file path.")
    return p.parse_args()


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_exe(cfg: dict, config_key: str, fallback_exes: Iterable[str]) -> Tuple[str, str]:
    section = cfg.get(config_key, {})
    configured = section.get("path")
    if configured and os.path.exists(configured):
        return configured, section.get("dir", os.path.dirname(configured))

    for exe in fallback_exes:
        if os.path.exists(exe):
            return exe, os.path.dirname(exe)

    raise FileNotFoundError(
        f"Executable not found for config key '{config_key}'. Checked configured path and fallbacks."
    )


def target_rect(cfg: dict, config_key: str) -> Rect:
    section = cfg.get(config_key, {})
    li = cfg.get("launcher_integration", {})
    r = cfg.get("retroarch", {})
    return (
        int(section.get("x", li.get("x", r.get("x", -1211)))),
        int(section.get("y", li.get("y", r.get("y", 43)))),
        int(section.get("w", li.get("w", r.get("w", 1057)))),
        int(section.get("h", li.get("h", r.get("h", 835)))),
    )


def primary_rect(cfg: dict) -> Rect:
    primary = cfg.get("launcher_integration", {}).get(
        "primary_on_exit", {"x": 100, "y": 100, "w": 1280, "h": 720}
    )
    return (
        int(primary.get("x", 100)),
        int(primary.get("y", 100)),
        int(primary.get("w", 1280)),
        int(primary.get("h", 720)),
    )


def enum_windows() -> List[int]:
    hwnds: List[int] = []

    def callback(hwnd: int, _lparam: int):
        hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(callback, 0)
    return hwnds


def get_rect(hwnd: int) -> Rect:
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return l, t, r - l, b - t


def move_window(hwnd: int, x: int, y: int, w: int, h: int, pulse: bool) -> None:
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)
    if pulse:
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, x, y, w + 1, h + 1, win32con.SWP_SHOWWINDOW
        )
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)


def process_tree_pids(root_pid: int) -> Set[int]:
    pids: Set[int] = {root_pid}
    if psutil is None:
        return pids
    try:
        root = psutil.Process(root_pid)
        for child in root.children(recursive=True):
            pids.add(child.pid)
    except Exception:
        pass
    return pids


def process_names_for_pids(pids: Set[int]) -> Set[str]:
    names: Set[str] = set()
    if psutil is None:
        return names
    for pid in pids:
        try:
            names.add(psutil.Process(pid).name().lower())
        except Exception:
            continue
    return names


def find_best_window(
    target_pids: Set[int],
    class_contains: List[str],
    title_contains: List[str],
    allowed_process_names: Set[str],
) -> Optional[int]:
    class_filters = [x.lower() for x in class_contains if x]
    title_filters = [x.lower() for x in title_contains if x]

    best = None
    best_area = -1
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                continue
            _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
            if win_pid not in target_pids:
                if allowed_process_names:
                    if psutil is None:
                        continue
                    try:
                        pname = psutil.Process(win_pid).name().lower()
                    except Exception:
                        continue
                    if pname not in allowed_process_names:
                        continue
                else:
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
                best = hwnd
                best_area = area
        except Exception:
            continue
    return best


def log_debug(enabled: bool, log_path: str, message: str) -> None:
    if not enabled:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"[{ts}] {message}\n"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(f"[GenericWrapper] {message}")


def main() -> int:
    args = parse_args()
    cfg = load_config()
    exe, cwd = resolve_exe(cfg, args.config_key, args.fallback_exe)
    x, y, w, h = target_rect(cfg, args.config_key)
    px, py, pw, ph = primary_rect(cfg)
    debug_log = args.debug_log or os.path.join(PROJECT_ROOT, f"{args.config_key}_wrapper_debug.log")

    try:
        if os.path.exists(STOP_ENFORCE_FLAG):
            os.remove(STOP_ENFORCE_FLAG)
            log_debug(args.debug, debug_log, f"Removed stale stop flag: {STOP_ENFORCE_FLAG}")
    except Exception:
        pass

    launch_args: List[str] = [exe]
    for kv in args.set_values:
        launch_args.extend(["-C", kv])
    launch_args.extend(args.arg_pre)
    passthrough = list(sys.argv[1:])
    # Remove wrapper args from passthrough.
    i = 0
    consumed = {
        "--config-key",
        "--fallback-exe",
        "--arg-pre",
        "--set",
        "--max-lock-seconds",
        "--fast-seconds",
        "--poll-fast",
        "--poll-slow",
        "--class-contains",
        "--title-contains",
        "--process-name",
        "--debug",
        "--debug-log",
    }
    filtered: List[str] = []
    while i < len(passthrough):
        cur = passthrough[i]
        if cur in consumed:
            if cur == "--debug":
                i += 1
                continue
            i += 2
            continue
        if any(cur.startswith(flag + "=") for flag in consumed if flag != "--debug"):
            i += 1
            continue
        filtered.append(cur)
        i += 1
    launch_args.extend(filtered)

    log_debug(args.debug, debug_log, f"Launch args: {launch_args}")
    log_debug(args.debug, debug_log, f"Target rect: x={x}, y={y}, w={w}, h={h}")
    log_debug(args.debug, debug_log, f"Primary rect: x={px}, y={py}, w={pw}, h={ph}")

    proc = subprocess.Popen(launch_args, cwd=cwd)
    log_debug(args.debug, debug_log, f"Spawned PID: {proc.pid}")

    start = time.time()
    pulsed = False
    lock_active = True
    last_rect: Optional[Rect] = None
    last_hwnd: Optional[int] = None
    last_miss_log = 0.0
    allowed_process_names = {x.lower() for x in args.process_name if x}

    while proc.poll() is None:
        elapsed = time.time() - start
        if os.path.exists(STOP_ENFORCE_FLAG):
            if lock_active:
                log_debug(args.debug, debug_log, "Stop flag detected; disabling enforcement.")
            lock_active = False

        if lock_active and elapsed <= args.max_lock_seconds:
            pids = process_tree_pids(proc.pid)
            if allowed_process_names:
                pids |= {proc.pid}
            if args.debug and elapsed > 0 and int(elapsed) % 5 == 0:
                names = ",".join(sorted(process_names_for_pids(pids)))
                if names:
                    log_debug(args.debug, debug_log, f"Tracked process names: {names}")
            hwnd = find_best_window(pids, args.class_contains, args.title_contains, allowed_process_names)
            if hwnd:
                if last_hwnd != hwnd:
                    log_debug(args.debug, debug_log, f"Tracking HWND: {hwnd}")
                    last_hwnd = hwnd
                try:
                    curr_rect = get_rect(hwnd)
                    if last_rect != curr_rect:
                        l, t, cw, ch = curr_rect
                        log_debug(args.debug, debug_log, f"Current rect: x={l}, y={t}, w={cw}, h={ch}")
                        last_rect = curr_rect
                    if curr_rect == (px, py, pw, ph):
                        log_debug(args.debug, debug_log, "Window moved to primary rect; disabling enforcement.")
                        lock_active = False
                        continue
                    if curr_rect != (x, y, w, h):
                        pulse = (not pulsed) and (elapsed < args.fast_seconds)
                        log_debug(
                            args.debug,
                            debug_log,
                            f"Applying target rect (pulse={pulse}): x={x}, y={y}, w={w}, h={h}",
                        )
                        move_window(hwnd, x, y, w, h, pulse)
                        if pulse:
                            pulsed = True
                except Exception:
                    log_debug(args.debug, debug_log, "Exception while reading/moving window; continuing.")
            elif (elapsed - last_miss_log) >= 2.0:
                log_debug(args.debug, debug_log, "No matching window found yet.")
                last_miss_log = elapsed

        time.sleep(args.poll_fast if elapsed < args.fast_seconds else args.poll_slow)

    rc = proc.returncode if proc.returncode is not None else 0
    log_debug(args.debug, debug_log, f"Process exited with code: {rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
