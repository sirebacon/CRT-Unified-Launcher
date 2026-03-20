"""VLC command/process helpers for Live TV."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List


def build_vlc_command(cfg: Dict[str, Any]) -> List[str]:
    cmd: List[str] = [cfg["vlc_path"], cfg["playlist_url"]]
    cmd.append(f"--network-caching={int(cfg['network_caching_ms'])}")
    if bool(cfg.get("disable_vlc_autoresize", True)):
        # Prevent VLC UI from resizing itself to the incoming video geometry.
        # This keeps manual CRT window placement stable.
        cmd.append("--no-qt-video-autoresize")
    # Fullscreen conflicts with precise x/y/w/h control. If user explicitly
    # configured a live_tv_rect, prefer windowed mode so rect can be honored.
    use_fullscreen = bool(cfg.get("fullscreen", True)) and not bool(cfg.get("user_rect_is_set", False))
    if use_fullscreen:
        cmd.append("--fullscreen")
    return cmd


def start_vlc(cfg: Dict[str, Any]) -> subprocess.Popen:
    cmd = build_vlc_command(cfg)
    return subprocess.Popen(cmd)
