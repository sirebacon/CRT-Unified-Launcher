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
    → https://t01.wcostream.com/getvid?evid=<tok2> (Python urllib with correct headers)
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

## CDN URL Resolution — The &json Endpoint

The embed page JavaScript resolves the CDN URL using a `&json` suffix on the getvid
endpoint:

```javascript
const videoUrl = server + '/getvid?evid=' + vsd + '&json';
fetchJsonData(videoUrl).then(data => {
    vp.src({ src: data, type: 'video/mp4' });
});
```

`_fetch_getvid_url` in `wco_http.py` replicates this exactly: it calls
`server/getvid?evid=<enc>&json` with the same XHR headers the embed page uses, then
parses the JSON string response (e.g. `"https://t01.wcostream.com/getvid?evid=<tok2>"`)
and uses that URL as the proxy target.

This replaces the earlier redirect-following approach (`_follow_getvid_redirect`) and
the lb-bypass probe (`_find_lb_cdn_url`), which were both more complex and less faithful
to the browser's actual behaviour.

## WCO CDN Cluster Notes

Three CDN clusters exist. Resolution via `&json` endpoint works the same way for all:

| Embed server | Load balancer | CDN nodes | Python access | Notes |
|---|---|---|---|---|
| `neptun` | `neptun.wcostream.com` | `t0X`, `c0X` | **works** | Most anime/manga series |
| `anime` | `lb.wcostream.com` | `m01`, `m02` | **fails (404)** | Western cartoons, some older content |
| `ndisk` | `ndisk.wcostream.com` | `nd0X` | unknown | Rarely seen in practice |

**Works:** `wco.tv/naruto-episode-1` (t01), `wco.tv/one-piece-episode-1` (c02),
`wco.tv/bleach-episode-1` (c02)

**Fails:** `wco.tv/2-stupid-dogs-episode-1-door-jam` — uses `lb.wcostream.com` (m01/m02);
m01/m02 CDN nodes return 404 to all Python HTTP clients (urllib, curl_cffi with any
TLS impersonation). The browser plays it successfully. The exact server-side rejection
mechanism is unknown — it is NOT a simple header or TLS fingerprint issue since every
tested client and fingerprint combination returns the same 404. The proxy correctly
surfaces this as a 404 error to mpv.

## The lb Cluster Investigation (2026-03-03)

For `lb.wcostream.com` (Western cartoons), extensive investigation found:

- `lb/getvid?evid=<enc>` → 302 redirect to `m01/getvid?evid=<tok2>` (different token)
- `lb/getvid?evid=<enc>&json` → JSON: `"https://m01.wcostream.com/getvid?evid=<tok2>"`
- Both `m01/getvid?evid=<enc>` and `m01/getvid?evid=<tok2>` → 404 from Python
- Tested: urllib, curl_cffi Chrome120/124/131/Firefox133/Safari18/17 — all 404
- No auth cookies set by lb in redirect response
- m01/m02 are the only nodes (m03+ do not exist)
- Browser (Chrome) plays successfully — mechanism unknown

Conclusion: the lb cluster CDN nodes (m01/m02) require something the browser provides
that no Python HTTP client can replicate. This is a hard limitation. The launcher
returns a proxy 404 for lb cluster content; the user would need to watch that content
in a browser directly.

## Relevant Code

| Location | Purpose |
|---|---|
| `media/providers/wco_http.py` — `_start_local_proxy` | Proxy server implementation |
| `media/providers/wco_http.py` — `_ThreadingHTTPServer` | Thread-safe HTTPServer base class |
| `media/providers/wco_http.py` — `_fetch_getvid_url` | Calls `&json` endpoint to get CDN URL |
| `media/providers/wco_http.py` — `resolve_episode_http` | Orchestrates full resolution chain |
