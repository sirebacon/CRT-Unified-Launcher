"""
Paths and identifiers shared across all GUI modules.

Nothing here imports from gui.* — safe to import from anywhere.
"""
from __future__ import annotations

import os
import shutil
import sys


# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------

def _get_launcher_dir() -> str:
    """Absolute path to the CRT-Unified-Launcher project root.

    Works whether we are running as a plain .py script or as a
    PyInstaller --onefile frozen executable.
    """
    if getattr(sys, "frozen", False):
        # Frozen: the .exe lives in the project root
        return os.path.dirname(sys.executable)
    # Normal: this file lives at <root>/gui/constants.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Python interpreter (for running backend .py scripts as subprocesses)
# ---------------------------------------------------------------------------

def _get_python_exe() -> str:
    """Path to the Python interpreter used to run backend scripts.

    When running as a plain .py script, sys.executable IS the interpreter.
    When running as a frozen .exe, we must find the system Python instead,
    because the .exe cannot execute loose .py files itself.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable

    # Frozen: search PATH for python.exe
    found = shutil.which("python") or shutil.which("python3")
    if found:
        return found

    # Last resort: look next to the .exe (e.g. an embedded distribution)
    exe_dir = os.path.dirname(sys.executable)
    for name in ("python.exe", "python3.exe"):
        candidate = os.path.join(exe_dir, name)
        if os.path.exists(candidate):
            return candidate

    raise RuntimeError(
        "Python interpreter not found. "
        "Ensure python.exe is on PATH before launching CRT Station."
    )


LAUNCHER_DIR: str = _get_launcher_dir()
PYTHON_EXE: str = _get_python_exe()

# ---------------------------------------------------------------------------
# External fixed paths (mirrors crt_station.py — not changed there)
# ---------------------------------------------------------------------------

LAUNCHBOX_EMULATORS_XML: str = r"D:\Emulators\LaunchBox\Data\Emulators.xml"

# ---------------------------------------------------------------------------
# Backend script names (relative to LAUNCHER_DIR)
# ---------------------------------------------------------------------------

SCRIPTS: dict[str, str] = {
    "generic_launcher":  "launch_generic.py",
    "session_launcher":  "launch_session.py",
    "plex_launcher":     "launch_plex.py",
    "youtube_launcher":  "launch_youtube.py",
    "live_tv_launcher":  "launch_live_tv.py",
    "re_launcher":       "launch_resident_evil_stack.py",
    "crt_tools":         "crt_tools.py",
}

# Profile paths (relative to LAUNCHER_DIR)
PROFILES: dict[str, str] = {
    "retroarch_session": os.path.join("profiles", "retroarch-session.json"),
    "gaming_manifest":   os.path.join("profiles", "gaming-manifest.json"),
}
