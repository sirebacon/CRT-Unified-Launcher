"""Multi-target session window watcher.

Holds the main poll loop for a gaming session.  Blocks until the primary
process exits or the user presses Ctrl+C.

On shutdown (either path):
  1. Move all tracked emulator windows back to the restore rect.
  2. Sleep one poll cycle so wrapper scripts see the move before the flag.
  3. Write wrapper_stop_enforce.flag to signal wrappers to stop enforcing CRT.

Config restore is performed by the caller (launch_session.py) after run()
returns.

Steam/GOG note: process matching is by process name only.  Games launched
through Steam or GOG that run under a different process name will not be
tracked.  This is a documented known gap for v1 option 3.
"""
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from session.window_utils import (
    find_existing_pids,
    find_window,
    get_rect,
    move_window,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STOP_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

@dataclass
class _WatchTarget:
    slug: str
    process_names: List[str]
    class_contains: List[str]
    title_contains: List[str]
    x: int
    y: int
    w: int
    h: int
    poll_slow: float = 0.5
    last_hwnd: Optional[int] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_target(profile_path: str) -> _WatchTarget:
    with open(profile_path, "r", encoding="utf-8-sig") as f:
        p = json.load(f)
    slug = os.path.splitext(os.path.basename(profile_path))[0]
    return _WatchTarget(
        slug=slug,
        process_names=p.get("process_name", []),
        class_contains=p.get("class_contains", []),
        title_contains=p.get("title_contains", []),
        x=int(p.get("x", -1211)),
        y=int(p.get("y", 43)),
        w=int(p.get("w", 1057)),
        h=int(p.get("h", 835)),
        poll_slow=float(p.get("poll_slow", 0.5)),
    )


def _find_window_for_target(target: _WatchTarget) -> Optional[int]:
    pids = find_existing_pids(target.process_names)
    if not pids:
        return None
    return find_window(
        pids[0],
        target.class_contains,
        target.title_contains,
        match_any_pid=False,
    )


def _lock_target(target: _WatchTarget, debug: bool) -> None:
    hwnd = _find_window_for_target(target)
    if not hwnd:
        return
    if hwnd != target.last_hwnd:
        if debug:
            print(f"  [watcher] {target.slug}: tracking HWND {hwnd}")
        target.last_hwnd = hwnd
    try:
        curr = get_rect(hwnd)
        if curr != (target.x, target.y, target.w, target.h):
            if debug:
                print(
                    f"  [watcher] {target.slug}: snap {curr} -> "
                    f"({target.x},{target.y},{target.w}x{target.h})"
                )
            move_window(hwnd, target.x, target.y, target.w, target.h)
    except Exception:
        pass


def _restore_all_windows(
    targets: List[_WatchTarget],
    rx: int,
    ry: int,
    rw: int,
    rh: int,
) -> None:
    for target in targets:
        hwnd = _find_window_for_target(target)
        if hwnd:
            try:
                move_window(hwnd, rx, ry, rw, rh)
                print(f"[watcher] {target.slug}: moved to primary rect.")
            except Exception as exc:
                print(f"[watcher] {target.slug}: could not restore window: {exc}")


def _write_stop_flag() -> None:
    try:
        with open(STOP_FLAG, "w") as f:
            f.write("")
        print(f"[watcher] Wrote stop flag: {STOP_FLAG}")
    except Exception as exc:
        print(f"[watcher] WARNING: could not write stop flag: {exc}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(
    proc: subprocess.Popen,
    primary_profile_path: str,
    watch_profile_paths: List[str],
    restore_rect: Tuple[int, int, int, int],
    poll_seconds: float = 0.5,
    debug: bool = False,
) -> None:
    """Run the watcher loop until the primary process exits or Ctrl+C.

    Args:
        proc:                  Popen handle for the primary (e.g. LaunchBox).
        primary_profile_path:  Session profile JSON for the primary.
        watch_profile_paths:   Session profile JSONs for emulators to watch.
        restore_rect:          (x, y, w, h) to move all windows to on shutdown.
        poll_seconds:          Seconds between poll iterations.
        debug:                 Print detailed window-tracking output.
    """
    # Clear any stale stop flag from a previous session.
    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
            print(f"[watcher] Removed stale stop flag: {STOP_FLAG}")
    except Exception:
        pass

    primary = _load_target(primary_profile_path)
    watch_targets = [_load_target(p) for p in watch_profile_paths]

    rx, ry, rw, rh = restore_rect

    # --- Signal handling: ignore second Ctrl+C during shutdown ---
    _shutting_down = False

    def _on_sigint(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            print("[watcher] Interrupt received during shutdown — ignoring.")
            return
        _shutting_down = True

    signal.signal(signal.SIGINT, _on_sigint)

    print(
        f"[watcher] Active — {1 + len(watch_targets)} target(s). "
        "Ctrl+C to stop."
    )

    # --- Main poll loop ---
    try:
        while not _shutting_down:
            if proc.poll() is not None:
                print(f"[watcher] Primary exited (code {proc.returncode}).")
                _shutting_down = True
                break

            _lock_target(primary, debug)
            for target in watch_targets:
                _lock_target(target, debug)

            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        # Fallback if signal handler wasn't reached.
        _shutting_down = True

    # --- Shutdown sequence (Ctrl+C ignored from here on) ---
    print("[watcher] Shutting down...")
    signal.signal(
        signal.SIGINT,
        lambda s, f: print("[watcher] Interrupt ignored — cleanup in progress."),
    )

    try:
        _restore_all_windows([primary] + watch_targets, rx, ry, rw, rh)
        time.sleep(poll_seconds)
        _write_stop_flag()
    except Exception as exc:
        print(f"[watcher] Error during shutdown sequence: {exc}")

    print("[watcher] Done.")
