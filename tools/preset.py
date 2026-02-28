"""CRT resolution preset management for crt_tools."""

import json
import os
from typing import Dict, List, Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_PRESETS_PATH = os.path.join(_PROJECT_ROOT, "crt_presets.json")
_CRT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "crt_config.json")
_RE_STACK_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "re_stack_config.json")
_GAMING_MANIFEST_PATH = os.path.join(_PROJECT_ROOT, "profiles", "gaming-manifest.json")

# Maps emulator_rects key → profile filename (relative to profiles/)
_EMULATOR_PROFILE_FILES: Dict[str, str] = {
    "retroarch": "retroarch-session.json",
    "dolphin":   "dolphin-session.json",
    "ppsspp":    "ppsspp-session.json",
    "pcsx2":     "pcsx2-session.json",
    "launchbox": "launchbox-session.json",
}


def _profile_path(name: str) -> str:
    return os.path.join(_PROJECT_ROOT, "profiles", _EMULATOR_PROFILE_FILES[name])


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _load_presets() -> dict:
    return _load_json(_PRESETS_PATH)


def _save_presets(data: dict) -> None:
    _save_json(_PRESETS_PATH, data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preset_list() -> dict:
    """Return {active, presets: [{name, note}]}."""
    try:
        data = _load_presets()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    active = data.get("active", "")
    presets = data.get("presets", {})
    return {
        "ok": True,
        "active": active,
        "presets": [
            {"name": name, "note": entry.get("note", "")}
            for name, entry in presets.items()
        ],
    }


def preset_apply(name: str) -> dict:
    """Write preset values to all targets. Returns {ok, name, changed, errors}."""
    try:
        data = _load_presets()
    except Exception as e:
        return {"ok": False, "name": name, "changed": [], "errors": [f"Cannot load presets: {e}"]}

    presets = data.get("presets", {})
    if name not in presets:
        known = list(presets.keys())
        return {
            "ok": False,
            "name": name,
            "changed": [],
            "errors": [f"Preset '{name}' not found. Known: {known}"],
        }

    preset = presets[name]
    emulator_rects: dict = preset.get("emulator_rects", {})
    plex_rect: Optional[dict] = preset.get("plex_rect")
    moonlight_crt_rect: Optional[dict] = preset.get("moonlight_crt_rect")
    aspect_ratio: Optional[str] = preset.get("aspect_ratio")

    changed: List[str] = []
    errors: List[str] = []

    # 1. Update each emulator profile JSON
    for key, rect in emulator_rects.items():
        if key not in _EMULATOR_PROFILE_FILES:
            errors.append(f"Unknown emulator key '{key}' — skipped")
            continue
        path = _profile_path(key)
        try:
            profile = _load_json(path)
            profile["x"] = rect["x"]
            profile["y"] = rect["y"]
            profile["w"] = rect["w"]
            profile["h"] = rect["h"]
            _save_json(path, profile)
            changed.append(f"profiles/{_EMULATOR_PROFILE_FILES[key]}")
        except Exception as e:
            errors.append(f"profiles/{_EMULATOR_PROFILE_FILES[key]}: {e}")

    # 2. Update crt_config.json — launcher_integration and plex
    try:
        crt_cfg = _load_json(_CRT_CONFIG_PATH)
        modified = False

        if "launchbox" in emulator_rects:
            lb = emulator_rects["launchbox"]
            li = crt_cfg.setdefault("launcher_integration", {})
            li["x"] = lb["x"]
            li["y"] = lb["y"]
            li["w"] = lb["w"]
            li["h"] = lb["h"]
            modified = True

        if plex_rect is not None:
            p = crt_cfg.setdefault("plex", {})
            p["x"] = plex_rect["x"]
            p["y"] = plex_rect["y"]
            p["w"] = plex_rect["w"]
            p["h"] = plex_rect["h"]
            modified = True

        if modified:
            _save_json(_CRT_CONFIG_PATH, crt_cfg)
            changed.append("crt_config.json")
    except Exception as e:
        errors.append(f"crt_config.json: {e}")

    # 3. Update re_stack_config.json — moonlight.crt_rect
    if moonlight_crt_rect is not None:
        try:
            re_cfg = _load_json(_RE_STACK_CONFIG_PATH)
            re_cfg.setdefault("moonlight", {})["crt_rect"] = moonlight_crt_rect
            _save_json(_RE_STACK_CONFIG_PATH, re_cfg)
            changed.append("re_stack_config.json")
        except Exception as e:
            errors.append(f"re_stack_config.json: {e}")

    # 4. Update gaming-manifest.json — video_aspect_ratio in the retroarch.cfg patch
    if aspect_ratio is not None:
        try:
            manifest = _load_json(_GAMING_MANIFEST_PATH)
            patch = _find_retroarch_cfg_patch(manifest)
            if patch is None:
                errors.append("profiles/gaming-manifest.json: retroarch.cfg patch not found")
            else:
                patch.setdefault("set_values", {})["video_aspect_ratio"] = aspect_ratio
                _save_json(_GAMING_MANIFEST_PATH, manifest)
                changed.append("profiles/gaming-manifest.json")
        except Exception as e:
            errors.append(f"profiles/gaming-manifest.json: {e}")

    # 5. Update active preset
    try:
        data["active"] = name
        _save_presets(data)
    except Exception as e:
        errors.append(f"crt_presets.json (update active): {e}")

    return {"ok": len(errors) == 0, "name": name, "changed": changed, "errors": errors}


def preset_save(name: str) -> dict:
    """Read current values from all targets and write into a preset entry.

    Returns {ok, name, created, error}.
    """
    try:
        data = _load_presets()
    except Exception as e:
        return {"ok": False, "name": name, "created": False, "error": str(e)}

    presets = data.setdefault("presets", {})
    existing = presets.get(name, {})

    errors: List[str] = []
    emulator_rects: dict = {}

    # 1. Read emulator rects from profile JSONs
    for key in _EMULATOR_PROFILE_FILES:
        path = _profile_path(key)
        try:
            profile = _load_json(path)
            emulator_rects[key] = {
                "x": profile["x"],
                "y": profile["y"],
                "w": profile["w"],
                "h": profile["h"],
            }
        except Exception as e:
            errors.append(f"profiles/{_EMULATOR_PROFILE_FILES[key]}: {e}")

    # 2. Read plex_rect from crt_config.json
    plex_rect: Optional[dict] = None
    try:
        crt_cfg = _load_json(_CRT_CONFIG_PATH)
        p = crt_cfg.get("plex", {})
        plex_rect = {"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"]}
    except Exception as e:
        errors.append(f"crt_config.json (plex): {e}")

    # 3. Read moonlight_crt_rect from re_stack_config.json
    moonlight_crt_rect: Optional[dict] = None
    try:
        re_cfg = _load_json(_RE_STACK_CONFIG_PATH)
        r = re_cfg.get("moonlight", {}).get("crt_rect", {})
        moonlight_crt_rect = {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]}
    except Exception as e:
        errors.append(f"re_stack_config.json (moonlight.crt_rect): {e}")

    # 4. Read aspect_ratio from gaming-manifest.json
    aspect_ratio: Optional[str] = None
    try:
        manifest = _load_json(_GAMING_MANIFEST_PATH)
        patch = _find_retroarch_cfg_patch(manifest)
        if patch is None:
            errors.append("profiles/gaming-manifest.json: retroarch.cfg patch not found")
        else:
            aspect_ratio = patch.get("set_values", {}).get("video_aspect_ratio")
    except Exception as e:
        errors.append(f"profiles/gaming-manifest.json: {e}")

    if errors:
        return {"ok": False, "name": name, "created": False, "error": "; ".join(errors)}

    created = name not in presets
    entry: dict = {}
    if "note" in existing:
        entry["note"] = existing["note"]
    if aspect_ratio is not None:
        entry["aspect_ratio"] = aspect_ratio
    entry["emulator_rects"] = emulator_rects
    if plex_rect is not None:
        entry["plex_rect"] = plex_rect
    if moonlight_crt_rect is not None:
        entry["moonlight_crt_rect"] = moonlight_crt_rect

    presets[name] = entry

    try:
        _save_presets(data)
    except Exception as e:
        return {"ok": False, "name": name, "created": created, "error": str(e)}

    return {"ok": True, "name": name, "created": created, "error": None}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_retroarch_cfg_patch(manifest: dict) -> Optional[dict]:
    """Find the retroarch_cfg patch whose path ends with 'retroarch.cfg'."""
    for patch in manifest.get("patches", []):
        if patch.get("type") == "retroarch_cfg":
            path = patch.get("path", "")
            if path.lower().endswith("retroarch.cfg"):
                return patch
    return None


