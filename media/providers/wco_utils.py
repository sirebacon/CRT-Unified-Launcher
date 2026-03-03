"""Utility helpers for WCO provider modules."""

from __future__ import annotations

import urllib.parse

VALID_HOSTS = {
    "wco.tv",
    "www.wco.tv",
    "wcoanimedub.tv",
    "www.wcoanimedub.tv",
    "wcoanimesub.tv",
    "www.wcoanimesub.tv",
    "wcostream.tv",
    "www.wcostream.tv",
}

EMBED_ORIGIN = "https://embed.wcostream.com"


def can_handle_host(host: str) -> bool:
    return host in VALID_HOSTS


def slug_to_title(slug: str) -> str:
    """Convert a URL slug to a readable title."""
    slug = slug.strip("/").split("?")[0]
    slug = slug.rsplit("/", 1)[-1]
    return " ".join(word.capitalize() for word in slug.replace("-", " ").split())


def normalize_to_wcostream(url: str) -> str:
    """Normalize supported WCO domains to www.wcostream.tv, preserving path/query."""
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed._replace(netloc="www.wcostream.tv"))

