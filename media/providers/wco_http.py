"""HTTP-first resolver for WCO episode URLs.

This module owns the network resolution chain and emits a normalized
`WCOResolveResult` for provider-level orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import socket as _socket
import ssl as _ssl
import threading
import urllib.error as _urllib_err
import urllib.parse
import urllib.request as _urllib_req
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from media.providers.wco_types import WCOResolveResult, validate_resolve_result
from media.providers.wco_utils import EMBED_ORIGIN, normalize_to_wcostream, slug_to_title

log = logging.getLogger("media.wco.http")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.5",
}


@dataclass
class WCOHTTPConfig:
    timeout_sec: int = 30
    impersonate: str = "chrome120"
    strict_final_url: bool = True


def _select_quality_token(vidlink: dict, quality: str) -> str:
    """Select enc/hd/fhd token from getvidlink response based on requested quality."""
    fhd = vidlink.get("fhd", "")
    hd = vidlink.get("hd", "")
    enc = vidlink.get("enc", "")

    q = quality.lower() if quality else "best"
    if q in ("best", "fhd", "1080p"):
        token = fhd or hd or enc
    elif q in ("720p", "hd"):
        token = hd or enc
    else:
        token = enc or hd or fhd

    if not token:
        raise RuntimeError(f"WCO: getvidlink returned no usable token for quality={quality!r}")
    return token


def _fetch_embed_params(cffi_req, stream_url: str, cfg: WCOHTTPConfig) -> tuple[str, str, str, str]:
    """Fetch episode page and extract embed URL parameters."""
    r = cffi_req.get(
        stream_url,
        headers={**_BROWSER_HEADERS, "Referer": "https://www.wco.tv/"},
        impersonate=cfg.impersonate,
        timeout=cfg.timeout_sec,
    )
    if r.status_code != 200:
        raise RuntimeError(f"WCO: wcostream.tv returned HTTP {r.status_code} for {stream_url}")

    iframe_srcs = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', r.text, re.I)
    embed_url = next((s for s in iframe_srcs if "embed.wcostream" in s), None)
    if not embed_url:
        raise RuntimeError(f"WCO: no embed.wcostream iframe found on {stream_url}")

    ep = urllib.parse.urlparse(embed_url)
    params = dict(urllib.parse.parse_qsl(ep.query))
    file_param = params.get("file", "")
    if not file_param:
        raise RuntimeError("WCO: embed iframe missing 'file' parameter")

    file_mp4 = (
        file_param[:-4] + ".mp4" if file_param.lower().endswith(".flv") else file_param
    )
    return embed_url, file_mp4, params.get("embed", "neptun"), params.get("fullhd", "1")


def _prime_session(sess, embed_url: str, referer: str, cfg: WCOHTTPConfig) -> None:
    """Prime session cookie context by visiting embed page."""
    sess.get(
        embed_url,
        headers={**_BROWSER_HEADERS, "Referer": referer},
        impersonate=cfg.impersonate,
        timeout=cfg.timeout_sec,
    )


def _fetch_vidlink(
    sess,
    embed_url: str,
    file_mp4: str,
    embed_server: str,
    fullhd: str,
    cfg: WCOHTTPConfig,
) -> dict:
    """Call getvidlink.php and parse response JSON."""
    v_param = f"{embed_server}/{file_mp4}"
    url = (
        f"{EMBED_ORIGIN}/inc/embed/getvidlink.php"
        f"?v={urllib.parse.quote(v_param)}"
        f"&embed={embed_server}&fullhd={fullhd}"
    )

    r = sess.get(
        url,
        headers={
            **_BROWSER_HEADERS,
            "Referer": embed_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        },
        impersonate=cfg.impersonate,
        timeout=cfg.timeout_sec,
    )
    if not r.text:
        raise RuntimeError("WCO: getvidlink.php returned empty response")
    try:
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"WCO: getvidlink.php returned non-JSON: {e}") from e

    if not data.get("server"):
        raise RuntimeError(f"WCO: getvidlink.php missing 'server' field: {data}")
    return data


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _start_local_proxy(target_url: str, base_headers: dict, timeout: int) -> str:
    """Start a localhost HTTP proxy that forwards requests to target_url via Python's urllib.

    mpv's ffmpeg HTTP client consistently gets 404 from WCO CDN nodes even when
    Python (urllib, curl_cffi) succeeds with identical headers. The proxy sidesteps
    this: mpv connects to localhost plain HTTP, Python handles the actual CDN HTTPS
    request where it works reliably.

    Returns http://127.0.0.1:{port}/ for mpv to use.
    Runs as a daemon thread; dies automatically when the launcher process exits.
    """
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._serve(head_only=False)

        def do_HEAD(self):
            self._serve(head_only=True)

        def _serve(self, head_only: bool) -> None:
            hdrs = dict(self.server._base_headers)
            range_hdr = self.headers.get("Range")
            if range_hdr:
                hdrs["Range"] = range_hdr

            ctx = _ssl.create_default_context()
            req = _urllib_req.Request(
                self.server._target,
                headers=hdrs,
                method="HEAD" if head_only else "GET",
            )
            try:
                with _urllib_req.urlopen(req, context=ctx, timeout=self.server._timeout) as resp:
                    self.send_response(resp.status)
                    for k, v in resp.headers.items():
                        if k.lower() in ("content-type", "content-length", "content-range",
                                         "accept-ranges", "last-modified", "etag"):
                            self.send_header(k, v)
                    self.end_headers()
                    if not head_only:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            try:
                                self.wfile.write(chunk)
                                self.wfile.flush()
                            except (BrokenPipeError, ConnectionResetError):
                                return
            except _urllib_err.HTTPError as e:
                log.warning("WCO proxy: upstream HTTP %s for %s", e.code, self.server._target)
                self.send_error(e.code)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                log.error("WCO proxy: upstream error: %s", e)
                try:
                    self.send_error(502)
                except Exception:
                    pass

        def log_message(self, fmt, *args):  # suppress per-request console noise
            log.debug("WCO proxy: " + fmt, *args)

    s = _socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    server = _ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server._target = target_url
    server._base_headers = base_headers
    server._timeout = timeout
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("WCO proxy: port %d -> %s", port, urllib.parse.urlparse(target_url).netloc)
    return f"http://127.0.0.1:{port}/"


def _fetch_getvid_url(
    sess,
    server: str,
    enc: str,
    embed_url: str,
    cfg: WCOHTTPConfig,
) -> str:
    """Call server/getvid?evid=<enc>&json and return the CDN URL.

    The embed page JavaScript calls this endpoint (with &json suffix) to resolve
    the playable CDN URL. It returns a JSON string containing the URL of the CDN
    node getvid endpoint (e.g. https://t01.wcostream.com/getvid?evid=<tok2>).

    Python's urllib can access this URL successfully for neptun cluster nodes
    (t01, c02); for lb cluster nodes (m01/m02) the CDN may reject non-browser
    connections for certain content. The proxy will surface a 404 to mpv in that
    case, which is the correct error signal.
    """
    url = f"{server}/getvid?evid={enc}&json"
    r = sess.get(
        url,
        headers={
            **_BROWSER_HEADERS,
            "Referer": embed_url,
            "Origin": EMBED_ORIGIN,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        },
        impersonate=cfg.impersonate,
        timeout=cfg.timeout_sec,
    )
    if not r.text:
        raise RuntimeError("WCO: getvid &json returned empty response")
    try:
        cdn_url = r.json()
    except Exception as e:
        raise RuntimeError(f"WCO: getvid &json returned non-JSON: {e}") from e
    if not isinstance(cdn_url, str) or not cdn_url.startswith("http"):
        raise RuntimeError(f"WCO: getvid &json returned unexpected value: {cdn_url!r}")
    return cdn_url


def resolve_episode_http(url: str, quality: str = "best", cfg: WCOHTTPConfig | None = None) -> WCOResolveResult:
    """Resolve WCO episode URL into a playable target URL and request headers."""
    cfg = cfg or WCOHTTPConfig()
    import curl_cffi.requests as cffi_req

    stream_url = normalize_to_wcostream(url)
    log.debug("WCO HTTP: resolving %s (quality=%s)", stream_url, quality)

    embed_url, file_mp4, embed_server, fullhd = _fetch_embed_params(cffi_req, stream_url, cfg)
    sess = cffi_req.Session()
    _prime_session(sess, embed_url, stream_url, cfg)
    vidlink = _fetch_vidlink(sess, embed_url, file_mp4, embed_server, fullhd, cfg)

    enc = _select_quality_token(vidlink, quality)

    # The embed page JavaScript calls server/getvid?evid=<enc>&json to resolve the
    # CDN URL. This matches the browser's resolution path exactly and works for all
    # cluster types (neptun t01/c02, lb m01/m02, ndisk nd0X).
    # For lb cluster content, the CDN node may still reject non-browser connections
    # at the proxy stage; the proxy will surface a 404 to mpv in that case.
    cookie_header = ""
    cdn_headers = {
        "User-Agent": _BROWSER_HEADERS["User-Agent"],
        "Referer": EMBED_ORIGIN + "/",
        "Accept": "*/*",
    }
    try:
        cdn_url = _fetch_getvid_url(sess, vidlink["server"], enc, embed_url, cfg)
        log.debug("WCO: getvid &json -> CDN %s", urllib.parse.urlparse(cdn_url).netloc)
    except Exception as e:
        log.warning("WCO: getvid &json failed (%s); falling back to raw getvid URL", e)
        cdn_url = f"{vidlink['server']}/getvid?evid={enc}"
        try:
            cookie_dict = sess.cookies.get_dict() if hasattr(sess.cookies, "get_dict") else {}
            if cookie_dict:
                cookie_header = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        except Exception:
            cookie_header = ""
        cdn_headers = {
            "Referer": embed_url,
            "Origin": EMBED_ORIGIN,
            "User-Agent": _BROWSER_HEADERS["User-Agent"],
            "Accept": "*/*",
        }
        if cookie_header:
            cdn_headers["Cookie"] = cookie_header

    # mpv's ffmpeg HTTP client consistently gets 404 from WCO CDN even when Python
    # (urllib, curl_cffi, direct IP, any headers) succeeds with the same URL.
    # Route through a local Python proxy so Python owns the CDN request; mpv connects
    # to localhost plain HTTP where it has no issues.
    target_url = _start_local_proxy(cdn_url, cdn_headers, cfg.timeout_sec)

    result = WCOResolveResult(
        target_url=target_url,
        title=slug_to_title(urllib.parse.urlparse(stream_url).path),
        subtitle_urls=[],
        extra_headers={},  # mpv connects to localhost plain HTTP; no CDN headers needed
        debug={
            "host": urllib.parse.urlparse(cdn_url).netloc,
            "quality": quality,
            "token_len": len(enc),
            "cookie_count": len(cookie_header.split("; ")) if cookie_header else 0,
        },
    )
    validate_resolve_result(result, strict_final_url=False)  # 127.0.0.1 is not a WCO CDN URL
    return result