# ---------------------------------------------------------------------------
# Print functions (CLI output)
# ---------------------------------------------------------------------------

def print_preset_list(data: dict) -> int:
    if not data.get("ok"):
        print(f"[preset] FAIL: {data.get('error', 'unknown error')}")
        return 1
    active = data["active"]
    presets = data["presets"]
    if not presets:
        print("No presets defined.")
        return 0
    print("Available presets:")
    for entry in presets:
        marker = "*" if entry["name"] == active else " "
        note = f'  "{entry["note"]}"' if entry["note"] else ""
        print(f"  {marker} {entry['name']:<16}{note}")
    return 0


def print_preset_apply(data: dict) -> int:
    name = data.get("name", "?")
    errors = data.get("errors", [])
    changed = data.get("changed", [])
    if errors:
        print(f"[preset] apply '{name}' — completed with errors:")
        for c in changed:
            print(f"  updated: {c}")
        for e in errors:
            print(f"  ERROR:   {e}")
        return 1
    print(f"[preset] apply '{name}' — OK")
    for c in changed:
        print(f"  updated: {c}")
    return 0


def print_preset_save(data: dict) -> int:
    name = data.get("name", "?")
    if not data.get("ok"):
        print(f"[preset] save '{name}' — FAIL: {data.get('error', 'unknown error')}")
        return 1
    verb = "created" if data.get("created") else "updated"
    print(f"[preset] save '{name}' — {verb}")
    return 0
