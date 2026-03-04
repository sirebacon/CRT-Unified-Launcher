"""Progress tracking for the Continue Watching feature.

Persistence: runtime/media_progress.json (atomic writes via temp+rename).
`playback_outcome` is the source of truth; `is_completed` is a derived convenience field.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("youtube.progress")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROGRESS_FILE = os.path.join(_PROJECT_ROOT, "runtime", "media_progress.json")

OUTCOME_IN_PROGRESS = "in_progress"
OUTCOME_COMPLETED   = "completed"
OUTCOME_SKIPPED     = "skipped"


# ---------------------------------------------------------------------------
# Internal I/O
# ---------------------------------------------------------------------------

def _load_raw() -> dict:
    try:
        with open(_PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data:
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"version": 1, "items": []}


def _save_raw(data: dict) -> None:
    os.makedirs(os.path.dirname(_PROGRESS_FILE), exist_ok=True)
    tmp = _PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _PROGRESS_FILE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_progress(
    continue_key: str,
    provider: str,
    entity_type: str,
    title: str,
    sub_title: str = "",
    target_url: str = "",
    episode_url: str = "",
    episode_index: Optional[int] = None,
    resume_position_sec: float = 0.0,
    duration_sec: Optional[float] = None,
    playback_outcome: str = OUTCOME_IN_PROGRESS,
    min_delta_sec: float = 5.0,
    max_items: int = 20,
) -> bool:
    """Upsert a progress entry.

    Returns True if written, False if skipped by min-delta guard.
    min-delta guard: avoids no-op writes while paused (only applied to in_progress updates).
    """
    data = _load_raw()
    items: list = data["items"]

    existing = next((i for i in items if i.get("continue_key") == continue_key), None)

    # Min-delta guard — skip if position barely moved (paused or same checkpoint)
    if existing and playback_outcome == OUTCOME_IN_PROGRESS:
        prev_pos = existing.get("resume_position_sec", 0.0)
        if abs(resume_position_sec - prev_pos) < min_delta_sec:
            return False

    progress_pct = 0.0
    if duration_sec and duration_sec > 0:
        progress_pct = round((resume_position_sec / duration_sec) * 100, 1)

    entry = {
        "continue_key": continue_key,
        "provider": provider,
        "entity_type": entity_type,
        "title": title,
        "sub_title": sub_title,
        "target_url": target_url,
        "resume_position_sec": round(resume_position_sec, 1),
        "duration_sec": round(duration_sec, 1) if duration_sec is not None else None,
        "progress_pct": progress_pct,
        "episode_url": episode_url,
        "episode_index": episode_index,
        "last_watched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_completed": playback_outcome == OUTCOME_COMPLETED,   # derived convenience
        "playback_outcome": playback_outcome,                    # source of truth
    }

    if existing:
        items[items.index(existing)] = entry
    else:
        items.append(entry)

    # Prune: keep at most max_items in-progress + max_items done entries
    in_prog = [i for i in items if i.get("playback_outcome") == OUTCOME_IN_PROGRESS]
    done    = [i for i in items if i.get("playback_outcome") != OUTCOME_IN_PROGRESS]
    in_prog.sort(key=lambda i: i.get("last_watched_at", ""), reverse=True)
    data["items"] = in_prog[:max_items] + done[-max_items:]

    _save_raw(data)
    log.debug("progress upsert key=%s outcome=%s pos=%.1fs pct=%.1f",
              continue_key, playback_outcome, resume_position_sec, progress_pct)
    return True


def get_continue_lane(max_items: int = 20) -> list[dict]:
    """Return in-progress items sorted by last_watched_at descending."""
    data = _load_raw()
    items = [i for i in data["items"] if i.get("playback_outcome") == OUTCOME_IN_PROGRESS]
    items.sort(key=lambda i: i.get("last_watched_at", ""), reverse=True)
    return items[:max_items]


def get_item(continue_key: str) -> Optional[dict]:
    """Get a single progress entry by continue_key, or None."""
    data = _load_raw()
    return next((i for i in data["items"] if i.get("continue_key") == continue_key), None)


def remove_item(continue_key: str) -> bool:
    """Remove an entry by continue_key. Returns True if found and removed."""
    data = _load_raw()
    before = len(data["items"])
    data["items"] = [i for i in data["items"] if i.get("continue_key") != continue_key]
    if len(data["items"]) < before:
        _save_raw(data)
        return True
    return False


def mark_completed(continue_key: str) -> bool:
    """Force an item to completed state. Returns True if found."""
    data = _load_raw()
    for item in data["items"]:
        if item.get("continue_key") == continue_key:
            item["playback_outcome"] = OUTCOME_COMPLETED
            item["is_completed"] = True
            _save_raw(data)
            return True
    return False


def write_checkpoint(
    continue_key: str,
    provider: str,
    entity_type: str,
    title: str,
    sub_title: str,
    target_url: str,
    episode_url: str,
    episode_index: Optional[int],
    position_sec: float,
    duration_sec: Optional[float],
    completion_threshold_pct: float = 92.0,
    max_items: int = 20,
    force: bool = False,
    min_position_sec: float = 30.0,
    skip_signal: bool = False,
) -> tuple[str, bool]:
    """Apply safety guards, classify outcome, write a progress entry.

    Guards (Phase 6.4):
    - Returns (OUTCOME_IN_PROGRESS, False) if duration_sec is None/0.
    - Clamps position_sec to max(0, duration_sec - 10).
    - Returns (outcome, False) if in_progress and position < min_position_sec.

    force=True  → bypass min_delta guard (min_delta_sec=0 passed to upsert_progress).
    skip_signal → if True and pct < threshold, outcome = OUTCOME_SKIPPED.

    Returns (outcome_str, written_bool).
    """
    if not duration_sec:
        return OUTCOME_IN_PROGRESS, False

    position_sec = max(0.0, min(position_sec, duration_sec - 10))
    pct = (position_sec / duration_sec) * 100

    if skip_signal and pct < completion_threshold_pct:
        outcome = OUTCOME_SKIPPED
    elif pct >= completion_threshold_pct:
        outcome = OUTCOME_COMPLETED
    else:
        outcome = OUTCOME_IN_PROGRESS

    if outcome == OUTCOME_IN_PROGRESS and position_sec < min_position_sec:
        return outcome, False

    written = upsert_progress(
        continue_key=continue_key,
        provider=provider,
        entity_type=entity_type,
        title=title,
        sub_title=sub_title,
        target_url=target_url,
        episode_url=episode_url,
        episode_index=episode_index,
        resume_position_sec=position_sec,
        duration_sec=duration_sec,
        playback_outcome=outcome,
        max_items=max_items,
        min_delta_sec=0 if force else 5.0,
    )
    return outcome, written
