"""Shared preflight helpers for Resident Evil stack modes."""

import os
import subprocess
from typing import Dict, List

from session.display_api import enumerate_attached_displays, find_display_by_token


def ensure_required_displays(required_display_groups: Dict[str, List[str]]) -> bool:
    attached = enumerate_attached_displays()
    print(f"[re-stack] Attached display count: {len(attached)}")

    missing: List[str] = []
    for label, tokens in required_display_groups.items():
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


def attached_display_count() -> int:
    return len(enumerate_attached_displays())


def open_windows_display_settings() -> None:
    try:
        if os.name == "nt" and hasattr(os, "startfile"):
            os.startfile("ms-settings:display")  # type: ignore[attr-defined]
            print("[re-stack] Opened Windows Display Settings (ms-settings:display).")
            return
    except Exception as e:
        print(f"[re-stack] Could not open Display Settings via startfile: {e}")

    for cmd in (
        ["explorer.exe", "ms-settings:display"],
        ["cmd", "/c", "start", "", "ms-settings:display"],
    ):
        try:
            subprocess.Popen(cmd)
            print("[re-stack] Opened Windows Display Settings (ms-settings:display).")
            return
        except Exception:
            continue
    print("[re-stack] Could not open Windows Display Settings automatically.")
