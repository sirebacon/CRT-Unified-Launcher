"""Game process helpers for the RE stack."""

import json
import os
from typing import List

try:
    import psutil
except Exception:
    psutil = None

from session.re_config import GAME_PROFILES


def find_wrapper_pids() -> List[int]:
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


def re_process_names() -> List[str]:
    """Return the lowercase process names declared across all loaded game profiles."""
    names: List[str] = []
    for profile_path in GAME_PROFILES.values():
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name in data.get("process_name", []):
                names.append(str(name).lower())
        except Exception:
            continue
    return names


def is_re_game_running() -> bool:
    """Return True if any RE game process from the known profiles is currently running."""
    if psutil is None:
        return False
    known = set(re_process_names())
    if not known:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() in known:
                return True
        except Exception:
            continue
    return False
