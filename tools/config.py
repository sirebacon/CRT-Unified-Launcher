"""Config dump/check commands for crt_tools (Phase 1 scaffold)."""

import json
import os
from typing import Any, Dict, List, Tuple

from session.audio import audio_tool_status
from session.display_api import find_display_by_token
from session.re_config import (
    CRT_DISPLAY_TOKEN,
    CRT_TARGET_REFRESH_HZ,
    GAME_PROFILES,
    MOONLIGHT_CRT_RECT,
    MOONLIGHT_DIR,
    MOONLIGHT_EXE,
    MOONLIGHT_IDLE_RECT,
    RE_AUDIO_DEVICE_TOKEN,
    RE_PRIMARY_DISPLAY_TOKEN,
    RE_STACK_CONFIG_PATH,
    REQUIRED_DISPLAY_GROUPS,
    RESTORE_AUDIO_DEVICE_TOKEN,
    RESTORE_PRIMARY_DISPLAY_TOKEN,
)


_KNOWN_PROFILE_KEYS = {
    "profile_version", "path", "dir", "process_name", "position_only",
    "max_lock_seconds", "_gameplay_title", "_config_title", "_window_sequence",
}


def _load_raw_config() -> Tuple[Dict[str, Any], str]:
    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f), ""
    except Exception as e:
        return {}, str(e)


def config_dump() -> Dict[str, Any]:
    raw, err = _load_raw_config()
    return {
        "raw_loaded": not bool(err),
        "raw_error": err,
        "config_path": RE_STACK_CONFIG_PATH,
        "moonlight_dir": MOONLIGHT_DIR,
        "moonlight_exe": MOONLIGHT_EXE,
        "moonlight_idle_rect": MOONLIGHT_IDLE_RECT,
        "moonlight_crt_rect": MOONLIGHT_CRT_RECT,
        "display": {
            "re_primary_token": RE_PRIMARY_DISPLAY_TOKEN,
            "crt_token": CRT_DISPLAY_TOKEN,
            "crt_target_refresh_hz": CRT_TARGET_REFRESH_HZ,
            "restore_primary_token": RESTORE_PRIMARY_DISPLAY_TOKEN,
            "required_groups": REQUIRED_DISPLAY_GROUPS,
        },
        "audio": {
            "re_device_token": RE_AUDIO_DEVICE_TOKEN,
            "restore_device_token": RESTORE_AUDIO_DEVICE_TOKEN,
            "backend": audio_tool_status(),
        },
        "game_profiles": GAME_PROFILES,
        "raw": raw,
    }


def print_config_dump(data: Dict[str, Any]) -> int:
    print("Config dump")
    print(f"Config file: {data['config_path']}")
    if not data.get("raw_loaded"):
        print(f"[tools] FAIL: config dump -- could not read config: {data.get('raw_error')}")
        return 1

    print()
    print("Paths:")
    print(f"  moonlight_dir : {data['moonlight_dir']}  [exists: {os.path.isdir(data['moonlight_dir'])}]")
    print(f"  Moonlight.exe : {data['moonlight_exe']}  [exists: {os.path.isfile(data['moonlight_exe'])}]")

    print()
    print("Moonlight rects:")
    print(f"  idle_rect     : {data['moonlight_idle_rect']}")
    print(f"  crt_rect      : {data['moonlight_crt_rect']}")

    d = data["display"]
    print()
    print("Display config:")
    print(f"  re_primary_token      : {d['re_primary_token']}")
    print(f"  crt_token             : {d['crt_token']}")
    print(f"  crt_target_refresh_hz : {d['crt_target_refresh_hz']}")
    print(f"  restore_primary_token : {d['restore_primary_token']}")
    print("  required_groups:")
    for k, v in d["required_groups"].items():
        print(f"    {k}: {v}")

    a = data["audio"]
    print()
    print("Audio config:")
    print(f"  backend               : {a['backend']}")
    print(f"  re_device_token       : {a['re_device_token']}")
    print(f"  restore_device_token  : {a['restore_device_token']}")

    print()
    print("Game profiles:")
    for k, p in data["game_profiles"].items():
        print(f"  {k}: {p}  [exists: {os.path.isfile(p)}]")
    return 0


