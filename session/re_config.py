"""Config loading and all project-level constants for the RE stack.

No imports from other session/ modules — purely stdlib + JSON.
"""

import json
import os
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STOP_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")
STATE_PATH = os.path.join(PROJECT_ROOT, "runtime", "re_stack_state.json")
RE_STACK_LOG_PATH = os.path.join(PROJECT_ROOT, "runtime", "re_stack.log")
CRT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")
RE_STACK_CONFIG_PATH = os.path.join(PROJECT_ROOT, "re_stack_config.json")


def _load_config() -> dict:
    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[re-stack] Config not found: {RE_STACK_CONFIG_PATH} — using built-in defaults.")
        return {}
    except Exception as e:
        print(f"[re-stack] Config load error: {e} — using built-in defaults.")
        return {}


_cfg = _load_config()
_display_cfg = _cfg.get("display", {})
_audio_cfg = _cfg.get("audio", {})
_profiles_cfg = _cfg.get("game_profiles", {})
_moonlight_cfg = _cfg.get("moonlight", {})

MOONLIGHT_DIR: str = _cfg.get(
    "moonlight_dir", r"D:\Emulators\MoonlightPortable-x64-6.1.0"
)
MOONLIGHT_EXE: str = os.path.join(MOONLIGHT_DIR, "Moonlight.exe")


def _parse_rect_cfg(d: Optional[dict]) -> Optional[tuple]:
    if not d:
        return None
    try:
        return (int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
    except (KeyError, TypeError, ValueError):
        return None


MOONLIGHT_IDLE_RECT: Optional[tuple] = _parse_rect_cfg(_moonlight_cfg.get("idle_rect"))
MOONLIGHT_CRT_RECT: Optional[tuple] = _parse_rect_cfg(_moonlight_cfg.get("crt_rect"))

VDD_ATTACH_TIMEOUT_SECONDS: int = int(_cfg.get("vdd_attach_timeout_seconds", 15))
FULLSCREEN_CONFIRM_SECONDS: float = float(_cfg.get("fullscreen_confirm_seconds", 2.0))

RE_PRIMARY_DISPLAY_TOKEN: str = _display_cfg.get(
    "re_primary_token", "SudoMaker Virtual Display"
)
CRT_DISPLAY_TOKEN: str = _display_cfg.get(
    "crt_token", "NVIDIA GeForce RTX 4090 Laptop GPU"
)
CRT_TARGET_REFRESH_HZ: int = int(_display_cfg.get("crt_target_refresh_hz", 60))
RESTORE_PRIMARY_DISPLAY_TOKEN: str = _display_cfg.get(
    "restore_primary_token", "Intel(R) UHD Graphics"
)
REQUIRED_DISPLAY_GROUPS: Dict[str, List[str]] = _display_cfg.get(
    "required_groups",
    {
        "internal_display": ["Internal Display", "Intel(R) UHD Graphics"],
        "crt_display": ["CP-1262HE", "NVIDIA GeForce RTX 4090 Laptop GPU"],
        "moonlight_display": ["SudoMaker Virtual Display"],
    },
)

RE_AUDIO_DEVICE_TOKEN: str = _audio_cfg.get(
    "re_device_token", "CP-1262HE (NVIDIA High Definition Audio)"
)
RESTORE_AUDIO_DEVICE_TOKEN: str = _audio_cfg.get(
    "restore_device_token", "Speakers (Realtek(R) Audio)"
)

_default_profiles = {
    "re1": "integrations/launchbox/wrapper/profiles/re1-gog.json",
    "re2": "integrations/launchbox/wrapper/profiles/re2-gog.json",
    "re3": "integrations/launchbox/wrapper/profiles/re3-gog.json",
}
GAME_PROFILES: Dict[str, str] = {
    k: (v if os.path.isabs(v) else os.path.join(PROJECT_ROOT, v))
    for k, v in (_profiles_cfg or _default_profiles).items()
}
