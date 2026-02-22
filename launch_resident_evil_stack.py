"""Resident Evil stack launcher and restore helper.

Usage:
    python launch_resident_evil_stack.py start --game re1
    python launch_resident_evil_stack.py start --game re2
    python launch_resident_evil_stack.py manual --game re1
    python launch_resident_evil_stack.py restore
    python launch_resident_evil_stack.py inspect
"""

import argparse
import os
import sys
from datetime import datetime
from typing import List

from default_restore import restore_defaults_from_backup
from session.audio import audio_tool_status
from session.display_api import (
    current_primary_display,
    enumerate_attached_displays,
    find_display_by_token,
)
from session.moonlight_adjuster import adjust_moonlight, capture_moonlight_pos
from session.re_auto_mode import start_stack as start_stack_auto
from session.re_config import (
    GAME_PROFILES,
    RE_AUDIO_DEVICE_TOKEN,
    RE_PRIMARY_DISPLAY_TOKEN,
    RE_STACK_LOG_PATH,
    RESTORE_AUDIO_DEVICE_TOKEN,
    RESTORE_PRIMARY_DISPLAY_TOKEN,
    STATE_PATH,
    STOP_FLAG,
)
from session.re_game import find_wrapper_pids
from session.re_manual_mode import manual_stack as start_stack_manual
from session.re_state import apply_restore_system_state

try:
    import psutil
except Exception:
    psutil = None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Set up the CRT environment for Resident Evil and wait for the game."
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser(
        "start",
        help="Prepare the stack and wait for manual game launch in Moonlight.",
    )
    p_start.add_argument(
        "--game",
        choices=sorted(GAME_PROFILES.keys()),
        required=True,
        help="Which game profile to use (for gameplay window detection).",
    )

    p_manual = sub.add_parser(
        "manual",
        help="Guided manual RE mode (you control display settings/primary).",
    )
    p_manual.add_argument(
        "--game",
        choices=sorted(GAME_PROFILES.keys()),
        required=True,
        help="Which game profile to use (for process monitoring/log labeling).",
    )

    sub.add_parser("restore", help="Stop enforcement and restore display/audio defaults.")
    sub.add_parser("inspect", help="Inspect display matches and audio tool availability.")
    sub.add_parser(
        "set-idle-pos",
        help="Capture current Moonlight window position and save as the idle (restore) rect.",
    )
    sub.add_parser(
        "set-crt-pos",
        help="Capture current Moonlight window position and save as the CRT rect.",
    )
    sub.add_parser(
        "adjust-moonlight",
        help="Interactive keyboard adjuster: nudge the Moonlight window and save the result.",
    )
    return p.parse_args()


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
# Commands (shared)
# ---------------------------------------------------------------------------

def restore_stack() -> int:
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as f:
            f.write("stop\n")
    except Exception:
        pass

    stopped: List[int] = []
    pids = find_wrapper_pids()
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

    state_ok = apply_restore_system_state()
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    if args.command == "adjust-moonlight":
        return adjust_moonlight()

    _enable_persistent_logging()

    if args.command == "start":
        return start_stack_auto(args.game, restore_stack)
    if args.command == "manual":
        return start_stack_manual(args.game)
    if args.command == "restore":
        return restore_stack()
    if args.command == "set-idle-pos":
        return capture_moonlight_pos("idle_rect")
    if args.command == "set-crt-pos":
        return capture_moonlight_pos("crt_rect")
    return inspect_state()


if __name__ == "__main__":
    raise SystemExit(main())
