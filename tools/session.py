"""Session/log diagnostics for crt_tools (Phase 2 scaffold)."""

import json
import os
import time
from typing import List

from session.re_config import RE_STACK_LOG_PATH, STATE_PATH, STOP_FLAG
from session.re_game import find_wrapper_pids, re_process_names

try:
    import psutil
except Exception:
    psutil = None


def _tail_lines(path: str, lines: int) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-lines:]
    except FileNotFoundError:
        return []


def session_state() -> int:
    """Read and display runtime/re_stack_state.json (written by auto mode at session start)."""
    if not os.path.exists(STATE_PATH):
        print(f"[tools] FAIL: session state -- no state file: {STATE_PATH}")
        print("  Auto mode has never run, or the file was cleaned up after restore.")
        return 1
    try:
        mtime = os.path.getmtime(STATE_PATH)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        print(f"[tools] FAIL: session state -- could not read state file: {e}")
        return 1

    print(f"State file: {STATE_PATH}  (written {ts})")
    print()
    print(f"previous_primary_device_name : {state.get('previous_primary_device_name', '(not set)')}")
    crt = state.get("crt_mode")
    if crt:
        print("crt_mode:")
        print(f"  device_name : {crt.get('device_name', '?')}")
        print(f"  resolution  : {crt.get('width', '?')}x{crt.get('height', '?')}")
        print(f"  refresh_hz  : {crt.get('hz', '?')}")
    else:
        print("crt_mode     : (not saved)")
    print()
    print("Note: this file stores display state only.")
    print("Audio restore uses the static restore_device_token from re_stack_config.json.")
    return 0


def session_flag(clear: bool = False) -> int:
    """Check or clear the wrapper_stop_enforce.flag stop flag."""
    exists = os.path.exists(STOP_FLAG)

    if clear:
        if not exists:
            print("[tools] PASS: session flag -- flag not present, nothing to clear")
            return 0
        try:
            os.remove(STOP_FLAG)
            print(f"[tools] PASS: session flag -- cleared: {STOP_FLAG}")
            return 0
        except Exception as e:
            print(f"[tools] FAIL: session flag -- could not remove: {e}")
            return 1

    print(f"Stop flag: {STOP_FLAG}")
    if exists:
        mtime = os.path.getmtime(STOP_FLAG)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        print(f"  Status : PRESENT  (written {ts})")
        print()
        print("  Wrappers will NOT enforce window position while this flag exists.")
        print("  Run with --clear to remove it.")
    else:
        print("  Status : not present  (wrappers will enforce normally)")
    return 0


def session_log(lines: int = 30, follow: bool = False) -> int:
    if not os.path.exists(RE_STACK_LOG_PATH):
        print(f"[tools] FAIL: session log -- not found: {RE_STACK_LOG_PATH}")
        return 1

    if not follow:
        for line in _tail_lines(RE_STACK_LOG_PATH, lines):
            print(line.rstrip("\n"))
        return 0

    # simple tail -f
    with open(RE_STACK_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        print(f"[tools] Following log: {RE_STACK_LOG_PATH} (Ctrl+C to stop)")
        while True:
            line = f.readline()
            if line:
                print(line.rstrip("\n"))
            else:
                time.sleep(0.25)


def session_processes() -> int:
    if psutil is None:
        print("[tools] FAIL: session processes -- psutil unavailable")
        return 1

    re_names = set(re_process_names())
    wrappers = set(find_wrapper_pids())
    buckets = {
        "moonlight": [],
        "re_games": [],
        "wrappers": [],
        "launchbox": [],
        "apollo": [],
    }
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = int(proc.info["pid"])
            name = str(proc.info.get("name") or "")
            lname = name.lower()
            cmd = " ".join(proc.info.get("cmdline") or [])
            row = {"pid": pid, "name": name, "cmd": cmd}
            if "moonlight" in lname:
                buckets["moonlight"].append(row)
            if lname in re_names:
                buckets["re_games"].append(row)
            if pid in wrappers or "launchbox_generic_wrapper.py" in cmd.lower():
                buckets["wrappers"].append(row)
            if lname in ("launchbox.exe", "bigbox.exe"):
                buckets["launchbox"].append(row)
            if "apollo" in lname:
                buckets["apollo"].append(row)
        except Exception:
            continue

    def _print_group(label: str, rows: List[dict]) -> None:
        print(f"{label}:")
        if not rows:
            print("  (none)")
            return
        for r in rows:
            print(f"  PID {r['pid']:<6} {r['name']}")

    print("Session-related processes")
    print()
    _print_group("Moonlight", buckets["moonlight"])
    print()
    _print_group("RE game processes", buckets["re_games"])
    print()
    _print_group("Wrapper processes", buckets["wrappers"])
    print()
    _print_group("LaunchBox / BigBox", buckets["launchbox"])
    print()
    _print_group("Apollo", buckets["apollo"])
    return 0
