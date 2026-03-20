"""Config loading/validation for the VLC Live TV launcher."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CRT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "crt_config.json")
_LOCAL_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "crt_config.local.json")

Rect = Tuple[int, int, int, int]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _resolve_rect(value: Any, fallback: Rect) -> Rect:
    if isinstance(value, dict):
        try:
            return (int(value["x"]), int(value["y"]), int(value["w"]), int(value["h"]))
        except Exception:
            return fallback
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        except Exception:
            return fallback
    return fallback


def load_live_tv_config() -> Dict[str, Any]:
    cfg = _load_json(_CRT_CONFIG_PATH)
    if os.path.exists(_LOCAL_CONFIG_PATH):
        try:
            cfg.update(_load_json(_LOCAL_CONFIG_PATH))
        except Exception:
            pass

    li = cfg.get("launcher_integration", {})
    default_crt_rect: Rect = (
        int(li.get("x", -1211)),
        int(li.get("y", 43)),
        int(li.get("w", 1057)),
        int(li.get("h", 835)),
    )
    pri = li.get("primary_on_exit", {"x": 100, "y": 100, "w": 1280, "h": 720})
    default_main_rect: Rect = (
        int(pri.get("x", 100)),
        int(pri.get("y", 100)),
        int(pri.get("w", 1280)),
        int(pri.get("h", 720)),
    )

    user_rect_value = cfg.get("live_tv_rect")
    user_rect_is_set = user_rect_value is not None

    return {
        "enabled": bool(cfg.get("live_tv_enabled", True)),
        "vlc_path": str(cfg.get("live_tv_vlc_path", r"C:\Program Files\VideoLAN\VLC\vlc.exe")),
        "playlist_url": str(cfg.get("live_tv_playlist_url", "")).strip(),
        "network_caching_ms": int(cfg.get("live_tv_network_caching_ms", 1500)),
        "fullscreen": bool(cfg.get("live_tv_fullscreen", True)),
        "disable_vlc_autoresize": bool(cfg.get("live_tv_disable_vlc_autoresize", True)),
        "crt_rect": _resolve_rect(user_rect_value, default_crt_rect),
        "user_rect_is_set": user_rect_is_set,
        "main_rect": _resolve_rect(cfg.get("live_tv_main_rect"), default_main_rect),
        "window_find_timeout_sec": float(cfg.get("live_tv_window_find_timeout_sec", 20.0)),
        "restore_main_on_exit": bool(cfg.get("live_tv_restore_main_on_exit", True)),
    }


def validate_live_tv_config(cfg: Dict[str, Any]) -> str:
    if not cfg.get("enabled", True):
        return "Live TV is disabled in config (live_tv_enabled=false)."
    vlc_path = cfg.get("vlc_path", "")
    if not vlc_path:
        return "Missing live_tv_vlc_path in config."
    if not os.path.isfile(vlc_path):
        return f"VLC not found: {vlc_path}"
    if not cfg.get("playlist_url"):
        return (
            "Missing live_tv_playlist_url. Put it in crt_config.local.json "
            "(gitignored) to keep it private."
        )
    return ""


def save_live_tv_rect_local(rect: Rect) -> None:
    data: Dict[str, Any] = {}
    if os.path.exists(_LOCAL_CONFIG_PATH):
        try:
            data = _load_json(_LOCAL_CONFIG_PATH)
        except Exception:
            data = {}
    x, y, w, h = rect
    data["live_tv_rect"] = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
    with open(_LOCAL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
