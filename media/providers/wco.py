"""WCOProvider - Tier 2 resolver-backed provider for WCO/WCOStream URLs."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from media.providers.base import Provider, ProviderCapabilities
from media.providers.wco_http import WCOHTTPConfig, resolve_episode_http
from media.providers.wco_playlist import build_playlist_for_episode
from media.providers.wco_types import WCOResolveResult
from media.providers.wco_utils import EMBED_ORIGIN, can_handle_host, normalize_to_wcostream, slug_to_title

log = logging.getLogger("media.wco")


class WCOProvider(Provider):
    capabilities = ProviderCapabilities(
        uses_ytdl=False,
        supports_playlist=True,
        supports_title_fetch=True,
        supports_resume=True,
        requires_cookies=False,
    )

    def __init__(self):
        # Cache keyed by (url, quality) so fetch_title + resolve_target can share.
        self._cache: dict[tuple[str, str], WCOResolveResult] = {}

    def name(self) -> str:
        return "WCO"

    def can_handle(self, url: str) -> bool:
        try:
            return can_handle_host(urlparse(url).netloc)
        except Exception:
            return False

    def validate(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return "URL must start with http:// or https://"
            if not can_handle_host(parsed.netloc):
                return f"Not a WCO URL (host: {parsed.netloc!r})"
            try:
                import curl_cffi  # noqa: F401
            except ImportError:
                return (
                    "curl_cffi is not installed - run: pip install curl_cffi\n"
                    "WCO.tv requires curl_cffi for Cloudflare bypass."
                )
            return None
        except Exception as e:
            return f"Invalid URL: {e}"

    def fetch_title(self, url: str) -> str:
        try:
            data = self._resolve(url, "best")
            return data.title or slug_to_title(urlparse(url).path)
        except Exception:
            try:
                return slug_to_title(urlparse(url).path)
            except Exception:
                return ""

    def is_playlist(self, url: str) -> bool:
        return False

    def resolve_target(self, url: str, quality: str = "best") -> dict:
        result = self._resolve(url, quality)
        payload = result.to_provider_payload()
        # Ensure referer survives even if a future resolver misses it.
        payload.setdefault("extra_headers", {})
        payload["extra_headers"].setdefault("Referer", f"{EMBED_ORIGIN}/")
        return payload

    def mpv_extra_args(self, url: str, quality: str, config: dict) -> list:
        return ["--no-ytdl"]

    def _resolve(self, url: str, quality: str) -> WCOResolveResult:
        key = (url, quality)
        cached = self._cache.get(key)
        if cached:
            log.debug("WCO cache hit: %s quality=%s", url, quality)
            return cached

        normalized = normalize_to_wcostream(url)
        cfg = WCOHTTPConfig(timeout_sec=30, impersonate="chrome120", strict_final_url=True)
        result = resolve_episode_http(normalized, quality, cfg)

        try:
            nav = build_playlist_for_episode(normalized, timeout_sec=cfg.timeout_sec, impersonate=cfg.impersonate)
        except Exception as e:
            log.warning("WCO playlist extraction failed: %s", e)
            nav = {
                "playlist_items": [],
                "current_index": 0,
                "has_next": False,
                "has_prev": False,
                "next_episode_url": "",
                "prev_episode_url": "",
                "next_episode_title": "",
                "prev_episode_title": "",
            }

        result.playlist_items = nav["playlist_items"]
        result.current_index = nav["current_index"]
        result.has_next = nav["has_next"]
        result.has_prev = nav["has_prev"]
        result.next_episode_url = nav["next_episode_url"]
        result.prev_episode_url = nav["prev_episode_url"]
        result.next_episode_title = nav["next_episode_title"]
        result.prev_episode_title = nav["prev_episode_title"]

        self._cache[key] = result
        return result

