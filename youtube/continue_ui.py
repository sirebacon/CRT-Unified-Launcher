"""Continue Watching UI surfaces — lane and history screen."""

import logging
import os
import time
from typing import Optional

from youtube.progress import get_continue_lane, mark_completed, remove_item
from youtube.media_history import get_history, remove_entry, clear_provider, clear_all
from youtube.state import get_bookmarks

log = logging.getLogger("youtube.continue_ui")


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


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


def run_continue_lane(max_items: int = 20) -> tuple[Optional[str], Optional[float], bool]:
    """Show the Continue Watching lane.

    Returns (url, resume_pos, play_next_episode) when the user selects an item,
    or (None, None, False) when the user hits Enter or an unrecognized key.
    Raises SystemExit(0) on KeyboardInterrupt/EOFError.
    """
    _continue_items = get_continue_lane(max_items=max_items)
    if not _continue_items:
        return None, None, False

    _dirty = True
    while _dirty:
        _dirty = False
        _continue_items = get_continue_lane(max_items=max_items)
        if not _continue_items:
            break
        print("\nContinue Watching:")
        for i, item in enumerate(_continue_items, 1):
            pct       = item.get("progress_pct", 0)
            sub       = item.get("sub_title", "")
            label     = item["title"] + (f"  [{sub}]" if sub else "")
            date      = item.get("last_watched_at", "")[:10]
            ep_idx    = item.get("episode_index")
            next_hint = (f"  → Ep {ep_idx + 2}" if item.get("provider") == "hianime"
                         and ep_idx is not None else "")
            print(f"  {i}) {label}{next_hint}  {pct:.0f}%  {date}")
        print()
        print(f"  1-{len(_continue_items)} play  R<N> remove  K<N> mark done  "
              f"B<N> bookmark  U<N> up-next  H history  A activity  Enter URL prompt")
        print("Pick: ", end="", flush=True)
        try:
            pick = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(0)

        if pick == "h":
            run_media_history_screen()
            _dirty = True
        elif pick == "a":
            run_recent_activity_screen()
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
        elif pick.startswith("b") and pick[1:].isdigit():
            bidx = int(pick[1:]) - 1
            if 0 <= bidx < len(_continue_items):
                bitem = _continue_items[bidx]
                burl  = bitem.get("episode_url") or bitem.get("target_url", "")
                bmarks = get_bookmarks(burl) if burl else []
                if not bmarks:
                    print("  No bookmarks for this item.")
                    time.sleep(0.8)
                else:
                    print()
                    for j, m in enumerate(bmarks, 1):
                        print(f"  {j}) {m.get('name','?')}  @ {_fmt_time(m.get('time_sec',0))}")
                    print("Pick bookmark (Enter to cancel): ", end="", flush=True)
                    try:
                        bpick = input().strip()
                    except (EOFError, KeyboardInterrupt):
                        bpick = ""
                    if bpick.isdigit():
                        bidx2 = int(bpick) - 1
                        if 0 <= bidx2 < len(bmarks):
                            return burl, bmarks[bidx2]["time_sec"], False
            _dirty = True
        elif pick.startswith("u") and pick[1:].isdigit():
            uidx = int(pick[1:]) - 1
            if 0 <= uidx < len(_continue_items):
                uitem = _continue_items[uidx]
                if uitem.get("provider") == "hianime" and uitem.get("episode_url"):
                    log.info("continue up-next: episode_url=%s", uitem["episode_url"])
                    return uitem["episode_url"], None, True
                else:
                    print("  Up Next is only available for HiAnime series.")
                    time.sleep(0.8)
            _dirty = True
        elif pick.isdigit():
            idx = int(pick) - 1
            if 0 <= idx < len(_continue_items):
                sel     = _continue_items[idx]
                sel_url = sel.get("episode_url") or sel.get("target_url", "")
                sel_pos = sel.get("resume_position_sec") or None
                # 6.5: bookmark-aware resume prompt
                if sel_url and sel_pos is not None:
                    bmarks = get_bookmarks(sel_url)
                    if bmarks:
                        print(f"\n  Resume at {_fmt_time(sel_pos)} (saved)  or pick bookmark?")
                        print(f"  1) Resume at {_fmt_time(sel_pos)}")
                        print(f"  2) Pick bookmark")
                        print("Pick [Enter=1]: ", end="", flush=True)
                        try:
                            rpick = input().strip()
                        except (EOFError, KeyboardInterrupt):
                            rpick = "1"
                        if rpick == "2":
                            print()
                            for j, m in enumerate(bmarks, 1):
                                print(f"    {j}) {m.get('name','?')}  @ {_fmt_time(m.get('time_sec',0))}")
                            print("  Pick [Enter=cancel]: ", end="", flush=True)
                            try:
                                bpick = input().strip()
                            except (EOFError, KeyboardInterrupt):
                                bpick = ""
                            if bpick.isdigit():
                                bidx = int(bpick) - 1
                                if 0 <= bidx < len(bmarks):
                                    sel_pos = bmarks[bidx]["time_sec"]
                log.info("continue watching: selected key=%s url=%s pos=%s",
                         sel.get("continue_key"), sel_url, sel_pos)
                return sel_url, sel_pos, False
        # out-of-range digit or unrecognized → _dirty stays False → URL prompt

    return None, None, False


