/**
 * HiAnime episode resolver.
 *
 * Usage:
 *   node resolve.js <hianime-url>
 *
 * URL format:
 *   https://hianime.to/watch/{show-slug}?ep={episode-id}
 *
 * Output (stdout): JSON with keys:
 *   target_url         (string)  — resolved HLS or MP4 URL for mpv
 *   is_playlist        (bool)    — always false (single episode)
 *   subtitle_urls      (array)   — VTT subtitle URLs
 *   extra_headers      (object)  — HTTP headers mpv needs (e.g. Referer)
 *   episode_title      (string)  — episode title if available
 *   server_used        (string)  — CDN server name selected
 *   has_next           (bool)    — true when a next episode exists in the series
 *   next_episode_url   (string|null) — full hianime.to URL for the next episode
 *   next_episode_title (string)  — title of the next episode (empty if unknown)
 *   playlist_items     (array)   — [{url, title, number}] from next episode onward
 *
 * Exits non-zero on any error and writes the reason to stderr.
 */

"use strict";

const { HiAnime } = require("aniwatch");

// Server preference order: pick the first available from this list.
const SERVER_PREFERENCE = ["hd-1", "hd-2", "hd-3"];

async function resolve(url) {
    const scraper = new HiAnime.Scraper();

    // --- Parse URL ---
    let urlObj;
    try {
        urlObj = new URL(url);
    } catch (_) {
        throw new Error(`Invalid URL: ${url}`);
    }

    const pathParts = urlObj.pathname.split("/").filter(Boolean);
    if (pathParts[0] !== "watch" || !pathParts[1]) {
        throw new Error(
            `Unsupported URL format — expected /watch/{slug}?ep={id}, got: ${url}`
        );
    }

    const showSlug = pathParts[1];
    const epId = urlObj.searchParams.get("ep");
    if (!epId) {
        throw new Error(`Missing episode ID (?ep=...) in URL: ${url}`);
    }

    const episodeId = `${showSlug}?ep=${epId}`;

    // --- Get available servers ---
    let serversData;
    try {
        serversData = await scraper.getEpisodeServers(episodeId);
    } catch (err) {
        throw new Error(`Failed to fetch episode servers: ${err.message}`);
    }

    const subServers = (serversData.sub || []).map((s) => s.serverName || s.name);
    if (subServers.length === 0) {
        throw new Error(`No sub servers available for episode: ${episodeId}`);
    }

    // Pick preferred server
    const serverName =
        SERVER_PREFERENCE.find((s) => subServers.includes(s)) || subServers[0];

    // --- Get sources and episode list concurrently ---
    // Sources are required; episode list is best-effort (for autoplay).
    const [sourcesResult, episodesResult] = await Promise.allSettled([
        scraper.getEpisodeSources(episodeId, serverName, "sub"),
        scraper.getEpisodes(showSlug),
    ]);

    if (sourcesResult.status === "rejected") {
        throw new Error(
            `Failed to fetch sources from server "${serverName}": ${sourcesResult.reason.message}`
        );
    }

    const sourcesData = sourcesResult.value;
    const episodesData =
        episodesResult.status === "fulfilled" ? episodesResult.value : null;

    const sources = sourcesData.sources || [];
    if (sources.length === 0) {
        throw new Error(
            `Server "${serverName}" returned no sources for episode: ${episodeId}`
        );
    }

    // Prefer the default/best quality source (aniwatch returns them pre-sorted)
    const bestSource = sources[0];
    const targetUrl = bestSource.url;

    if (!targetUrl) {
        throw new Error(`Source URL is empty for episode: ${episodeId}`);
    }

    // --- Subtitle tracks ---
    // Track format from aniwatch package: { url, lang } — filter out thumbnails track.
    const subtitleUrls = (sourcesData.tracks || [])
        .filter((t) => t.lang && t.lang.toLowerCase() !== "thumbnails")
        .map((t) => t.url || t.file)
        .filter(Boolean);

    // --- Extra headers (Referer required by some CDNs) ---
    const extraHeaders = {};
    if (sourcesData.headers && sourcesData.headers.Referer) {
        extraHeaders["Referer"] = sourcesData.headers.Referer;
    }

    // --- Episode list for autoplay + episode title ---
    let hasNext = false;
    let nextEpisodeUrl = null;
    let nextEpisodeTitle = "";
    let hasPrev = false;
    let prevEpisodeUrl = null;
    let prevEpisodeTitle = "";
    let playlistItems = [];

    // Fall back to episode list for the title if the source didn't provide one.
    let episodeTitle = sourcesData.episodeTitle || "";

    if (episodesData && Array.isArray(episodesData.episodes)) {
        const episodes = episodesData.episodes;
        const currentIndex = episodes.findIndex((ep) => ep.episodeId === episodeId);
        if (currentIndex !== -1) {
            // Use episode list title if sources gave us nothing.
            if (!episodeTitle) {
                episodeTitle = episodes[currentIndex].title || "";
            }
            // Next episodes
            if (currentIndex + 1 < episodes.length) {
                playlistItems = episodes.slice(currentIndex + 1).map((ep) => ({
                    url: `https://hianime.to/watch/${ep.episodeId}`,
                    title: ep.title || `Episode ${ep.number}`,
                    number: ep.number,
                }));
                hasNext = playlistItems.length > 0;
                if (hasNext) {
                    nextEpisodeUrl = playlistItems[0].url;
                    nextEpisodeTitle = playlistItems[0].title;
                }
            }
            // Previous episode
            if (currentIndex > 0) {
                const prevEp = episodes[currentIndex - 1];
                hasPrev = true;
                prevEpisodeUrl = `https://hianime.to/watch/${prevEp.episodeId}`;
                prevEpisodeTitle = prevEp.title || `Episode ${prevEp.number}`;
            }
        }
    }

    const result = {
        target_url: targetUrl,
        is_playlist: false,
        subtitle_urls: subtitleUrls,
        extra_headers: extraHeaders,
        episode_title: episodeTitle,
        server_used: serverName,
        has_next: hasNext,
        next_episode_url: nextEpisodeUrl,
        next_episode_title: nextEpisodeTitle,
        has_prev: hasPrev,
        prev_episode_url: prevEpisodeUrl,
        prev_episode_title: prevEpisodeTitle,
        playlist_items: playlistItems,
    };

    process.stdout.write(JSON.stringify(result) + "\n");
}

// --- Entry point ---
const url = process.argv[2];
if (!url) {
    process.stderr.write("Usage: node resolve.js <hianime-url>\n");
    process.exit(1);
}

resolve(url).catch((err) => {
    process.stderr.write(`Error: ${err.message}\n`);
    process.exit(1);
});
