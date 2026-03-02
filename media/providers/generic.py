"""GenericProvider — fallback for direct media URLs and local files.

Accepts any URL or file path that mpv can open natively. Does not use yt-dlp.
No title fetch, no playlist support, no resume.
"""

from media.providers.base import Provider, ProviderCapabilities


class GenericProvider(Provider):
    capabilities = ProviderCapabilities(
        uses_ytdl=False,
        supports_playlist=False,
        supports_title_fetch=False,
        supports_resume=False,
        requires_cookies=False,
    )

    def name(self) -> str:
        return "Generic"

    def can_handle(self, url: str) -> bool:
        return True  # fallback — accepts anything

    def mpv_extra_args(self, url: str, quality: str, config: dict) -> list:
        return ["--no-ytdl"]
