/**
 * HiAnime episode resolver.
 *
 * Usage:
 *   node resolve.js [--list] [--type sub|dub] [--server hd-1|hd-2|hd-3] <hianime-url>
 *
 * URL format:
 *   https://hianime.to/watch/{show-slug}?ep={episode-id}
 *
 * Modes:
 *   --list   -> return available server choices only (no source fetch)
 *   default  -> resolve playback source, with failover across servers on errors
 */

"use strict";

const { HiAnime } = require("aniwatch");

// Server preference order used for fallback.
const SERVER_PREFERENCE = ["hd-1", "hd-2", "hd-3"];

function normServerName(s) {
    return (s || "").toString().trim().toLowerCase();
}

function unique(arr) {
    return [...new Set(arr)];
}

function orderedServers(available, preferred = "") {
    const clean = unique((available || []).map(normServerName).filter(Boolean));
    const out = [];
    if (preferred) {
        const p = normServerName(preferred);
        if (clean.includes(p)) out.push(p);
    }
    for (const p of SERVER_PREFERENCE) {
        if (clean.includes(p) && !out.includes(p)) out.push(p);
    }
    for (const s of clean) {
        if (!out.includes(s)) out.push(s);
    }
    return out;
}

function buildNavFromEpisodes(episodesData, episodeId) {
    let hasNext = false;
    let nextEpisodeUrl = null;
    let nextEpisodeTitle = "";
    let hasPrev = false;
    let prevEpisodeUrl = null;
    let prevEpisodeTitle = "";
    let playlistItems = [];
    let episodeTitle = "";
    let currentIndex = -1;

    if (episodesData && Array.isArray(episodesData.episodes)) {
        const episodes = episodesData.episodes;
        currentIndex = episodes.findIndex((ep) => ep.episodeId === episodeId);
        if (currentIndex !== -1) {
            episodeTitle = episodes[currentIndex].title || "";

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

            if (currentIndex > 0) {
                const prevEp = episodes[currentIndex - 1];
                hasPrev = true;
                prevEpisodeUrl = `https://hianime.to/watch/${prevEp.episodeId}`;
                prevEpisodeTitle = prevEp.title || `Episode ${prevEp.number}`;
            }
        }
    }

    return {
        episodeTitle,
        currentIndex,
        hasNext,
        nextEpisodeUrl,
        nextEpisodeTitle,
        hasPrev,
        prevEpisodeUrl,
        prevEpisodeTitle,
        playlistItems,
    };
}

