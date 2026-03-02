"""Config loading, URL helpers, quality presets."""

import json
import os
import subprocess
import sys
from typing import Optional
from urllib.parse import urlparse, parse_qs

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CRT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "crt_config.json")
_MPV_PROFILE_PATH = os.path.join(_PROJECT_ROOT, "profiles", "mpv-session.json")
_PRESETS_PATH = os.path.join(_PROJECT_ROOT, "crt_presets.json")
_LOG_PATH = os.path.join(_PROJECT_ROOT, "runtime", "youtube.log")
_PIPE_NAME = r'\\.\pipe\crt-mpv-ipc'

_VALID_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config() -> dict:
    """Load all config needed by the launcher.

    Returns a dict with keys: mpv_path, yt_dlp_path, x, y, w, h,
    youtube_audio_device, youtube_quality_presets.
    """
    try:
        cfg = load_json(_CRT_CONFIG_PATH)
    except Exception as e:
        print(f"[youtube] Cannot read crt_config.json: {e}")
        sys.exit(1)

    mpv_path = cfg.get("mpv_path", "mpv")
    yt_dlp_path = cfg.get("yt_dlp_path", "yt-dlp")

    try:
        profile = load_json(_MPV_PROFILE_PATH)
        x, y, w, h = profile["x"], profile["y"], profile["w"], profile["h"]
    except Exception as e:
        print(f"[youtube] Cannot read profiles/mpv-session.json: {e}")
        sys.exit(1)

    return {
        "mpv_path": mpv_path,
        "yt_dlp_path": yt_dlp_path,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "youtube_audio_device": cfg.get("youtube_audio_device", ""),
        "youtube_quality_presets": cfg.get("youtube_quality_presets", {}),
    }


def is_playlist_url(url: str) -> bool:
    """Return True if the URL carries a YouTube playlist parameter."""
    try:
        return bool(parse_qs(urlparse(url).query).get("list"))
    except Exception:
        return "list=" in url


def fetch_title(yt_dlp_path: str, url: str) -> str:
    """Fetch video title via yt-dlp. Returns title string or empty string on failure."""
    try:
        result = subprocess.run(
            [yt_dlp_path, "--get-title", "--no-playlist", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def validate_youtube_url(url: str) -> Optional[str]:
    """Return None if valid, else an error message string."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "URL must start with http:// or https://"
        if parsed.netloc not in _VALID_HOSTS:
            return f"Not a YouTube URL (host: {parsed.netloc!r})"
        return None
    except Exception as e:
        return f"Invalid URL: {e}"


def load_quality_presets(cfg: dict) -> dict:
    """Return the quality presets dict from config."""
    return cfg.get("youtube_quality_presets", {})


def apply_quality_preset(mpv_cmd: list, preset_name: str, presets: dict) -> list:
    """Append --ytdl-format=... to mpv_cmd if the preset specifies it."""
    if not preset_name or preset_name == "best":
        return mpv_cmd
    preset = presets.get(preset_name, {})
    if not preset:
        return mpv_cmd
    fmt = preset.get("ytdl_format", "")
    if fmt:
        mpv_cmd = list(mpv_cmd)
        mpv_cmd.append(f"--ytdl-format={fmt}")
    return mpv_cmd


def paste_from_clipboard() -> Optional[str]:
    """Read text from Windows clipboard. Returns stripped string or None."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        return text.strip() if text else None
    except Exception:
        return None
