"""Session, favorites, history, and bookmark persistence (all JSON-backed)."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qsl

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNTIME = os.path.join(_PROJECT_ROOT, "runtime")

_SESSION_PATH   = os.path.join(_RUNTIME, "youtube_session.json")
_FAVORITES_PATH = os.path.join(_RUNTIME, "youtube_favorites.json")
_HISTORY_PATH   = os.path.join(_RUNTIME, "youtube_history.json")
_BOOKMARKS_PATH = os.path.join(_RUNTIME, "youtube_bookmarks.json")

_PROFILES_DIR       = os.path.join(_PROJECT_ROOT, "profiles")
_ZOOM_PRESETS_PATH  = os.path.join(_PROFILES_DIR, "youtube_zoom_presets.json")

_HISTORY_MAX = 200

# ---- Internal helpers ----

def _ensure_runtime():
    os.makedirs(_RUNTIME, exist_ok=True)


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, data) -> None:
    _ensure_runtime()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- URL normalisation ----

_STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "feature", "app", "src", "from",
}


def normalize_url(url: str) -> str:
    """Strip tracking query params; keep list=, v=, etc."""
    try:
        p = urlparse(url)
        kept = [(k, v) for k, v in parse_qsl(p.query) if k not in _STRIP_PARAMS]
        clean = p._replace(query=urlencode(kept))
        return clean.geturl()
    except Exception:
        return url


# ---- Session ----

def save_session(
    url: str,
    title: str,
    is_playlist: bool,
    playlist_pos: Optional[int],
    position_sec: Optional[float],
) -> None:
    data = {
        "url": url,
        "title": title,
        "is_playlist": is_playlist,
        "playlist_pos": playlist_pos if playlist_pos is not None else 0,
        "position_sec": round(position_sec, 2) if position_sec is not None else 0.0,
        "last_played": _now_iso(),
    }
    _write_json(_SESSION_PATH, data)


def load_session() -> Optional[dict]:
    data = _read_json(_SESSION_PATH, None)
    if isinstance(data, dict) and data.get("url"):
        return data
    return None


def clear_session() -> None:
    try:
        os.remove(_SESSION_PATH)
    except FileNotFoundError:
        pass


# ---- Favorites ----

def load_favorites() -> list:
    return _read_json(_FAVORITES_PATH, [])


def _save_favorites(favs: list) -> None:
    _write_json(_FAVORITES_PATH, favs)


def add_favorite(url: str, title: str, fav_type: str = "video") -> None:
    """Add or update a favorite entry (deduped by normalized URL)."""
    nurl = normalize_url(url)
    favs = load_favorites()
    for fav in favs:
        if normalize_url(fav.get("url", "")) == nurl:
            fav["title"] = title
            fav["last_played_at"] = _now_iso()
            fav["play_count"] = fav.get("play_count", 0) + 1
            _save_favorites(favs)
            return
    favs.append({
        "id": str(uuid.uuid4()),
        "type": fav_type,
        "title": title,
        "url": url,
        "tags": [],
        "created_at": _now_iso(),
        "last_played_at": _now_iso(),
        "play_count": 1,
        "resume_index": 0,
        "resume_position_sec": 0.0,
    })
    _save_favorites(favs)


def remove_favorite(url: str) -> bool:
    nurl = normalize_url(url)
    favs = load_favorites()
    new_favs = [f for f in favs if normalize_url(f.get("url", "")) != nurl]
    if len(new_favs) < len(favs):
        _save_favorites(new_favs)
        return True
    return False


# ---- History ----

def load_history() -> list:
    return _read_json(_HISTORY_PATH, [])


def add_to_history(url: str, title: str) -> None:
    """Append to history, auto-prune to _HISTORY_MAX."""
    hist = load_history()
    # Remove previous entry for same URL to avoid duplicate runs
    nurl = normalize_url(url)
    hist = [e for e in hist if normalize_url(e.get("url", "")) != nurl]
    hist.append({
        "url": url,
        "title": title,
        "played_at": _now_iso(),
    })
    if len(hist) > _HISTORY_MAX:
        hist = hist[-_HISTORY_MAX:]
    _write_json(_HISTORY_PATH, hist)


# ---- Bookmarks ----

def load_bookmarks() -> dict:
    return _read_json(_BOOKMARKS_PATH, {})


def save_bookmarks(data: dict) -> None:
    _write_json(_BOOKMARKS_PATH, data)


def get_bookmarks(url: str) -> list:
    data = load_bookmarks()
    nurl = normalize_url(url)
    # Try exact match first, then normalized
    return data.get(url, data.get(nurl, []))


def add_bookmark(url: str, time_sec: float, name: Optional[str] = None) -> None:
    nurl = normalize_url(url)
    data = load_bookmarks()
    marks = data.get(nurl, [])
    marks.append({
        "name": name or _fmt_time(time_sec),
        "time_sec": round(time_sec, 2),
    })
    data[nurl] = marks
    save_bookmarks(data)


def _fmt_time(seconds: float) -> str:
    """Format seconds as M:SS."""
    if seconds is None:
        return "?:??"
    s = int(seconds)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


# ---- Zoom presets ----

def load_zoom_presets() -> list:
    """Load named zoom presets from profiles/youtube_zoom_presets.json."""
    try:
        with open(_ZOOM_PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_zoom_presets(presets: list) -> None:
    os.makedirs(_PROFILES_DIR, exist_ok=True)
    with open(_ZOOM_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2, ensure_ascii=False)
        f.write("\n")


def add_zoom_preset(name: str, zoom: float, pan_x: float, pan_y: float) -> None:
    """Add or replace a named zoom preset (zoom, pan_x, pan_y)."""
    presets = load_zoom_presets()
    for p in presets:
        if p.get("name") == name:
            p["zoom"]  = round(zoom,  4)
            p["pan_x"] = round(pan_x, 4)
            p["pan_y"] = round(pan_y, 4)
            save_zoom_presets(presets)
            return
    presets.append({
        "name":  name,
        "zoom":  round(zoom,  4),
        "pan_x": round(pan_x, 4),
        "pan_y": round(pan_y, 4),
    })
    save_zoom_presets(presets)