async function resolve(url, opts) {
    const listOnly = !!opts.listOnly;
    const requestedType = (opts.streamType || "sub").toLowerCase();
    const requestedServer = normServerName(opts.serverName || "");

    const scraper = new HiAnime.Scraper();

    // Parse URL
    let urlObj;
    try {
        urlObj = new URL(url);
    } catch (_) {
        throw new Error(`Invalid URL: ${url}`);
    }

    const pathParts = urlObj.pathname.split("/").filter(Boolean);
    if (pathParts[0] !== "watch" || !pathParts[1]) {
        throw new Error(
            `Unsupported URL format - expected /watch/{slug}?ep={id}, got: ${url}`
        );
    }

    const showSlug = pathParts[1];
    const epId = urlObj.searchParams.get("ep");
    if (!epId) {
        throw new Error(`Missing episode ID (?ep=...) in URL: ${url}`);
    }

    const episodeId = `${showSlug}?ep=${epId}`;

    // Available servers
    let serversData;
    try {
        serversData = await scraper.getEpisodeServers(episodeId);
    } catch (err) {
        throw new Error(`Failed to fetch episode servers: ${err.message}`);
    }

    const subServers = unique((serversData.sub || []).map((s) => normServerName(s.serverName || s.name)).filter(Boolean));
    const dubServers = unique((serversData.dub || []).map((s) => normServerName(s.serverName || s.name)).filter(Boolean));

    if (subServers.length === 0 && dubServers.length === 0) {
        throw new Error(`No servers available for episode: ${episodeId}`);
    }

    // Episode list is best-effort (title + autoplay metadata)
    let episodesData = null;
    try {
        episodesData = await scraper.getEpisodes(showSlug);
    } catch (_) {
        episodesData = null;
    }

    const nav = buildNavFromEpisodes(episodesData, episodeId);

    if (listOnly) {
        const available = { sub: subServers, dub: dubServers };
        let defaultType = "sub";
        if (requestedType === "dub" && dubServers.length > 0) {
            defaultType = "dub";
        } else if (subServers.length === 0 && dubServers.length > 0) {
            defaultType = "dub";
        }
        const defaultServers = orderedServers(
            defaultType === "dub" ? dubServers : subServers,
            requestedServer
        );
        process.stdout.write(JSON.stringify({
            mode: "choices",
            available,
            default_type: defaultType,
            default_server: defaultServers[0] || "",
            episode_title: nav.episodeTitle || "",
            current_index: nav.currentIndex,
        }) + "\n");
        return;
    }

    // Select stream type with fallback
    let streamType = requestedType;
    if (streamType !== "sub" && streamType !== "dub") {
        streamType = "sub";
    }
    if (streamType === "dub" && dubServers.length === 0) {
        streamType = "sub";
    }
    if (streamType === "sub" && subServers.length === 0 && dubServers.length > 0) {
        streamType = "dub";
    }

    const pool = streamType === "dub" ? dubServers : subServers;
    const ordered = orderedServers(pool, requestedServer);
    if (ordered.length === 0) {
        throw new Error(`No ${streamType} servers available for episode: ${episodeId}`);
    }

    // Resolve sources with failover across servers
    let sourcesData = null;
    let serverName = "";
    const attempts = [];
    for (const s of ordered) {
        try {
            const data = await scraper.getEpisodeSources(episodeId, s, streamType);
            if (data && Array.isArray(data.sources) && data.sources.length > 0) {
                sourcesData = data;
                serverName = s;
                break;
            }
            attempts.push(`${streamType}/${s}: empty_sources`);
        } catch (err) {
            const msg = (err && err.message) ? err.message : String(err);
            attempts.push(`${streamType}/${s}: ${msg}`);
        }
    }

    if (!sourcesData) {
        throw new Error(`Failed to fetch sources. Attempts: ${attempts.join(" | ")}`);
    }

    const sources = sourcesData.sources || [];
    if (sources.length === 0) {
        throw new Error(`Server "${serverName}" returned no sources for episode: ${episodeId}`);
    }

    // Prefer default/best source (aniwatch returns pre-sorted)
    const bestSource = sources[0];
    const targetUrl = bestSource.url;
    if (!targetUrl) {
        throw new Error(`Source URL is empty for episode: ${episodeId}`);
    }

    // Subtitle tracks (exclude thumbnails)
    const subtitleUrls = (sourcesData.tracks || [])
        .filter((t) => t.lang && t.lang.toLowerCase() !== "thumbnails")
        .map((t) => t.url || t.file)
        .filter(Boolean);

    // Extra headers (Referer required by some CDNs)
    const extraHeaders = {};
    if (sourcesData.headers && sourcesData.headers.Referer) {
        extraHeaders["Referer"] = sourcesData.headers.Referer;
    }

    const episodeTitle = sourcesData.episodeTitle || nav.episodeTitle || "";

    const result = {
        target_url: targetUrl,
        is_playlist: false,
        subtitle_urls: subtitleUrls,
        extra_headers: extraHeaders,
        episode_title: episodeTitle,
        server_used: serverName,
        stream_type_used: streamType,
        available_servers: { sub: subServers, dub: dubServers },
        current_index: nav.currentIndex,
        has_next: nav.hasNext,
        next_episode_url: nav.nextEpisodeUrl,
        next_episode_title: nav.nextEpisodeTitle,
        has_prev: nav.hasPrev,
        prev_episode_url: nav.prevEpisodeUrl,
        prev_episode_title: nav.prevEpisodeTitle,
        playlist_items: nav.playlistItems,
    };

    process.stdout.write(JSON.stringify(result) + "\n");
}

function parseArgs(argv) {
    const out = {
        listOnly: false,
        streamType: "sub",
        serverName: "",
        url: "",
    };
    const args = [...argv];
    while (args.length > 0) {
        const a = args.shift();
        if (a === "--list") {
            out.listOnly = true;
        } else if (a === "--type") {
            out.streamType = (args.shift() || "sub").toLowerCase();
        } else if (a === "--server") {
            out.serverName = normServerName(args.shift() || "");
        } else if (!out.url) {
            out.url = a;
        }
    }
    return out;
}

const opts = parseArgs(process.argv.slice(2));
if (!opts.url) {
    process.stderr.write("Usage: node resolve.js [--list] [--type sub|dub] [--server hd-1|hd-2|hd-3] <hianime-url>\n");
    process.exit(1);
}

resolve(opts.url, opts).catch((err) => {
    process.stderr.write(`Error: ${err.message}\n`);
    process.exit(1);
});
