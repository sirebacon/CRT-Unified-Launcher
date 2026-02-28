"""Multi-target session window watcher.

Holds the main poll loop for a gaming session.  Blocks until the primary
process exits or the user ends the session.

Ctrl+C behaviour
----------------
Single Ctrl+C  — Toggle:
                   Active      → Soft stop: moves emulator windows to the
                                 main screen, writes stop flag so wrapper
                                 scripts disengage.  Session stays alive.
                   Soft-stopped → Re-arm: clears paused state, removes stop
                                 flag, emulators snap back to CRT on the
                                 next poll.

Double Ctrl+C  — (within 8 seconds) Full shutdown from any state: moves all
                 windows, writes stop flag, returns to caller for config
                 restore.

Session ends automatically when the primary process (LaunchBox / BigBox)
is no longer running.

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

_SOFT_STOP_WINDOW = 8.0  # seconds: second Ctrl+C within this window = full shutdown


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
    paused: bool = False   # True while the emulator is intentionally on main screen


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
    """Lock the target window to its CRT rect, unless the target is paused.

    A paused target was intentionally moved to the main screen via soft stop.
    It stays paused until its process exits (e.g. user closed the game), at
    which point it is un-paused and ready to track the next game launch.
    """
    if target.paused:
        if not find_existing_pids(target.process_names):
            if debug:
                print(f"  [watcher] {target.slug}: process ended — resuming watch.")
            target.paused = False
        return

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


def _soft_stop_targets(
    targets: List[_WatchTarget],
    rx: int, ry: int, rw: int, rh: int,
) -> None:
    """Move active emulator windows to the main screen and mark them paused."""
    moved_any = False
    for target in targets:
        if target.paused:
            continue
        hwnd = _find_window_for_target(target)
        if hwnd:
            try:
                move_window(hwnd, rx, ry, rw, rh)
                print(f"[watcher] {target.slug}: moved to main screen.")
                moved_any = True
            except Exception as exc:
                print(f"[watcher] {target.slug}: could not move: {exc}")
        target.paused = True
        target.last_hwnd = None
    if moved_any:
        _write_stop_flag()


def _restore_all_windows(
    targets: List[_WatchTarget],
    rx: int, ry: int, rw: int, rh: int,
) -> None:
    """Move all windows (paused or not) to the restore rect on full shutdown."""
    for target in targets:
        hwnd = _find_window_for_target(target)
        if hwnd:
            try:
                move_window(hwnd, rx, ry, rw, rh)
                print(f"[watcher] {target.slug}: moved to primary rect.")
            except Exception as exc:
                print(f"[watcher] {target.slug}: could not restore: {exc}")


def _write_stop_flag() -> None:
    try:
        with open(STOP_FLAG, "w") as f:
            f.write("")
        print(f"[watcher] Wrote stop flag: {STOP_FLAG}")
    except Exception as exc:
        print(f"[watcher] WARNING: could not write stop flag: {exc}")


def _clear_stop_flag() -> None:
    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
            print(f"[watcher] Cleared stop flag: {STOP_FLAG}")
    except Exception as exc:
        print(f"[watcher] WARNING: could not clear stop flag: {exc}")


def _rearm_targets(targets: List[_WatchTarget]) -> None:
    """Clear paused state on all targets so CRT enforcement resumes."""
    for target in targets:
        target.paused = False
        target.last_hwnd = None
    _clear_stop_flag()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(
    proc: Optional[subprocess.Popen],
    primary_profile_path: str,
    watch_profile_paths: List[str],
    restore_rect: Tuple[int, int, int, int],
    poll_seconds: float = 0.5,
    debug: bool = False,
) -> None:
    """Run the watcher loop until the primary process exits or full shutdown.

    Args:
        proc:                  Popen handle for the primary, or None in
                               reattach mode (watcher finds it by process name).
        primary_profile_path:  Session profile JSON for the primary.
        watch_profile_paths:   Session profile JSONs for emulators to watch.
        restore_rect:          (x, y, w, h) to move windows to on shutdown.
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

    # --- Signal handling ---
    # Single Ctrl+C (active)       → soft stop (emulators to main screen)
    # Single Ctrl+C (soft-stopped) → re-arm (emulators snap back to CRT)
    # Double Ctrl+C within _SOFT_STOP_WINDOW seconds → full shutdown from any state
    _shutting_down = False
    _return_to_menu = False   # True = quiet exit, skip window moves and stop flag
    _soft_stop = False        # signal: process a soft stop this iteration
    _rearm = False            # signal: process a re-arm this iteration
    _is_soft_stopped = False  # state: session is currently paused on main screen
    _last_sigint_time = 0.0
    _logged_spawned_exit = False
    _last_heartbeat = time.time()
    _HEARTBEAT_INTERVAL = 60.0  # seconds between "still active" messages

    def _on_sigint(signum, frame):
        nonlocal _shutting_down, _soft_stop, _rearm, _last_sigint_time
        now = time.time()
        elapsed = now - _last_sigint_time
        _last_sigint_time = now
        # Double Ctrl+C within window → full shutdown from any state.
        if elapsed < _SOFT_STOP_WINDOW and (_soft_stop or _is_soft_stopped or _rearm):
            print("\n[watcher] Second Ctrl+C — ending session.")
            _shutting_down = True
            return
        # Toggle: soft-stopped → re-arm; active → soft stop.
        if _is_soft_stopped:
            _rearm = True
        else:
            _soft_stop = True

    signal.signal(signal.SIGINT, _on_sigint)

    print(
        f"[watcher] Active — {len(watch_targets)} emulator target(s). "
        "Ctrl+C to pause (move to main screen). Ctrl+C again to resume CRT. "
        "Ctrl+C twice quickly to end session."
    )

    # --- Main poll loop ---
    try:
        while not _shutting_down:
            # Primary exit detection.
            spawned_exited = proc is None or proc.poll() is not None
            if spawned_exited:
                if not find_existing_pids(primary.process_names):
                    if proc is not None:
                        print(f"[watcher] Primary exited (code {proc.returncode}).")
                    else:
                        print("[watcher] Primary process no longer running.")
                    _shutting_down = True
                    break
                elif debug and proc is not None and proc.poll() is not None and not _logged_spawned_exit:
                    print("[watcher] Spawned process exited — matching process still alive, continuing.")
                    _logged_spawned_exit = True

            # Soft stop: move active emulators to main screen, keep session alive.
            # If no emulators are running at all, return to menu quietly.
            if _soft_stop and not _shutting_down:
                any_running = any(find_existing_pids(t.process_names) for t in watch_targets)
                if not any_running:
                    print("\n[watcher] Ctrl+C — no emulators running, returning to menu.")
                    _return_to_menu = True
                    _shutting_down = True
                    break
                print("[watcher] Pausing — moving emulators to main screen.")
                print("[watcher] Ctrl+C to move back to CRT, or twice quickly to end session.")
                _soft_stop_targets(watch_targets, rx, ry, rw, rh)
                _soft_stop = False
                _is_soft_stopped = True

            # Re-arm: clear paused state so CRT enforcement resumes.
            if _rearm and not _shutting_down:
                print("[watcher] Resuming — emulators will snap back to CRT.")
                _rearm_targets(watch_targets)
                _is_soft_stopped = False
                _rearm = False

            # Lock emulator windows to CRT.
            for target in watch_targets:
                _lock_target(target, debug)

            # Periodic heartbeat so the terminal shows the session is still alive.
            now = time.time()
            if now - _last_heartbeat >= _HEARTBEAT_INTERVAL:
                active = [t.slug for t in watch_targets if not t.paused]
                print(f"[watcher] Session active — watching: {', '.join(active) if active else 'none'}")
                _last_heartbeat = now

            time.sleep(poll_seconds)

    except KeyboardInterrupt:
        _shutting_down = True

    # --- Shutdown sequence ---
    signal.signal(
        signal.SIGINT,
        lambda s, f: print("[watcher] Interrupt ignored — cleanup in progress."),
    )

    if _return_to_menu:
        # Quiet exit: no emulators were running, nothing to move or signal.
        # Configs are restored by the caller (launch_session.py).
        print("[watcher] Session ended.")
    else:
        print("[watcher] Shutting down...")
        try:
            _restore_all_windows([primary] + watch_targets, rx, ry, rw, rh)
            time.sleep(poll_seconds)
            _write_stop_flag()
        except Exception as exc:
            print(f"[watcher] Error during shutdown: {exc}")
        print("[watcher] Done.")