def config_check() -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []
    raw, err = _load_raw_config()
    checks.append({
        "name": "Config file readable",
        "status": "PASS" if not err else "FAIL",
        "detail": RE_STACK_CONFIG_PATH if not err else err,
    })
    checks.append({
        "name": "moonlight_dir exists",
        "status": "PASS" if os.path.isdir(MOONLIGHT_DIR) else "FAIL",
        "detail": MOONLIGHT_DIR,
    })
    checks.append({
        "name": "Moonlight.exe exists",
        "status": "PASS" if os.path.isfile(MOONLIGHT_EXE) else "FAIL",
        "detail": MOONLIGHT_EXE,
    })

    for label, token in (
        ("crt_token resolves", CRT_DISPLAY_TOKEN),
        ("re_primary_token resolves", RE_PRIMARY_DISPLAY_TOKEN),
        ("restore_primary_token resolves", RESTORE_PRIMARY_DISPLAY_TOKEN),
    ):
        match = find_display_by_token(token)
        checks.append({
            "name": label,
            "status": "PASS" if match else "WARN",
            "detail": str(match.get("device_name", "no attached display match")),
        })

    for group, tokens in REQUIRED_DISPLAY_GROUPS.items():
        ok = any(find_display_by_token(t) for t in tokens)
        checks.append({
            "name": f"required group '{group}' resolves",
            "status": "PASS" if ok else "WARN",
            "detail": " | ".join(tokens),
        })

    backend = audio_tool_status()
    checks.append({
        "name": "Audio backend available",
        "status": "PASS" if backend != "none" else "WARN",
        "detail": backend,
    })
    checks.append({
        "name": "re_device_token non-empty",
        "status": "PASS" if str(RE_AUDIO_DEVICE_TOKEN).strip() else "FAIL",
        "detail": RE_AUDIO_DEVICE_TOKEN,
    })
    checks.append({
        "name": "restore_device_token non-empty",
        "status": "PASS" if str(RESTORE_AUDIO_DEVICE_TOKEN).strip() else "FAIL",
        "detail": RESTORE_AUDIO_DEVICE_TOKEN,
    })

    for key, path in GAME_PROFILES.items():
        status = "PASS"
        detail = path
        if not os.path.isfile(path):
            status = "FAIL"
            detail = "missing file"
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    prof = json.load(f)
                if not prof.get("process_name"):
                    status = "FAIL"
                    detail = "process_name missing/empty"
            except Exception as e:
                status = "FAIL"
                detail = f"json error: {e}"
        checks.append({
            "name": f"profile '{key}' valid",
            "status": status,
            "detail": detail,
        })

    return {"checks": checks, "raw_loaded": not bool(err), "raw": raw}


def print_config_check(data: Dict[str, Any]) -> int:
    fail = 0
    warn = 0
    print("Config check")
    print()
    for c in data["checks"]:
        status = c["status"]
        if status == "FAIL":
            fail += 1
        elif status == "WARN":
            warn += 1
        print(f"  {status:<4} {c['name']}")
        if c.get("detail"):
            print(f"        {c['detail']}")
    print()
    if fail:
        print(f"[tools] FAIL: config check -- {fail} failure(s), {warn} warning(s)")
        return 1
    print(f"[tools] PASS: config check -- 0 failures, {warn} warning(s)")
    return 0


def config_check_wrapper(profile_path: str) -> Dict[str, Any]:
    """Validate a LaunchBox wrapper profile JSON against the expected schema."""
    checks: List[Dict[str, str]] = []

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            prof = json.load(f)
    except Exception as e:
        return {"profile_path": profile_path, "load_error": str(e), "checks": []}

    pname = prof.get("process_name")
    checks.append({
        "name": "process_name present and non-empty",
        "status": "PASS" if pname else "FAIL",
        "detail": str(pname) if pname else "(missing or empty)",
    })

    exe_path = prof.get("path", "")
    checks.append({
        "name": "path field present",
        "status": "PASS" if exe_path else "FAIL",
        "detail": exe_path or "(not set)",
    })
    if exe_path:
        checks.append({
            "name": "path exists on disk",
            "status": "PASS" if os.path.isfile(exe_path) else "WARN",
            "detail": exe_path,
        })

    if prof.get("position_only"):
        for field in ("_gameplay_title", "_config_title"):
            val = prof.get(field)
            checks.append({
                "name": f"{field} present (required when position_only=true)",
                "status": "PASS" if val else "FAIL",
                "detail": repr(val) if val else "(missing)",
            })

    unknown = set(prof.keys()) - _KNOWN_PROFILE_KEYS
    if unknown:
        checks.append({
            "name": "no unknown top-level keys",
            "status": "WARN",
            "detail": ", ".join(sorted(unknown)),
        })

    return {"profile_path": profile_path, "load_error": None, "checks": checks}


def print_config_check_wrapper(data: Dict[str, Any]) -> int:
    print(f"Wrapper profile: {data.get('profile_path', '?')}")
    print()
    if data.get("load_error"):
        print(f"[tools] FAIL: config check --wrapper -- {data['load_error']}")
        return 1
    fail = warn = 0
    for c in data["checks"]:
        status = c["status"]
        if status == "FAIL":
            fail += 1
        elif status == "WARN":
            warn += 1
        print(f"  {status:<4} {c['name']}")
        if c.get("detail"):
            print(f"        {c['detail']}")
    print()
    if fail:
        print(f"[tools] FAIL: config check --wrapper -- {fail} failure(s), {warn} warning(s)")
        return 1
    print(f"[tools] PASS: config check --wrapper -- 0 failures, {warn} warning(s)")
    return 0
