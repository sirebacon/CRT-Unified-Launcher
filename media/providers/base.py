"""Provider interface and capability flags."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderCapabilities:
    uses_ytdl: bool = True
    supports_playlist: bool = False
    supports_title_fetch: bool = False
    supports_resume: bool = False
    requires_cookies: bool = False


class Provider(ABC):
    """Base class for all media providers.

    Tier 1 (yt-dlp-backed): uses_ytdl=True. mpv receives the original URL and
    resolves it via the yt-dlp hook at playback time.

    Tier 2 (resolver-backed): uses_ytdl=False. resolve_target() calls an external
    subprocess to obtain a raw HLS/MP4 URL before mpv launches. mpv receives the
    pre-resolved URL with --no-ytdl.
    """

    capabilities: ProviderCapabilities = ProviderCapabilities()

    @property
    def uses_ytdl(self) -> bool:
        return self.capabilities.uses_ytdl

    @property
    def supports_playlist(self) -> bool:
        return self.capabilities.supports_playlist

    @property
    def supports_title_fetch(self) -> bool:
        return self.capabilities.supports_title_fetch

    @property
    def supports_resume(self) -> bool:
        return self.capabilities.supports_resume

    @property
    def requires_cookies(self) -> bool:
        return self.capabilities.requires_cookies

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this provider can handle the given URL."""

    def validate(self, url: str) -> Optional[str]:
        """Return None if the URL is valid for this provider, else an error string."""
        return None

    def resolve_target(self, url: str) -> dict:
        """Resolve the URL to playback info.

        Returns a dict with:
            target_url (str)       — the URL passed to mpv
            is_playlist (bool)
            extra_mpv_flags (list) — e.g. ["--ytdl-raw-options=yes-playlist="]
            subtitle_urls (list)   — Tier 2: passed as --sub-file=<url>
            extra_headers (dict)   — Tier 2: passed as --http-header-fields=
            playlist_items (list)  — optional episode list for next/prev nav
            current_index (int)    — optional index into playlist_items
        """
        return {
            "target_url": url,
            "is_playlist": False,
            "extra_mpv_flags": [],
            "subtitle_urls": [],
            "extra_headers": {},
            "playlist_items": [],
            "current_index": 0,
        }

    def fetch_title(self, url: str) -> str:
        """Fetch a human-readable title for the URL. Returns empty string on failure."""
        return ""

    def is_playlist(self, url: str) -> bool:
        """Return True if the URL refers to a playlist or episode series."""
        return False

    def mpv_extra_args(self, url: str, quality: str, config: dict) -> list:
        """Return extra CLI args to append to the mpv command for this provider."""
        return []
