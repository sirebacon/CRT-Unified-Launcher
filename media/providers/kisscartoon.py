"""KissCartoonProvider - Tier 3 browser-backed provider for kisscartoon.sh URLs.

GCS bucket returns HTTP 403 to all Python clients; only Chrome's media element
can access it. resolve_target() returns requires_mpv=False to route to
browser_launcher instead of mpv.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from media.providers.base import Provider, ProviderCapabilities

_HANDLED_HOSTS = {"kisscartoon.sh", "www.kisscartoon.sh"}


def _slug_to_title(path: str) -> str:
    """Convert a URL path slug to a human-readable title.

    /Cartoon/2-Stupid-Dogs/Season-01-Episode-01-a-Red
    → "Season 01 Episode 01 A Red"
    """
    # Take last non-empty path segment
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    slug = parts[-1]
    # Strip trailing query junk (shouldn't be present after urlparse, but be safe)
    slug = slug.split("?")[0]
    # Replace hyphens with spaces, then title-case
    title = re.sub(r"-+", " ", slug).strip()
    return title.title()


class KissCartoonProvider(Provider):
    capabilities = ProviderCapabilities(
        uses_ytdl=False,
        supports_playlist=False,
        supports_title_fetch=True,
        supports_resume=False,
        requires_cookies=False,
    )

    def name(self) -> str:
        return "KissCartoon"

    def can_handle(self, url: str) -> bool:
        try:
            return urlparse(url).netloc in _HANDLED_HOSTS
        except Exception:
            return False

    def validate(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
        except Exception as exc:
            return f"Invalid URL: {exc}"
        if parsed.scheme not in ("http", "https"):
            return "URL must start with http:// or https://"
        if parsed.netloc not in _HANDLED_HOSTS:
            return f"Not a KissCartoon URL (host: {parsed.netloc!r})"
        return None

    def fetch_title(self, url: str) -> str:
        try:
            return _slug_to_title(urlparse(url).path)
        except Exception:
            return ""

    def is_playlist(self, url: str) -> bool:
        return False

    def resolve_target(self, url: str, quality: str = "best") -> dict:
        return {
            "target_url": url,
            "is_playlist": False,
            "extra_mpv_flags": [],
            "subtitle_urls": [],
            "extra_headers": {},
            "playlist_items": [],
            "current_index": 0,
            "requires_mpv": False,
            "launch_mode": "browser",
            "browser_profile": "kisscartoon",
        }

    def mpv_extra_args(self, url: str, quality: str, config: dict) -> list:
        return []
