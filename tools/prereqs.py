"""Prerequisite checks for crt_tools (Phase 1 scaffold)."""

import importlib.util
import json
import os
from typing import Any, Dict, List

from session.audio import audio_tool_status
from session.display_api import find_display_by_token
from session.re_config import (
    GAME_PROFILES,
    MOONLIGHT_DIR,
    MOONLIGHT_EXE,
    RE_PRIMARY_DISPLAY_TOKEN,
    RE_STACK_CONFIG_PATH,
)

try:
    import psutil as _psutil
except Exception:
    _psutil = None


def _has_import(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _apollo_processes() -> List[Dict[str, Any]]:
    if _psutil is None:
        return []
    wanted = {"apollodisplayhost.exe", "apollo.exe", "apollosystray.exe"}
    found: List[Dict[str, Any]] = []
    for proc in _psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in wanted:
                found.append({"pid": int(proc.info["pid"]), "name": proc.info["name"]})
        except Exception:
            continue
    return found


def prereqs_check() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "pywin32": _has_import("win32api"),
        "psutil": _has_import("psutil"),
        "audio_backend": audio_tool_status(),
        "moonlight_dir_exists": os.path.isdir(MOONLIGHT_DIR),
        "moonlight_exe_exists": os.path.isfile(MOONLIGHT_EXE),
        "apollo": _apollo_processes(),
        "config_readable": False,
        "profiles": [],
        "vdd_attached": bool(find_display_by_token(RE_PRIMARY_DISPLAY_TOKEN)),
    }

    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            json.load(f)
        result["config_readable"] = True
    except Exception:
        result["config_readable"] = False

    profiles: List[Dict[str, Any]] = []
    for key, path in GAME_PROFILES.items():
        profiles.append({"key": key, "path": path, "exists": os.path.isfile(path)})
    result["profiles"] = profiles
    return result


def print_prereqs_check(data: Dict[str, Any]) -> int:
    fail = 0
    warn = 0

    def _line(status: str, msg: str) -> None:
        nonlocal fail, warn
        if status == "FAIL":
            fail += 1
        elif status == "WARN":
            warn += 1
        print(f"  {status:<4} {msg}")

    print("Prereqs check")
    print()
    print("Python packages:")
    _line("PASS" if data["pywin32"] else "FAIL", "pywin32")
    _line("PASS" if data["psutil"] else "FAIL", "psutil")

    print()
    print("Audio backend:")
    backend = data.get("audio_backend", "none")
    _line("PASS" if backend != "none" else "WARN", backend)

    print()
    print("Moonlight:")
    _line("PASS" if data["moonlight_dir_exists"] else "FAIL", f"moonlight_dir: {MOONLIGHT_DIR}")
    _line("PASS" if data["moonlight_exe_exists"] else "FAIL", f"Moonlight.exe: {MOONLIGHT_EXE}")

    print()
    print("Apollo / VDD:")
    apollo = data.get("apollo") or []
    if apollo:
        proc_txt = ", ".join(f"{p['name']} (PID {p['pid']})" for p in apollo)
        _line("PASS", f"Apollo process running: {proc_txt}")
    else:
        _line("WARN", "Apollo process not detected")
    _line("PASS" if data["vdd_attached"] else "WARN", "SudoMaker VDD attached")

    print()
    print("Config:")
    _line("PASS" if data["config_readable"] else "FAIL", f"{RE_STACK_CONFIG_PATH} readable")
    for p in data.get("profiles", []):
        _line("PASS" if p["exists"] else "FAIL", f"{p['key']} profile: {p['path']}")

    print()
    if fail:
        print(f"[tools] FAIL: prereqs -- {fail} failure(s), {warn} warning(s)")
        return 1
    print(f"[tools] PASS: prereqs -- 0 failures, {warn} warning(s)")
    return 0

