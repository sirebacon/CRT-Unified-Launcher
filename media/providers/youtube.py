"""YouTubeProvider — Tier 1 yt-dlp-backed provider for YouTube URLs."""

import subprocess
from typing import Optional
from urllib.parse import urlparse, parse_qs

from media.providers.base import Provider, ProviderCapabilities

_VALID_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


class YouTubeProvider(Provider):
    capabilities = ProviderCapabilities(
        uses_ytdl=True,
        supports_playlist=True,
        supports_title_fetch=True,
        supports_resume=True,
        requires_cookies=False,
    )

    def __init__(
        self,
        yt_dlp_path: str = "yt-dlp",
        cookies_from_browser: str = "",
        cookies_file: str = "",
    ):
        self._yt_dlp_path = yt_dlp_path
        self._cookies_from_browser = cookies_from_browser
        self._cookies_file = cookies_file

    def name(self) -> str:
        return "YouTube"

    def can_handle(self, url: str) -> bool:
        try:
            return urlparse(url).netloc.lower() in _VALID_HOSTS
        except Exception:
            return False

    def validate(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            if parsed.scheme not in ("http", "https"):
                return "URL must start with http:// or https://"
            if host not in _VALID_HOSTS:
                return f"Not a YouTube URL (host: {parsed.netloc!r})"
            return None
        except Exception as e:
            return f"Invalid URL: {e}"

    def _cookie_args(self) -> list:
        """Return yt-dlp CLI args for cookie authentication."""
        if self._cookies_from_browser:
            return ["--cookies-from-browser", self._cookies_from_browser]
        if self._cookies_file:
            return ["--cookies", self._cookies_file]
        return []

    def fetch_title(self, url: str) -> str:
        try:
            result = subprocess.run(
                [self._yt_dlp_path, "--get-title", "--no-playlist", "--js-runtimes", "node"]
                + self._cookie_args()
                + [url],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def is_playlist(self, url: str) -> bool:
        try:
            return bool(parse_qs(urlparse(url).query).get("list"))
        except Exception:
            return "list=" in url

    def resolve_target(self, url: str, quality: str = "best") -> dict:
        playlist = self.is_playlist(url)
        return {
            "target_url": url,
            "is_playlist": playlist,
            "extra_mpv_flags": ["--ytdl-raw-options=yes-playlist="] if playlist else [],
            "subtitle_urls": [],
            "extra_headers": {},
            "playlist_items": [],
            "current_index": 0,
        }

    def get_continue_metadata(self, url: str) -> dict:
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            qs = parse_qs(parsed.query)
            if host in _VALID_HOSTS:
                video_ids = qs.get("v", [])
                if video_ids:
                    video_id = video_ids[0]
                elif host == "youtu.be":
                    video_id = parsed.path.lstrip("/").split("/")[0]
                else:
                    return {}
                if not video_id:
                    return {}
                return {
                    "continue_key":  f"youtube:video:{video_id}",
                    "entity_type":   "video",
                    "series_title":  "",
                    "episode_title": "",
                    "episode_index": None,
                    "episode_url":   url,
                }
        except Exception:
            pass
        return {}

    def mpv_extra_args(self, url: str, quality: str, config: dict) -> list:
        # Collect all --ytdl-raw-options entries into a single flag.
        # mpv replaces the entire ytdl-raw-options list each time you pass
        # --ytdl-raw-options=..., so multiple flags lose all but the last one.
        # The comma-separated form --ytdl-raw-options=k1=v1,k2=v2 accumulates correctly.
        raw = {}

        if self.is_playlist(url):
            raw["yes-playlist"] = ""

        # Node.js runtime — required for YouTube's n-challenge (without it yt-dlp
        # can only see storyboard images and reports "Requested format is not available")
        raw["js-runtimes"] = "node"

        if self._cookies_from_browser:
            raw["cookies-from-browser"] = self._cookies_from_browser
        elif self._cookies_file:
            raw["cookies"] = self._cookies_file

        args = [f"--ytdl-raw-options={','.join(f'{k}={v}' for k, v in raw.items())}"]

        presets = config.get("youtube_quality_presets", {})
        if quality and quality != "best":
            preset = presets.get(quality, {})
            fmt = preset.get("ytdl_format", "")
            if fmt:
                args.append(f"--ytdl-format={fmt}")
        return args
