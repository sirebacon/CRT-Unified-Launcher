"""Provider registry — maps URLs to the correct provider.

Usage:
    from media.providers import registry

    registry.setup(cfg)                        # call once at startup
    provider = registry.get_provider_or_generic(url)
    err = provider.validate(url)
"""

import logging
from typing import Optional

from media.providers.base import Provider

log = logging.getLogger("media.registry")

_providers: list[Provider] = []


def setup(config: dict) -> None:
    """Initialise and register all providers with config. Call once at startup."""
    global _providers
    _providers = []

    yt_dlp_path = config.get("yt_dlp_path", "yt-dlp")
    node_path = config.get("node_path", "node")
    cookies_from_browser = config.get("youtube_cookies_from_browser", "")
    cookies_file = config.get("youtube_cookies_file", "")

    # Tier 1 — yt-dlp-backed
    from media.providers.youtube import YouTubeProvider
    register(YouTubeProvider(
        yt_dlp_path=yt_dlp_path,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
    ))

    # Tier 2 — curl_cffi-backed resolver for wco.tv / wcostream.tv
    try:
        from media.providers.wco import WCOProvider
        register(WCOProvider())
        log.debug("WCOProvider registered")
    except Exception as e:
        log.warning("WCOProvider could not be registered: %s", e)

    # Tier 2 — resolver-backed
    try:
        from media.providers.aniwatch import AniwatchProvider
        register(AniwatchProvider(node_path=node_path))
        log.debug("AniwatchProvider registered")
    except Exception as e:
        log.warning("AniwatchProvider could not be registered: %s", e)

    # Tier 3 — browser-backed
    try:
        from media.providers.kisscartoon import KissCartoonProvider
        register(KissCartoonProvider())
        log.debug("KissCartoonProvider registered")
    except Exception as e:
        log.warning("KissCartoonProvider could not be registered: %s", e)

    # Fallback — registered last, matches anything
    from media.providers.generic import GenericProvider
    register(GenericProvider())

    log.debug("Registry ready: %s", [p.name() for p in _providers])


def register(provider: Provider) -> None:
    """Register a provider. Providers registered earlier take priority."""
    _providers.append(provider)


def get_provider(url: str) -> Optional[Provider]:
    """Return the first registered provider that can handle this URL, or None."""
    for p in _providers:
        if p.can_handle(url):
            return p
    return None


def get_provider_or_generic(url: str) -> Provider:
    """Return the matching provider, falling back to GenericProvider."""
    from media.providers.generic import GenericProvider
    return get_provider(url) or GenericProvider()


def all_providers() -> list[Provider]:
    return list(_providers)
