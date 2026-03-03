# WCO CDN 404 — Why mpv Fails and Why the Proxy Fixes It

## The Problem

When playing WCO.tv episodes, mpv consistently receives `HTTP 404 Not Found` from
WCO CDN nodes (e.g. `t01.wcostream.com`) even for URLs that are confirmed to work.

This is surprising because:
- The same URL, fetched from Python (urllib, curl_cffi, direct IP), returns `200/206 video/mp4`
- The same URL works regardless of which headers Python sends
- The same URL works at any timing — tokens do not expire quickly
- The same URL works even when fetching from the raw IP, bypassing DNS

In other words: **the URL is valid and the content exists. Only mpv fails.**

## Investigation Summary

The following were tested and ruled out as causes:

| Hypothesis | Test | Result |
|---|---|---|
| TLS fingerprint mismatch | curl_cffi Chrome120 impersonation vs plain urllib | Both return 206 — TLS not the issue |
| Token expires before mpv uses it | urllib fetch with 0s, 3s, 8s delays | All 206 — token doesn't expire quickly |
| DNS round-robin returns different IPs | Resolved IP vs direct IP fetch | t01 has one IP; both paths return 206 |
| Range header required | Fetch with no Range, `Range: 0-99`, `Range: 0-` | All variants return 200/206 |
| Specific headers required | Exact mpv headers, any UA, no UA | Any UA works; no UA → 500 |

After ruling out all of the above, the only remaining explanation is that **mpv's internal
ffmpeg HTTP client sends something the WCO CDN rejects**. The exact trigger was not
identified — it may be a specific HTTP/1.1 vs HTTP/2 behavior, a header mpv always
includes, or a quirk of ffmpeg's HTTP implementation. Whatever it is, it is invisible
to us from outside mpv.

## Root Cause (Working Theory)

WCO CDN nodes appear to have server-side filtering that rejects requests from
mpv/ffmpeg's HTTP stack. This is consistent with CDN anti-hotlink or bot-detection
behavior that fingerprints the HTTP client at the TCP/HTTP layer, beyond what headers
alone can control.

Python's HTTP stack (urllib) does not trigger this filtering, even with headers that
exactly match what mpv would send.

## The Fix: Local Python HTTP Proxy

Since Python works and mpv doesn't, the fix is to put Python between mpv and the CDN:

```
mpv → http://127.0.0.1:{port}/ (plain HTTP, no special headers)
  → _start_local_proxy (Python ThreadingHTTPServer, daemon thread)
    → https://t01.wcostream.com/...mp4 (Python urllib with correct headers)
      ← 200/206 video/mp4 streamed back in 64KB chunks
  ← response forwarded to mpv
```

### How It Works

`_start_local_proxy` in `media/providers/wco_http.py`:

1. Binds a `ThreadingHTTPServer` to a random available localhost port
2. Stores the real CDN URL and headers on the server object
3. Starts a daemon thread (`serve_forever`) — dies automatically when the launcher exits
4. Returns `http://127.0.0.1:{port}/` as the URL mpv opens

The proxy handler:
- Forwards `Range` headers from mpv so **seeking works correctly**
- Forwards only safe response headers to mpv (`Content-Type`, `Content-Length`,
  `Content-Range`, `Accept-Ranges`, `Last-Modified`, `ETag`)
- Handles `BrokenPipeError` / `ConnectionResetError` cleanly (mpv closes the connection
  when it seeks or stops)
- Returns the upstream HTTP error code to mpv if the CDN request fails
- Logs at DEBUG level to avoid console noise

### Why the Proxy URL Passes Validation

`validate_resolve_result` has a `strict_final_url` check that normally rejects
non-CDN URLs. The proxy bypasses this by passing `strict_final_url=False` —
`127.0.0.1` is obviously not a WCO stream URL, but it is the correct target for mpv
in this architecture.

## WCO CDN Cluster Notes

Not all WCO content is available. Three CDN clusters exist:

| Embed server | CDN cluster | Status |
|---|---|---|
| `neptun` | `t0X.wcostream.com`, `c0X.wcostream.com` | **Works** — used by recent anime (Naruto, One Piece, Bleach) |
| `anime` | `m0X.wcostream.com` | **404** — content not hosted; old Western cartoons |
| `ndisk` | `nd0X.wcostream.com` | **404** — content not hosted; some older anime |

If an episode returns 404 even through the proxy, the content is genuinely not on the
CDN. This is not fixable in the resolver. The embed page JS itself falls back to
`/error.mp4` for these episodes.

**Works:** `wco.tv/naruto-episode-1`, `wco.tv/one-piece-episode-1`, `wco.tv/bleach-episode-1`

**Does not work (content unavailable):** `wco.tv/2-stupid-dogs-*`, `wco.tv/dragon-ball-super-*`

## Relevant Code

| Location | Purpose |
|---|---|
| `media/providers/wco_http.py` — `_start_local_proxy` | Proxy server implementation |
| `media/providers/wco_http.py` — `_ThreadingHTTPServer` | Thread-safe HTTPServer base class |
| `media/providers/wco_http.py` — `resolve_episode_http` | Calls proxy after CDN URL is resolved |
| `media/providers/wco_http.py` — `_follow_getvid_redirect` | Follows first-hop getvid → CDN URL |
