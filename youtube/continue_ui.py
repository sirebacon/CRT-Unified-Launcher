"""Continue Watching UI surfaces — lane and history screen."""

import logging
import os
import time
from typing import Optional

from youtube.progress import get_continue_lane, mark_completed, remove_item
from youtube.media_history import get_history, remove_entry, clear_provider, clear_all

log = logging.getLogger("youtube.continue_ui")


def run_media_history_screen(provider_filter: str = "") -> Optional[str]:
    """Show unified watch history. Returns a URL to open, or None."""
    _filter = provider_filter
    _PROVIDER_LABELS = {"": "All", "youtube": "YouTube", "hianime": "HiAnime"}
    _OUTCOME_BADGE   = {"in_progress": "▶", "completed": "✓", "skipped": "»"}
    PAGE_SIZE = 20

    while True:
        items = get_history(provider=_filter or None, limit=PAGE_SIZE)
        os.system("cls" if os.name == "nt" else "clear")
        filter_label = _PROVIDER_LABELS.get(_filter, _filter or "All")
        print(f"=== Watch History  [{filter_label}] ===")
        if not items:
            print("  (no entries)")
        else:
            for i, entry in enumerate(items, 1):
                title   = (entry.get("title") or entry.get("url", "?"))[:52]
                prov    = entry.get("provider", "?")[:3]
                outcome = entry.get("playback_outcome", "")
                badge   = _OUTCOME_BADGE.get(outcome, " ")
                pct     = entry.get("progress_pct", 0)
                date    = (entry.get("watched_at", "")[:10])
                print(f"  {i:2d}) {badge} [{prov}] {title:<52}  {pct:3.0f}%  {date}")
        print()
        print("  Y=YouTube  I=HiAnime  A=All  R<N>=remove  C=clear filter  X=exit")
        print("Pick (number to re-open URL): ", end="", flush=True)
        try:
            pick = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None

        if pick in ("x", "b", "q", ""):
            return None
        elif pick == "a":
            _filter = ""
        elif pick == "y":
            _filter = "youtube"
        elif pick in ("i", "h"):
            _filter = "hianime"
        elif pick == "c":
            target = _filter or "all"
            print(f"  Clear {target} history? [Y/N]: ", end="", flush=True)
            try:
                ans = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans == "y":
                n = clear_provider(_filter) if _filter else clear_all()
                print(f"  Cleared {n} entries.")
                time.sleep(1.0)
        elif pick.startswith("r") and pick[1:].isdigit():
            idx = int(pick[1:]) - 1
            if 0 <= idx < len(items):
                entry = items[idx]
                remove_entry(entry.get("url", ""))
                print(f"  Removed: {(entry.get('title') or '?')[:60]}")
                time.sleep(0.8)
        elif pick.isdigit():
            idx = int(pick) - 1
            if 0 <= idx < len(items):
                return items[idx].get("url")
    return None


def run_continue_lane(max_items: int = 20) -> tuple[Optional[str], Optional[float]]:
    """Show the Continue Watching lane.

    Returns (url, resume_pos) when the user selects an item, or (None, None)
    when the user hits Enter or an unrecognized key to proceed to the URL prompt.
    Raises SystemExit(0) on KeyboardInterrupt/EOFError.
    """
    _continue_items = get_continue_lane(max_items=max_items)
    if not _continue_items:
        return None, None

    _dirty = True
    while _dirty:
        _dirty = False
        _continue_items = get_continue_lane(max_items=max_items)
        if not _continue_items:
            break
        print("\nContinue Watching:")
        for i, item in enumerate(_continue_items, 1):
            pct   = item.get("progress_pct", 0)
            sub   = item.get("sub_title", "")
            label = item["title"] + (f"  [{sub}]" if sub else "")
            date  = item.get("last_watched_at", "")[:10]
            print(f"  {i}) {label}  {pct:.0f}%  {date}")
        print()
        print(f"  1-{len(_continue_items)} play  R<N> remove  K<N> mark done  H history  Enter URL prompt")
        print("Pick: ", end="", flush=True)
        try:
            pick = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(0)

        if pick == "h":
            run_media_history_screen()
            _dirty = True
        elif pick.startswith("r") and pick[1:].isdigit():
            ridx = int(pick[1:]) - 1
            if 0 <= ridx < len(_continue_items):
                ritem = _continue_items[ridx]
                remove_item(ritem.get("continue_key", ""))
                print(f"  Removed: {ritem.get('title', '?')[:60]}")
                time.sleep(0.6)
            _dirty = True
        elif pick.startswith("k") and pick[1:].isdigit():
            kidx = int(pick[1:]) - 1
            if 0 <= kidx < len(_continue_items):
                kitem = _continue_items[kidx]
                mark_completed(kitem.get("continue_key", ""))
                print(f"  Marked done: {kitem.get('title', '?')[:60]}")
                time.sleep(0.6)
            _dirty = True
        elif pick.isdigit():
            idx = int(pick) - 1
            if 0 <= idx < len(_continue_items):
                sel = _continue_items[idx]
                sel_url = sel.get("episode_url") or sel.get("target_url", "")
                sel_pos = sel.get("resume_position_sec") or None
                log.info(
                    "continue watching: selected key=%s url=%s pos=%s",
                    sel.get("continue_key"), sel_url, sel_pos,
                )
                return sel_url, sel_pos
        # out-of-range digit or unrecognized → _dirty stays False → URL prompt

    return None, None
