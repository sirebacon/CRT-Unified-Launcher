import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

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
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "profiles")
DEFAULTS_PATH = os.path.join(PROFILES_DIR, "defaults.json")
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "runtime")

DEFAULT_MAX_LOCK_SECONDS = 120.0
DEFAULT_FAST_SECONDS = 8.0
DEFAULT_POLL_FAST = 0.1
DEFAULT_POLL_SLOW = 0.4

SUPPORTED_PROFILE_VERSIONS = {1}

MAX_LOG_BYTES = 1_048_576  # 1 MB
MAX_LOG_ROTATIONS = 3

# Schema: key -> (required, type_or_types, optional_(min, max) range)
PROFILE_SCHEMA: Dict[str, tuple] = {
    "path":             (True,  str,           None),
    "dir":              (False, str,           None),
    "profile_version":  (False, int,           (1, 1)),
    "base":             (False, str,           None),
    "x":                (False, (int, float),  None),
    "y":                (False, (int, float),  None),
    "w":                (False, (int, float),  (1, 9999)),
    "h":                (False, (int, float),  (1, 9999)),
    "max_lock_seconds": (False, (int, float),  (0, 600)),
    "fast_seconds":     (False, (int, float),  (0, 60)),
    "poll_fast":        (False, (int, float),  (0.01, 5)),
    "poll_slow":        (False, (int, float),  (0.01, 10)),
    "process_name":     (False, list,          None),
    "class_contains":   (False, list,          None),
    "title_contains":   (False, list,          None),
    "arg_pre":          (False, list,          None),
    "set_values":       (False, list,          None),
    "position_only":    (False, bool,          None),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generic LaunchBox CRT wrapper.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--config-key", help="Key in crt_config.json (e.g. dolphin, ppsspp, pcsx2).")
    mode.add_argument("--profile-file", help="Path to a profile JSON file.")
    p.add_argument("--fallback-exe", action="append", default=[], help="Fallback exe path if config/profile path is missing.")
    p.add_argument("--arg-pre", action="append", default=[], help="Arguments to prepend before LaunchBox passthrough args.")
    p.add_argument("--set", dest="set_values", action="append", default=[], help="Adds '-C KEY=VALUE' (repeatable).")
    p.add_argument("--max-lock-seconds", type=float, default=None, help="How long to enforce target rect (default 120.0).")
    p.add_argument("--fast-seconds", type=float, default=None, help="Fast poll period duration (default 8.0).")
    p.add_argument("--poll-fast", type=float, default=None, help="Poll interval during fast period (default 0.1).")
    p.add_argument("--poll-slow", type=float, default=None, help="Poll interval after fast period (default 0.4).")
    p.add_argument("--class-contains", action="append", default=[], help="Window class substring filter (repeatable).")
    p.add_argument("--title-contains", action="append", default=[], help="Window title substring filter (repeatable).")
    p.add_argument("--process-name", action="append", default=[], help="Extra process name filter for child windows.")
    p.add_argument("--position-only", action="store_true", help="Only enforce x,y position; do not fight window size. Use for fullscreen games that manage their own sizing.")
    p.add_argument("--validate-only", action="store_true", help="Validate profile and resolved config, then exit without launching.")
    p.add_argument("--dry-run", action="store_true", help="Print resolved config and launch command, then exit without launching.")
    p.add_argument("--debug", action="store_true", help="Enable debug logs to stdout and log file.")
    p.add_argument("--debug-log", default="", help="Custom debug log file path.")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Config and profile loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_defaults() -> dict:
    """Load profiles/defaults.json if present. Returns empty dict if missing."""
    if not os.path.exists(DEFAULTS_PATH):
        return {}
    with open(DEFAULTS_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_base_path(base: str, profile_path: str) -> str:
    """Resolve a base profile path relative to the current profile's directory."""
    if os.path.isabs(base):
        return base
    return os.path.join(os.path.dirname(os.path.abspath(profile_path)), base)


def load_profile_with_inheritance(path: str) -> dict:
    """Load a profile and apply single-level base inheritance if 'base' key is present."""
    profile = load_profile(path)
    if "base" not in profile:
        return profile
    base_path = resolve_base_path(profile["base"], path)
    base = load_profile(base_path)
    # Shallow merge: base values first, profile overrides.
    return {**base, **profile}


def expand_variables(profile: dict) -> dict:
    """Expand %PROJECT_ROOT% and %GAME_DIR% in string and list-of-string values.

    Expansion runs after inheritance merge so %GAME_DIR% reflects the final 'dir' value.
    """
    game_dir = profile.get("dir", "")

    def expand(value: str) -> str:
        return (
            value
            .replace("%PROJECT_ROOT%", PROJECT_ROOT)
            .replace("%GAME_DIR%", game_dir)
        )

    result = {}
    for key, value in profile.items():
        if isinstance(value, str):
            result[key] = expand(value)
        elif isinstance(value, list):
            result[key] = [expand(v) if isinstance(v, str) else v for v in value]
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_profile(profile: dict) -> List[str]:
    """Return a list of error strings. Empty list means the profile is valid."""
    errors: List[str] = []

    for key, value in profile.items():
        if key.startswith("_"):
            continue  # metadata keys are always ignored
        if key not in PROFILE_SCHEMA:
            errors.append(f"Unknown key: '{key}'")
            continue
        _, expected_type, range_ = PROFILE_SCHEMA[key]
        if not isinstance(value, expected_type):
            type_name = (
                " or ".join(t.__name__ for t in expected_type)
                if isinstance(expected_type, tuple)
                else expected_type.__name__
            )
            errors.append(f"Key '{key}': expected {type_name}, got {type(value).__name__}")
        elif range_ is not None and isinstance(value, (int, float)):
            lo, hi = range_
            if not (lo <= value <= hi):
                errors.append(f"Key '{key}': value {value} out of range [{lo}, {hi}]")

    for key, (required, _, _) in PROFILE_SCHEMA.items():
        if required and key not in profile:
            errors.append(f"Missing required key: '{key}'")

    if "profile_version" in profile:
        v = profile["profile_version"]
        if isinstance(v, int) and v not in SUPPORTED_PROFILE_VERSIONS:
            errors.append(
                f"Unsupported profile_version: {v}. "
                f"Supported: {sorted(SUPPORTED_PROFILE_VERSIONS)}"
            )

    # Path existence check — skip if value still contains unexpanded variables.
    path_val = profile.get("path", "")
    if isinstance(path_val, str) and path_val and "%" not in path_val:
        if not os.path.exists(path_val):
            errors.append(f"'path' does not exist: {path_val}")

    return errors


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def apply_profile_to_args(
    profile: dict, cfg: dict, args: argparse.Namespace
) -> Tuple[str, str, int, int, int, int]:
    """Merge profile into args in-place.

    Precedence: CLI args > profile > defaults file > crt_config.json > hardcoded defaults.
    Returns (exe, cwd, x, y, w, h).
    """
    li = cfg.get("launcher_integration", {})
    r = cfg.get("retroarch", {})
    defaults = load_defaults()

    # Executable: profile required; CLI --fallback-exe used if profile path is missing/invalid.
    path = profile.get("path", "")
    dir_ = profile.get("dir", os.path.dirname(path) if path else "")
    if not (path and os.path.exists(path)):
        for fe in args.fallback_exe:
            if os.path.exists(fe):
                path, dir_ = fe, os.path.dirname(fe)
                break
    if not (path and os.path.exists(path)):
        raise FileNotFoundError(
            f"Executable not found. Profile path: '{profile.get('path', '')}'. "
            f"Fallbacks: {args.fallback_exe}"
        )

    # Target rect: profile > launcher_integration > retroarch hardcoded.
    x = int(profile.get("x", li.get("x", r.get("x", -1211))))
    y = int(profile.get("y", li.get("y", r.get("y", 43))))
    w = int(profile.get("w", li.get("w", r.get("w", 1057))))
    h = int(profile.get("h", li.get("h", r.get("h", 835))))

    # Timings: CLI (explicit) > profile > defaults file > hardcoded defaults.
    if args.max_lock_seconds is None:
        args.max_lock_seconds = float(profile.get("max_lock_seconds", defaults.get("max_lock_seconds", DEFAULT_MAX_LOCK_SECONDS)))
    if args.fast_seconds is None:
        args.fast_seconds = float(profile.get("fast_seconds", defaults.get("fast_seconds", DEFAULT_FAST_SECONDS)))
    if args.poll_fast is None:
        args.poll_fast = float(profile.get("poll_fast", defaults.get("poll_fast", DEFAULT_POLL_FAST)))
    if args.poll_slow is None:
        args.poll_slow = float(profile.get("poll_slow", defaults.get("poll_slow", DEFAULT_POLL_SLOW)))

    # Filters: profile provides base list; CLI args appended on top.
    args.class_contains = list(profile.get("class_contains", [])) + args.class_contains
    args.title_contains = list(profile.get("title_contains", [])) + args.title_contains
    args.process_name = list(profile.get("process_name", [])) + args.process_name

    # Launch args: profile provides base; CLI appended.
    args.arg_pre = list(profile.get("arg_pre", [])) + args.arg_pre
    args.set_values = list(profile.get("set_values", [])) + args.set_values

    # Flags: CLI wins if explicitly set.
    if not args.position_only:
        args.position_only = bool(profile.get("position_only", False))

    return path, dir_, x, y, w, h


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


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def rotate_log_if_needed(log_path: str) -> None:
    """Rotate log file if it exceeds MAX_LOG_BYTES. Keeps up to MAX_LOG_ROTATIONS old copies."""
    if not os.path.exists(log_path):
        return
    if os.path.getsize(log_path) < MAX_LOG_BYTES:
        return
    for i in range(MAX_LOG_ROTATIONS - 1, 0, -1):
        src = f"{log_path}.{i}"
        dst = f"{log_path}.{i + 1}"
        if os.path.exists(src):
            try:
                os.replace(src, dst)
            except Exception:
                pass
    try:
        os.replace(log_path, f"{log_path}.1")
    except Exception:
        pass


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


# ---------------------------------------------------------------------------
# Last-launch summary
# ---------------------------------------------------------------------------

def write_launch_summary(
    slug: str,
    mode: str,
    profile_file: Optional[str],
    config_key: Optional[str],
    exe: str,
    rect: Rect,
    position_only: bool,
    exit_code: int,
    duration_seconds: float,
) -> None:
    """Write a compact last-launch summary to runtime/last_launch_summary.json."""
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    summary = {
        "timestamp": datetime.now().isoformat(),
        "slug": slug,
        "mode": mode,
        "profile_file": profile_file,
        "config_key": config_key,
        "exe": exe,
        "rect": {"x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]},
        "position_only": position_only,
        "exit_code": exit_code,
        "duration_seconds": round(duration_seconds, 1),
    }
    try:
        summary_path = os.path.join(RUNTIME_DIR, "last_launch_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Window management
# ---------------------------------------------------------------------------

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


def move_window(hwnd: int, x: int, y: int, w: int, h: int, pulse: bool, position_only: bool = False) -> None:
    if position_only:
        flags = win32con.SWP_SHOWWINDOW | win32con.SWP_NOSIZE
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, 0, 0, flags)
    else:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    cfg = load_config()

    if args.profile_file:
        profile = load_profile_with_inheritance(args.profile_file)
        profile = expand_variables(profile)
        errors = validate_profile(profile)
        if errors:
            for e in errors:
                print(f"[ProfileError] {e}")
            return 1
        exe, cwd, x, y, w, h = apply_profile_to_args(profile, cfg, args)
        log_slug = os.path.splitext(os.path.basename(args.profile_file))[0]
        mode = "profile"
    else:
        exe, cwd = resolve_exe(cfg, args.config_key, args.fallback_exe)
        x, y, w, h = target_rect(cfg, args.config_key)
        log_slug = args.config_key
        mode = "config-key"

    # Resolve timing defaults for any values not set by CLI or profile.
    if args.max_lock_seconds is None:
        args.max_lock_seconds = DEFAULT_MAX_LOCK_SECONDS
    if args.fast_seconds is None:
        args.fast_seconds = DEFAULT_FAST_SECONDS
    if args.poll_fast is None:
        args.poll_fast = DEFAULT_POLL_FAST
    if args.poll_slow is None:
        args.poll_slow = DEFAULT_POLL_SLOW

    px, py, pw, ph = primary_rect(cfg)
    debug_log = args.debug_log or os.path.join(PROJECT_ROOT, f"{log_slug}_wrapper_debug.log")

    # --validate-only: profile validation already ran above. Just confirm and exit.
    if args.validate_only:
        if args.profile_file:
            print(f"[ValidateOnly] '{args.profile_file}' is valid.")
            print(f"[ValidateOnly] Exe:  {exe}")
            print(f"[ValidateOnly] Rect: x={x}  y={y}  w={w}  h={h}")
        else:
            print(f"[ValidateOnly] Config key '{args.config_key}' resolved OK.")
            print(f"[ValidateOnly] Exe:  {exe}")
            print(f"[ValidateOnly] Rect: x={x}  y={y}  w={w}  h={h}")
        return 0

    # Build passthrough-stripped launch args (needed for both --dry-run and live launch).
    launch_args: List[str] = [exe]
    for kv in args.set_values:
        launch_args.extend(["-C", kv])
    launch_args.extend(args.arg_pre)
    passthrough = list(sys.argv[1:])
    i = 0
    flag_args = {"--position-only", "--validate-only", "--dry-run", "--debug"}
    consumed = {
        "--config-key", "--profile-file", "--fallback-exe", "--arg-pre", "--set",
        "--max-lock-seconds", "--fast-seconds", "--poll-fast", "--poll-slow",
        "--class-contains", "--title-contains", "--process-name",
        "--position-only", "--validate-only", "--dry-run", "--debug", "--debug-log",
    }
    filtered: List[str] = []
    while i < len(passthrough):
        cur = passthrough[i]
        if cur in consumed:
            if cur in flag_args:
                i += 1
                continue
            i += 2
            continue
        if any(cur.startswith(f + "=") for f in consumed if f not in flag_args):
            i += 1
            continue
        filtered.append(cur)
        i += 1
    launch_args.extend(filtered)

    # --dry-run: print everything resolved, then exit.
    if args.dry_run:
        source = f"profile: {args.profile_file}" if args.profile_file else f"config-key: {args.config_key}"
        print(f"[DryRun] Mode:         {source}")
        print(f"[DryRun] Exe:          {exe}")
        print(f"[DryRun] Dir:          {cwd}")
        print(f"[DryRun] Exe exists:   {'YES' if os.path.exists(exe) else 'NO  <-- path not found'}")
        print(f"[DryRun] Rect:         x={x}  y={y}  w={w}  h={h}")
        print(f"[DryRun] Primary:      x={px}  y={py}  w={pw}  h={ph}")
        print(f"[DryRun] max_lock:     {args.max_lock_seconds}s")
        print(f"[DryRun] fast:         {args.fast_seconds}s  poll_fast={args.poll_fast}s  poll_slow={args.poll_slow}s")
        print(f"[DryRun] position_only:{args.position_only}")
        print(f"[DryRun] process_name: {args.process_name}")
        print(f"[DryRun] class:        {args.class_contains}")
        print(f"[DryRun] title:        {args.title_contains}")
        print(f"[DryRun] Command:      {launch_args}")
        return 0

    # Rotate log before first write.
    rotate_log_if_needed(debug_log)

    try:
        if os.path.exists(STOP_ENFORCE_FLAG):
            os.remove(STOP_ENFORCE_FLAG)
            log_debug(args.debug, debug_log, f"Removed stale stop flag: {STOP_ENFORCE_FLAG}")
    except Exception:
        pass

    # Startup summary line.
    log_debug(
        args.debug, debug_log,
        f"Resolved: mode={mode}  slug={log_slug}  exe={exe}  "
        f"rect=({x},{y},{w},{h})  position_only={args.position_only}"
    )
    log_debug(args.debug, debug_log, f"Launch args: {launch_args}")
    log_debug(args.debug, debug_log, f"Primary rect: x={px}, y={py}, w={pw}, h={ph}")

    proc = subprocess.Popen(launch_args, cwd=cwd)
    start_time = time.time()
    log_debug(args.debug, debug_log, f"Spawned PID: {proc.pid}")

    pulsed = False
    lock_active = True
    last_rect: Optional[Rect] = None
    last_hwnd: Optional[int] = None
    last_miss_log = 0.0
    allowed_process_names = {x.lower() for x in args.process_name if x}

    while proc.poll() is None:
        elapsed = time.time() - start_time
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
                    needs_move = (
                        (curr_rect[0] != x or curr_rect[1] != y)
                        if args.position_only
                        else curr_rect != (x, y, w, h)
                    )
                    if needs_move:
                        pulse = (not pulsed) and (elapsed < args.fast_seconds)
                        log_debug(
                            args.debug, debug_log,
                            f"Applying target rect (pulse={pulse}, position_only={args.position_only}): "
                            f"x={x}, y={y}, w={w}, h={h}",
                        )
                        move_window(hwnd, x, y, w, h, pulse, args.position_only)
                        if pulse:
                            pulsed = True
                except Exception:
                    log_debug(args.debug, debug_log, "Exception while reading/moving window; continuing.")
            elif (elapsed - last_miss_log) >= 2.0:
                log_debug(args.debug, debug_log, "No matching window found yet.")
                last_miss_log = elapsed

        time.sleep(args.poll_fast if elapsed < args.fast_seconds else args.poll_slow)

    rc = proc.returncode if proc.returncode is not None else 0
    duration = time.time() - start_time
    log_debug(args.debug, debug_log, f"Process exited with code: {rc}  duration={round(duration, 1)}s")

    write_launch_summary(
        slug=log_slug,
        mode=mode,
        profile_file=args.profile_file,
        config_key=args.config_key,
        exe=exe,
        rect=(x, y, w, h),
        position_only=args.position_only,
        exit_code=rc,
        duration_seconds=duration,
    )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
