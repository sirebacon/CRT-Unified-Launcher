"""Typed structures for the modular WCO resolver stack.

This module is scaffold-only for now: it defines the shared contract used by
HTTP resolution, Playwright fallback, playlist enrichment, and provider mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass
class WCOPlaylistItem:
    """Normalized playlist item for episode navigation."""

    title: str
    url: str


@dataclass
class WCOResolveResult:
    """Normalized resolver output before provider->mpv mapping."""

    target_url: str
    title: str = ""
    subtitle_urls: list[str] = field(default_factory=list)
    extra_headers: dict[str, str] = field(default_factory=dict)
    playlist_items: list[WCOPlaylistItem] = field(default_factory=list)
    current_index: int = 0
    has_next: bool = False
    has_prev: bool = False
    next_episode_url: str = ""
    prev_episode_url: str = ""
    next_episode_title: str = ""
    prev_episode_title: str = ""
    debug: dict[str, Any] = field(default_factory=dict)

    def to_provider_payload(self) -> dict[str, Any]:
        """Convert to the provider payload shape expected by launcher/session."""
        return {
            "target_url": self.target_url,
            "is_playlist": bool(self.playlist_items),
            "extra_mpv_flags": [],
            "subtitle_urls": self.subtitle_urls,
            "extra_headers": self.extra_headers,
            "playlist_items": [
                {"title": item.title, "url": item.url} for item in self.playlist_items
            ],
            "current_index": self.current_index,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
            "next_episode_url": self.next_episode_url,
            "prev_episode_url": self.prev_episode_url,
            "next_episode_title": self.next_episode_title,
            "prev_episode_title": self.prev_episode_title,
        }


def validate_resolve_result(result: WCOResolveResult, strict_final_url: bool = True) -> None:
    """Validate resolver output.

    Strict mode is intentionally conservative: callers should only pass a URL to
    mpv when it is confidently playable.
    """
    if not result.target_url:
        raise ValueError("WCO resolve result missing target_url")

    if strict_final_url:
        lower = result.target_url.lower()
        looks_stream = ".m3u8" in lower or ".mp4" in lower
        looks_intermediate = "getvid?" in lower
        parsed = urlparse(result.target_url)
        host = parsed.netloc.lower()
        query = parse_qs(parsed.query)
        is_wco_getvid = (
            parsed.path.lower().endswith("/getvid")
            and "evid" in query
            and ("wcostream.com" in host)
        )
        if looks_intermediate and not looks_stream and not is_wco_getvid:
            raise ValueError(
                "WCO resolve result appears to be an intermediate getvid URL in strict mode"
            )
