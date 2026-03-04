"""AniwatchProvider — Tier 2 resolver-backed provider for hianime.to URLs.

Resolves episode URLs by calling integrations/aniwatch-js/resolve.js as a subprocess.
The Node script returns a JSON payload with the pre-resolved HLS URL and subtitle tracks.
mpv receives the raw URL with --no-ytdl.
"""

import json
import logging
import os
import re
import subprocess
from typing import Optional
from urllib.parse import urlparse, parse_qs

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

from media.providers.base import Provider, ProviderCapabilities

log = logging.getLogger("media.aniwatch")

_VALID_HOSTS = {"hianime.to", "www.hianime.to"}
_DEFAULT_TIMEOUT = 15

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_RESOLVER = os.path.join(
    _PROJECT_ROOT, "integrations", "aniwatch-js", "resolve.js"
)


class AniwatchProvider(Provider):
    capabilities = ProviderCapabilities(
        uses_ytdl=False,
        supports_playlist=True,
        supports_title_fetch=True,
        supports_resume=True,
        requires_cookies=False,
    )

    def __init__(
        self,
        node_path: str = "node",
        resolver_path: str = _DEFAULT_RESOLVER,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        self._node_path = node_path
        self._resolver_path = resolver_path
        self._timeout = timeout
        self._cache: dict = {}  # url -> resolver result; avoids double-fetching per session

    def name(self) -> str:
        return "HiAnime"

    def can_handle(self, url: str) -> bool:
        try:
            return urlparse(url).netloc in _VALID_HOSTS
        except Exception:
            return False

    def validate(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return "URL must start with http:// or https://"
            if parsed.netloc not in _VALID_HOSTS:
                return f"Not a HiAnime URL (host: {parsed.netloc!r})"
            if "/watch/" not in parsed.path:
                return "URL must be a /watch/ episode URL (e.g. hianime.to/watch/slug?ep=id)"
            if not parsed.query or "ep=" not in parsed.query:
                return "URL must include an episode ID (?ep=...)"
            if not self._node_available():
                return (
                    "Node.js not found — install Node.js and ensure it is on PATH "
                    "before using HiAnime provider"
                )
            if not os.path.exists(self._resolver_path):
                return f"HiAnime resolver script not found: {self._resolver_path}"
            return None
        except Exception as e:
            return f"Invalid URL: {e}"

    def resolve_target(self, url: str, quality: str = "best") -> dict:
        data = self._run_resolver(url)
        return {
            "target_url": data["target_url"],
            "is_playlist": data.get("is_playlist", False),
            "extra_mpv_flags": [],
            "subtitle_urls": data.get("subtitle_urls", []),
            "extra_headers": data.get("extra_headers", {}),
            "playlist_items": data.get("playlist_items", []),
            "current_index": data.get("current_index", 0),
            "has_next": data.get("has_next", False),
            "next_episode_url": data.get("next_episode_url"),
            "next_episode_title": data.get("next_episode_title", ""),
            "has_prev": data.get("has_prev", False),
            "prev_episode_url": data.get("prev_episode_url"),
            "prev_episode_title": data.get("prev_episode_title", ""),
        }

    def fetch_title(self, url: str) -> str:
        try:
            data = self._run_resolver(url)
            return data.get("episode_title", "")
        except Exception as e:
            log.warning("fetch_title failed: %s", e)
            return ""

    def is_playlist(self, url: str) -> bool:
        return False  # each hianime.to URL is a single episode

    def get_continue_metadata(self, url: str) -> dict:
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) < 2 or path_parts[0] != "watch":
                return {}
            series_slug = path_parts[1]   # e.g. "super-demon-hero-wataru-4045"
            qs = parse_qs(parsed.query) if hasattr(parsed, "query") else {}
            episode_id = (qs.get("ep", [""]))[0]
            # episode_index from resolver cache if available
            episode_index = None
            if url in self._cache:
                episode_index = self._cache[url].get("current_index")
            return {
                "continue_key":  f"hianime:series:{series_slug}",
                "entity_type":   "series",
                "series_title":  "",
                "episode_title": "",
                "episode_index": episode_index,
                "episode_url":   url,
                "episode_id":    episode_id,
            }
        except Exception:
            return {}

    def mpv_extra_args(self, url: str, quality: str, config: dict) -> list:
        return ["--no-ytdl"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _node_available(self) -> bool:
        try:
            subprocess.run(
                [self._node_path, "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception:
            return False

    def _run_resolver(self, url: str) -> dict:
        if url in self._cache:
            log.debug("resolver cache hit: %s", url)
            return self._cache[url]

        if not os.path.exists(self._resolver_path):
            raise RuntimeError(f"Resolver script not found: {self._resolver_path}")

        log.debug("running resolver: %s %s", self._resolver_path, url)

        try:
            result = subprocess.run(
                [self._node_path, self._resolver_path, url],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"HiAnime resolver timed out after {self._timeout}s for URL: {url}"
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Node.js not found at '{self._node_path}' — install Node.js and "
                "ensure it is on PATH"
            )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"HiAnime resolver failed: {stderr}")

        # The aniwatch package writes INFO log lines (with ANSI colour codes) to stdout
        # alongside our JSON result. Strip colour codes and scan for the JSON line.
        json_line = None
        for line in result.stdout.splitlines():
            line = _ANSI_ESCAPE.sub("", line).strip()
            if line.startswith("{"):
                json_line = line
                break

        if not json_line:
            raise RuntimeError("HiAnime resolver returned no JSON output")

        try:
            data = json.loads(json_line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"HiAnime resolver returned invalid JSON: {e}")

        self._cache[url] = data
        return data
