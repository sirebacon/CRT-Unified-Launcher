"""Playlist extraction helpers for WCO episode navigation."""

from __future__ import annotations

import html
import re
import urllib.parse

from media.providers.wco_types import WCOPlaylistItem
from media.providers.wco_utils import VALID_HOSTS, normalize_to_wcostream


def _normalized_episode_key(url: str) -> str:
    parsed = urllib.parse.urlparse(normalize_to_wcostream(url))
    return parsed.path.rstrip("/").lower()


def _extract_show_prefix(path: str) -> str:
    slug = path.strip("/").rsplit("/", 1)[-1].lower()
    return slug.split("-episode-")[0]


def _derive_series_url(current_url: str) -> str:
    """Best-effort derivation; caller should fallback if no episodes parse."""
    parsed = urllib.parse.urlparse(current_url)
    show_prefix = _extract_show_prefix(parsed.path)
    return f"https://www.wco.tv/anime/{show_prefix}/?season=all"


def _extract_episode_links(html_text: str, base_url: str, show_prefix: str) -> list[WCOPlaylistItem]:
    links = re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html_text,
        re.I | re.S,
    )
    out: list[WCOPlaylistItem] = []
    seen: set[str] = set()

    for href, label in links:
        abs_url = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(abs_url)
        if parsed.netloc and parsed.netloc not in VALID_HOSTS:
            continue
        path = parsed.path.lower()
        if "-episode-" not in path:
            continue
        if "/anime/" in path:
            continue
        slug = path.strip("/").rsplit("/", 1)[-1]
        if show_prefix and not slug.startswith(show_prefix):
            continue

        norm = normalize_to_wcostream(abs_url)
        if norm in seen:
            continue
        seen.add(norm)

        # Strip tags from anchor text and normalize whitespace.
        title = re.sub(r"<[^>]+>", "", label)
        title = " ".join(html.unescape(title).split())
        if not title:
            title = slug.replace("-", " ")

        out.append(WCOPlaylistItem(title=title, url=norm))
    return out


def _episode_number(path: str) -> int:
    m = re.search(r"-episode-(\d+)", path.lower())
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def build_playlist_for_episode(
    current_url: str,
    timeout_sec: int = 30,
    impersonate: str = "chrome120",
) -> dict:
    """Return playlist and nav metadata for current episode URL.

    Returns keys:
    - playlist_items: list[WCOPlaylistItem]
    - current_index: int
    - has_next / has_prev: bool
    - next_episode_url / prev_episode_url: str
    - next_episode_title / prev_episode_title: str
    """
    import curl_cffi.requests as cffi_req

    current_norm = normalize_to_wcostream(current_url)
    current_key = _normalized_episode_key(current_norm)
    show_prefix = _extract_show_prefix(urllib.parse.urlparse(current_norm).path)
    series_url = _derive_series_url(current_norm)

    browser_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.wco.tv/",
    }

    # First probe series page; fallback to current page if parsing yields nothing.
    pages_to_try = [series_url, current_norm]
    playlist_items: list[WCOPlaylistItem] = []

    for page in pages_to_try:
        r = cffi_req.get(
            page,
            headers=browser_headers,
            impersonate=impersonate,
            timeout=timeout_sec,
        )
        if r.status_code != 200 or not r.text:
            continue
        parsed_items = _extract_episode_links(r.text, page, show_prefix)
        if parsed_items:
            playlist_items = parsed_items
            break

    if not playlist_items:
        return {
            "playlist_items": [],
            "current_index": 0,
            "has_next": False,
            "has_prev": False,
            "next_episode_url": "",
            "prev_episode_url": "",
            "next_episode_title": "",
            "prev_episode_title": "",
        }

    # Prefer existing page order; if current isn't found, try episode-number ordering.
    current_index = next(
        (i for i, item in enumerate(playlist_items) if _normalized_episode_key(item.url) == current_key),
        -1,
    )

    if current_index < 0:
        playlist_items.sort(key=lambda item: _episode_number(urllib.parse.urlparse(item.url).path))
        current_index = next(
            (i for i, item in enumerate(playlist_items) if _normalized_episode_key(item.url) == current_key),
            0,
        )

    has_prev = current_index > 0
    has_next = current_index < len(playlist_items) - 1

    prev_item = playlist_items[current_index - 1] if has_prev else None
    next_item = playlist_items[current_index + 1] if has_next else None

    return {
        "playlist_items": playlist_items,
        "current_index": current_index,
        "has_next": has_next,
        "has_prev": has_prev,
        "next_episode_url": next_item.url if next_item else "",
        "prev_episode_url": prev_item.url if prev_item else "",
        "next_episode_title": next_item.title if next_item else "",
        "prev_episode_title": prev_item.title if prev_item else "",
    }