def run_recent_activity_screen() -> Optional[str]:
    """Merged in-progress + history sorted by recency (up to 25 items).

    Returns a URL to open, or None.
    """
    PAGE_SIZE = 25
    _OUTCOME_BADGE = {"in_progress": "▶", "completed": "✓", "skipped": "»"}

    while True:
        in_prog = get_continue_lane(max_items=15)
        hist    = get_history(limit=30)

        seen: set = set()
        feed: list = []

        for item in in_prog:
            u = item.get("episode_url") or item.get("target_url", "")
            seen.add(u)
            sub   = item.get("sub_title", "")
            label = item.get("title", "?")
            feed.append({
                "title":    label,
                "sub":      sub,
                "provider": item.get("provider", "?"),
                "pct":      item.get("progress_pct", 0),
                "outcome":  item.get("playback_outcome", "in_progress"),
                "ts":       item.get("last_watched_at", ""),
                "url":      u,
            })

        for entry in hist:
            u = entry.get("url", "")
            if u in seen:
                continue
            seen.add(u)
            feed.append({
                "title":    entry.get("title") or u,
                "sub":      "",
                "provider": entry.get("provider", "?"),
                "pct":      entry.get("progress_pct", 0),
                "outcome":  entry.get("playback_outcome", ""),
                "ts":       entry.get("watched_at", ""),
                "url":      u,
            })

        feed.sort(key=lambda x: x["ts"], reverse=True)
        feed = feed[:PAGE_SIZE]

        os.system("cls" if os.name == "nt" else "clear")
        print("=== Recent Activity ===")
        if not feed:
            print("  (no activity)")
        else:
            for i, row in enumerate(feed, 1):
                badge = _OUTCOME_BADGE.get(row["outcome"], " ")
                prov  = row["provider"][:3]
                title = row["title"][:44]
                sub   = f"  [{row['sub']}]" if row["sub"] else ""
                pct   = row["pct"]
                date  = row["ts"][:10]
                print(f"  {i:2d}) {badge} [{prov}] {title}{sub:<10}  {pct:3.0f}%  {date}")
        print()
        print("  H=history  X=exit  number=re-open URL")
        print("Pick: ", end="", flush=True)
        try:
            pick = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None

        if pick in ("x", "q", "b", ""):
            return None
        elif pick == "h":
            run_media_history_screen()
        elif pick.isdigit():
            idx = int(pick) - 1
            if 0 <= idx < len(feed):
                return feed[idx]["url"]
    return None
