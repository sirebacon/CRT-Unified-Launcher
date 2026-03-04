"""Unified cross-provider media history.

Writes to runtime/media_history.json (atomic writes).
Imports existing runtime/youtube_history.json on first run (one-time migration).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("youtube.media_history")

_PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HISTORY_FILE  = os.path.join(_PROJECT_ROOT, "runtime", "media_history.json")
_LEGACY_FILE   = os.path.join(_PROJECT_ROOT, "runtime", "youtube_history.json")
_IMPORT_SENTINEL = _LEGACY_FILE + ".imported"

MAX_HISTORY = 500


# ---------------------------------------------------------------------------
# Internal I/O
# ---------------------------------------------------------------------------

def _load_raw() -> list:
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _save_raw(items: list) -> None:
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    tmp = _HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _HISTORY_FILE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_entry(
    provider: str,
    title: str,
    url: str,
    continue_key: str = "",
    playback_outcome: str = "in_progress",
    duration_sec: Optional[float] = None,
    progress_pct: float = 0.0,
) -> None:
    """Append a history entry."""
    items = _load_raw()
    items.append({
        "provider": provider,
        "title": title,
        "url": url,
        "continue_key": continue_key,
        "playback_outcome": playback_outcome,
        "duration_sec": duration_sec,
        "progress_pct": progress_pct,
        "watched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if len(items) > MAX_HISTORY:
        items = items[-MAX_HISTORY:]
    _save_raw(items)


def get_history(provider: Optional[str] = None, limit: int = 50) -> list:
    """Return recent history entries, most recent first."""
    items = _load_raw()
    if provider:
        items = [i for i in items if i.get("provider") == provider]
    return list(reversed(items[-limit:]))


def remove_entry(url: str) -> bool:
    """Remove all entries matching a URL. Returns True if any removed."""
    items = _load_raw()
    before = len(items)
    items = [i for i in items if i.get("url") != url]
    if len(items) < before:
        _save_raw(items)
        return True
    return False


def clear_provider(provider: str) -> int:
    """Remove all history entries for a provider. Returns count removed."""
    items = _load_raw()
    before = len(items)
    items = [i for i in items if i.get("provider") != provider]
    _save_raw(items)
    return before - len(items)


def clear_all() -> int:
    """Remove all history entries. Returns count removed."""
    items = _load_raw()
    count = len(items)
    _save_raw([])
    return count


def import_legacy_history() -> int:
    """One-time import of youtube_history.json into unified history.

    Returns count of entries imported (0 on subsequent calls — sentinel file prevents re-import).
    Writes a log line so it's easy to confirm migration ran.
    """
    if os.path.exists(_IMPORT_SENTINEL):
        return 0

    if not os.path.exists(_LEGACY_FILE):
        # No legacy file; write sentinel so we don't check on every startup
        try:
            with open(_IMPORT_SENTINEL, "w") as f:
                f.write("no_legacy")
        except Exception:
            pass
        return 0

    try:
        with open(_LEGACY_FILE, "r", encoding="utf-8") as f:
            legacy = json.load(f)
        if not isinstance(legacy, list):
            return 0
    except Exception as e:
        log.warning("legacy history import failed to read %s: %s", _LEGACY_FILE, e)
        return 0

    existing = _load_raw()
    existing_urls = {i.get("url") for i in existing}

    imported = []
    for entry in legacy:
        url = entry.get("url", "")
        if url and url not in existing_urls:
            imported.append({
                "provider": "youtube",
                "title": entry.get("title", ""),
                "url": url,
                "continue_key": "",
                "playback_outcome": "in_progress",
                "duration_sec": None,
                "progress_pct": 0.0,
                "watched_at": entry.get("watched_at", ""),
            })

    if imported:
        all_items = existing + imported
        if len(all_items) > MAX_HISTORY:
            all_items = all_items[-MAX_HISTORY:]
        _save_raw(all_items)
        log.info("legacy history import: %d entries imported from %s", len(imported), _LEGACY_FILE)

    try:
        with open(_IMPORT_SENTINEL, "w") as f:
            f.write(f"imported:{len(imported)}")
    except Exception:
        pass

    return len(imported)
