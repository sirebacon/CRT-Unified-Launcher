"""Resident Evil stack launcher and restore helper.

Usage:
    python launch_resident_evil_stack.py start --game re1
    python launch_resident_evil_stack.py start --game re2 --debug
    python launch_resident_evil_stack.py restore
    python launch_resident_evil_stack.py inspect
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

from default_restore import restore_defaults_from_backup
from session.audio import audio_tool_status, set_default_audio_best_effort
from session.display_api import (
    current_primary_device_name,
    current_primary_display,
    enumerate_attached_displays,
    find_display_by_device_name,
    find_display_by_token,
    set_display_refresh_best_effort,
    set_primary_display_entry,
    set_primary_display_verified,
)
from session.moonlight import ensure_moonlight_running, move_moonlight_to_crt
from session.vdd import plug_vdd_and_wait, unplug_vdd

try:
    import psutil
except Exception:
    psutil = None


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
WRAPPER_PATH = os.path.join(
    PROJECT_ROOT,
    "integrations",
    "launchbox",
    "wrapper",
    "launchbox_generic_wrapper.py",
)
STOP_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")
STATE_PATH = os.path.join(PROJECT_ROOT, "runtime", "re_stack_state.json")
RE_STACK_LOG_PATH = os.path.join(PROJECT_ROOT, "runtime", "re_stack.log")
CRT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")
MOONLIGHT_DIR = r"D:\Emulators\MoonlightPortable-x64-6.1.0"
MOONLIGHT_EXE = os.path.join(MOONLIGHT_DIR, "Moonlight.exe")

# SudoMaker Virtual Display Adapter (Moonlight virtual display).
# Plugged (attached to desktop) on start, unplugged on restore.
VDD_ATTACH_TIMEOUT_SECONDS = 15

# Moonlight virtual display is set as primary so RE launches on it;
# Moonlight client streams the output to the CRT.
RE_PRIMARY_DISPLAY_TOKEN = "SudoMaker Virtual Display"
RE_AUDIO_DEVICE_TOKEN = "CP-1262HE (NVIDIA High Definition Audio)"
CRT_DISPLAY_TOKEN = "NVIDIA GeForce RTX 4090 Laptop GPU"
CRT_TARGET_REFRESH_HZ = 60

# Restore targets after Resident Evil mode.
RESTORE_PRIMARY_DISPLAY_TOKEN = "Intel(R) UHD Graphics"
RESTORE_AUDIO_DEVICE_TOKEN = "Speakers (Realtek(R) Audio)"

# Required display set for RE mode preflight.
# Each entry is a list of acceptable name tokens (first match wins).
REQUIRED_DISPLAY_GROUPS = {
    "internal_display": ["Internal Display", "Intel(R) UHD Graphics"],
    "crt_display": ["CP-1262HE", "NVIDIA GeForce RTX 4090 Laptop GPU"],
    "moonlight_display": ["SudoMaker Virtual Display"],
}

GAME_PROFILES: Dict[str, str] = {
    "re1": os.path.join(
        PROJECT_ROOT,
        "integrations",
        "launchbox",
        "wrapper",
        "profiles",
        "re1-gog.json",
    ),
    "re2": os.path.join(
        PROJECT_ROOT,
        "integrations",
        "launchbox",
        "wrapper",
        "profiles",
        "re2-gog.json",
    ),
    "re3": os.path.join(
        PROJECT_ROOT,
        "integrations",
        "launchbox",
        "wrapper",
        "profiles",
        "re3-gog.json",
    ),
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Launch Resident Evil profiles with CRT wrapper and restore state."
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a Resident Evil stack launch.")
    p_start.add_argument(
        "--game",
        choices=sorted(GAME_PROFILES.keys()),
        required=True,
        help="Which game profile to launch.",
    )
    p_start.add_argument("--debug", action="store_true", help="Enable wrapper debug.")
    p_start.add_argument(
        "passthrough",
        nargs=argparse.REMAINDER,
        help="Optional passthrough args to the game/wrapper (prefix with --).",
    )

    sub.add_parser("restore", help="Stop wrapper enforcement and restore backed up configs.")
    sub.add_parser("inspect", help="Inspect display matches and audio tool availability.")
    return p.parse_args()


def _normalize_passthrough(passthrough: List[str]) -> List[str]:
    if passthrough and passthrough[0] == "--":
        return passthrough[1:]
    return passthrough


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class _TeeWriter:
    def __init__(self, original_stream, log_stream):
        self._original = original_stream
        self._log = log_stream

    def write(self, data):
        self._original.write(data)
        self._log.write(data)

    def flush(self):
        self._original.flush()
        self._log.flush()


def _enable_persistent_logging() -> None:
    os.makedirs(os.path.dirname(RE_STACK_LOG_PATH), exist_ok=True)
    log_f = open(RE_STACK_LOG_PATH, "a", encoding="utf-8")
    log_f.write(
        "\n==== re-stack session "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====\n"
    )
    log_f.flush()
    sys.stdout = _TeeWriter(sys.stdout, log_f)
    sys.stderr = _TeeWriter(sys.stderr, log_f)
    print(f"[re-stack] Logging to: {RE_STACK_LOG_PATH}")


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

def _write_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def _read_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def _ensure_required_displays() -> bool:
    attached = enumerate_attached_displays()
    print(f"[re-stack] Attached display count: {len(attached)}")

    missing: List[str] = []
    for label, tokens in REQUIRED_DISPLAY_GROUPS.items():
        match = next((find_display_by_token(t) for t in tokens if find_display_by_token(t)), {})
        if match:
            matched_token = next(t for t in tokens if find_display_by_token(t))
            print(
                f"[re-stack] Required display '{label}' matched: "
                f"{match['device_name']} via token '{matched_token}'"
            )
        else:
            missing.append(f"{label} ({' | '.join(tokens)})")

    if missing:
        print("[re-stack] Required display check failed. Missing:")
        for item in missing:
            print(f" - {item}")
        return False

    return True


# ---------------------------------------------------------------------------
# System state
# ---------------------------------------------------------------------------

def _apply_re_mode_system_state() -> bool:
    primary = current_primary_display()
    if primary:
        _write_state({"previous_primary_device_name": primary["device_name"]})
    set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    ok_display = set_primary_display_verified(RE_PRIMARY_DISPLAY_TOKEN)
    set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    set_default_audio_best_effort(RE_AUDIO_DEVICE_TOKEN)
    return ok_display


def _apply_restore_system_state() -> bool:
    state = _read_state()
    restored_by_state = False
    prev_device = str(state.get("previous_primary_device_name", "")).strip()
    if prev_device:
        prev = find_display_by_device_name(prev_device)
        if prev and set_primary_display_entry(prev):
            print(f"[re-stack] Primary display restored to previous device: {prev_device}")
            restored_by_state = True

    ok_display = restored_by_state or set_primary_display_verified(RESTORE_PRIMARY_DISPLAY_TOKEN)
    set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    set_default_audio_best_effort(RESTORE_AUDIO_DEVICE_TOKEN)
    unplug_vdd(REQUIRED_DISPLAY_GROUPS["moonlight_display"][0])
    return ok_display


# ---------------------------------------------------------------------------
# Wrapper process helpers
# ---------------------------------------------------------------------------

def _find_wrapper_pids() -> List[int]:
    if psutil is None:
        return []
    pids: List[int] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if "launchbox_generic_wrapper.py" in cmdline:
                pids.append(int(proc.info["pid"]))
        except Exception:
            continue
    return pids


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def start_stack(game: str, debug: bool, passthrough: List[str]) -> int:
    profile = GAME_PROFILES[game]
    if not os.path.exists(WRAPPER_PATH):
        print(f"[re-stack] Wrapper not found: {WRAPPER_PATH}")
        return 1
    if not os.path.exists(profile):
        print(f"[re-stack] Profile not found: {profile}")
        return 1

    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
    except Exception:
        pass

    if not ensure_moonlight_running(MOONLIGHT_EXE, MOONLIGHT_DIR):
        print("[re-stack] Moonlight requirement failed; aborting launch.")
        return 1
    if not plug_vdd_and_wait(
        REQUIRED_DISPLAY_GROUPS["moonlight_display"][0],
        timeout_seconds=VDD_ATTACH_TIMEOUT_SECONDS,
    ):
        print("[re-stack] VDD plug in failed; aborting launch.")
        return 1
    if not _ensure_required_displays():
        print("[re-stack] Required display set not found; aborting launch.")
        return 1
    if not move_moonlight_to_crt(
        REQUIRED_DISPLAY_GROUPS["crt_display"],
        MOONLIGHT_DIR,
        crt_config_path=CRT_CONFIG_PATH,
    ):
        print("[re-stack] Moonlight window placement failed; aborting launch.")
        return 1

    if not _apply_re_mode_system_state():
        print("[re-stack] Failed to apply Resident Evil system state; aborting launch.")
        return 1

    cmd = [sys.executable, WRAPPER_PATH, "--profile-file", profile]
    if debug:
        cmd.append("--debug")
    cmd.extend(_normalize_passthrough(passthrough))

    print(f"[re-stack] Launching {game} with profile: {profile}")
    rc = 1
    interrupted = False
    target_display = find_display_by_token(RE_PRIMARY_DISPLAY_TOKEN)
    wanted_primary = str(target_display.get("device_name", "")).strip().lower()
    proc: Optional[subprocess.Popen] = None
    last_refresh_enforce = 0.0
    try:
        proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
        while True:
            rc_now = proc.poll()
            if rc_now is not None:
                rc = rc_now
                break
            if wanted_primary:
                active = current_primary_device_name().lower()
                if active != wanted_primary:
                    print(
                        f"[re-stack] Primary drift detected during RE session "
                        f"({active or 'UNKNOWN'} -> {wanted_primary}). Re-applying."
                    )
                    set_primary_display_verified(RE_PRIMARY_DISPLAY_TOKEN, retries=1)
            now = time.time()
            if now - last_refresh_enforce >= 5.0:
                set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
                last_refresh_enforce = now
            time.sleep(1.0)
    except KeyboardInterrupt:
        interrupted = True
        print("[re-stack] Ctrl+C detected. Restoring system state...")
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    finally:
        restore_rc = restore_stack()
        if restore_rc != 0:
            print("[re-stack] WARNING: restore reported errors.")

    if interrupted:
        return 130
    return rc


def restore_stack() -> int:
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as f:
            f.write("stop\n")
    except Exception:
        pass

    stopped: List[int] = []
    pids = _find_wrapper_pids()
    for pid in pids:
        try:
            proc = psutil.Process(pid) if psutil is not None else None
            if proc is None:
                continue
            proc.terminate()
            proc.wait(timeout=3)
            stopped.append(pid)
        except Exception:
            try:
                if psutil is not None:
                    psutil.Process(pid).kill()
                    stopped.append(pid)
            except Exception:
                pass

    ok, msg, restored = restore_defaults_from_backup()
    print(f"[re-stack] {msg}")
    if stopped:
        print("[re-stack] Stopped wrapper PID(s): " + ", ".join(str(pid) for pid in stopped))
    if restored:
        print("[re-stack] Restored files:")
        for item in restored:
            print(f" - {item}")

    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
    except Exception:
        pass

    state_ok = _apply_restore_system_state()
    return 0 if (ok and state_ok) else 1


def inspect_state() -> int:
    displays = enumerate_attached_displays()
    if not displays:
        print("[re-stack] No attached displays found or display API unavailable.")
    else:
        print("[re-stack] Attached displays:")
        for d in displays:
            mons = ", ".join(d["monitor_strings"]) if d["monitor_strings"] else "(none)"
            print(
                f" - {d['device_name']} | {d['device_string']} | "
                f"pos={d['position'][0]},{d['position'][1]} | monitors={mons}"
            )

    re_match = find_display_by_token(RE_PRIMARY_DISPLAY_TOKEN)
    restore_match = find_display_by_token(RESTORE_PRIMARY_DISPLAY_TOKEN)
    primary_now = current_primary_display()
    print(
        f"[re-stack] Current primary display: "
        f"{primary_now.get('device_name', 'UNKNOWN')} | "
        f"{primary_now.get('device_string', '')}"
    )
    print(
        f"[re-stack] RE primary token '{RE_PRIMARY_DISPLAY_TOKEN}' match: "
        f"{re_match.get('device_name', 'NOT FOUND')}"
    )
    print(
        f"[re-stack] Restore primary token '{RESTORE_PRIMARY_DISPLAY_TOKEN}' match: "
        f"{restore_match.get('device_name', 'NOT FOUND')}"
    )

    tool = audio_tool_status()
    print(f"[re-stack] Audio switch tool: {tool}")
    print(f"[re-stack] RE audio token: {RE_AUDIO_DEVICE_TOKEN}")
    print(f"[re-stack] Restore audio token: {RESTORE_AUDIO_DEVICE_TOKEN}")
    return 0


def main() -> int:
    _enable_persistent_logging()
    args = parse_args()
    if args.command == "start":
        return start_stack(args.game, args.debug, args.passthrough)
    if args.command == "restore":
        return restore_stack()
    return inspect_state()


if __name__ == "__main__":
    raise SystemExit(main())
