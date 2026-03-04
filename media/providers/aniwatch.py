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
import sys
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
        prompt_stream_choice: bool = False,
        default_stream_type: str = "sub",
        default_server: str = "",
    ):
        self._node_path = node_path
        self._resolver_path = resolver_path
        self._timeout = timeout
        self._prompt_stream_choice = bool(prompt_stream_choice)
        self._default_stream_type = (default_stream_type or "sub").lower()
        self._default_server = (default_server or "").strip().lower()
        # Sticky stream selection for the current launcher session.
        self._session_stream_type = ""
        self._session_server = ""
        # Cache keyed by (url, stream_type, server)
        self._cache: dict = {}

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
        data = self._resolve_with_optional_choice(url)
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
            # Do not require full source resolution just to get title.
            data = self._run_resolver_with_options(url, list_only=True)
            return data.get("episode_title", "") or ""
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
            for key, payload in self._cache.items():
                if not isinstance(key, tuple) or len(key) < 1:
                    continue
                if key[0] == url and isinstance(payload, dict):
                    idx = payload.get("current_index")
                    if idx is not None:
                        episode_index = idx
                        break
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
        return self._run_resolver_with_options(url, stream_type="", server_name="", list_only=False)

    def _resolve_with_optional_choice(self, url: str) -> dict:
        """Resolve URL, optionally prompting user to choose sub/dub + server."""
        stream_type = self._session_stream_type or (
            self._default_stream_type if self._default_stream_type in {"sub", "dub"} else "sub"
        )
        server_name = self._session_server or self._default_server

        # Prompt only before first explicit choice in this launcher session.
        if self._prompt_stream_choice and sys.stdin.isatty() and not self._session_stream_type:
            try:
                choices = self._run_resolver_with_options(url, list_only=True)
                stream_type, server_name = self._prompt_stream_selection(choices)
                self._session_stream_type = stream_type
                self._session_server = server_name
            except Exception as e:
                log.warning("stream choice listing failed; using defaults: %s", e)
        else:
            # Keep session choice sticky across next/prev/autoplay episode transitions.
            if stream_type in {"sub", "dub"}:
                self._session_stream_type = stream_type
            if server_name:
                self._session_server = server_name

        return self._run_resolver_with_options(
            url,
            stream_type=stream_type,
            server_name=server_name,
            list_only=False,
        )

    def _prompt_stream_selection(self, choices: dict) -> tuple[str, str]:
        available = choices.get("available", {}) if isinstance(choices, dict) else {}
        sub_servers = list(available.get("sub", []) or [])
        dub_servers = list(available.get("dub", []) or [])
        default_type = choices.get("default_type", "sub")
        default_server = choices.get("default_server", "")

        # If only one practical choice, don't prompt.
        total_variants = (1 if sub_servers else 0) + (1 if dub_servers else 0)
        if total_variants <= 1:
            st = "sub" if sub_servers else "dub"
            ss = (sub_servers[0] if sub_servers else (dub_servers[0] if dub_servers else ""))
            return st, ss

        print("\n[hianime] Stream choices:")
        idx = 1
        options: list[tuple[str, str]] = []
        for stype, servers in (("sub", sub_servers), ("dub", dub_servers)):
            for s in servers:
                marker = " (default)" if stype == default_type and s == default_server else ""
                print(f"  {idx}) {stype.upper()} / {s}{marker}")
                options.append((stype, s))
                idx += 1
        print("Pick stream (Enter for default): ", end="", flush=True)
        try:
            pick = input().strip()
        except (EOFError, KeyboardInterrupt):
            pick = ""

        if pick.isdigit():
            i = int(pick) - 1
            if 0 <= i < len(options):
                return options[i]

        if default_type in {"sub", "dub"} and default_server:
            return default_type, default_server
        return options[0] if options else ("sub", "")

    def _run_resolver_with_options(
        self,
        url: str,
        stream_type: str = "",
        server_name: str = "",
        list_only: bool = False,
    ) -> dict:
        cache_key = (url, stream_type or "", server_name or "", bool(list_only))
        if cache_key in self._cache:
            log.debug("resolver cache hit: %s", cache_key)
            return self._cache[cache_key]

        if not os.path.exists(self._resolver_path):
            raise RuntimeError(f"Resolver script not found: {self._resolver_path}")

        log.debug(
            "running resolver: %s url=%s list=%s type=%s server=%s",
            self._resolver_path, url, list_only, stream_type, server_name
        )

        cmd = [self._node_path, self._resolver_path]
        if list_only:
            cmd.append("--list")
        if stream_type:
            cmd.extend(["--type", stream_type])
        if server_name:
            cmd.extend(["--server", server_name])
        cmd.append(url)

        try:
            result = subprocess.run(
                cmd,
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

        self._cache[cache_key] = data
        return data
