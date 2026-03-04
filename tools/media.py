"""Media progress and history diagnostics for crt_tools."""

import json
import os

_PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROGRESS_FILE = os.path.join(_PROJECT_ROOT, "runtime", "media_progress.json")
_HISTORY_FILE  = os.path.join(_PROJECT_ROOT, "runtime", "media_history.json")


def _fmt_time(seconds) -> str:
    if seconds is None:
        return "?:??"
    s = int(seconds)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def media_progress() -> int:
    """Show all Continue Watching progress entries."""
    if not os.path.exists(_PROGRESS_FILE):
        print(f"[tools] No progress file: {_PROGRESS_FILE}")
        return 0
    try:
        with open(_PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[tools] FAIL: could not read progress file: {e}")
        return 1

    items = data.get("items", [])
    in_prog = [i for i in items if i.get("playback_outcome") == "in_progress"]
    done    = [i for i in items if i.get("playback_outcome") != "in_progress"]
    in_prog.sort(key=lambda i: i.get("last_watched_at", ""), reverse=True)
    done.sort(key=lambda i: i.get("last_watched_at", ""), reverse=True)

    _BADGE = {"in_progress": "▶", "completed": "✓", "skipped": "»"}

    print(f"=== Media Progress  ({len(in_prog)} in-progress, {len(done)} done) ===")
    print()

    def _print_item(item):
        badge   = _BADGE.get(item.get("playback_outcome", ""), " ")
        prov    = item.get("provider", "?")[:3]
        title   = (item.get("title") or "?")[:40]
        sub     = item.get("sub_title", "")
        ep_idx  = item.get("episode_index")
        ep_str  = f"  ep {ep_idx + 1}" if ep_idx is not None else ""
        pos     = _fmt_time(item.get("resume_position_sec"))
        dur     = _fmt_time(item.get("duration_sec"))
        pct     = item.get("progress_pct", 0)
        date    = item.get("last_watched_at", "")[:16].replace("T", " ")
        key     = item.get("continue_key", "")
        sub_str = f"  [{sub}]" if sub else ""
        print(f"  {badge} [{prov}] {title}{sub_str}{ep_str}")
        print(f"       {pos}/{dur}  {pct:.0f}%  {date}  key={key}")

    if in_prog:
        print("In-progress:")
        for item in in_prog:
            _print_item(item)
        print()

    if done:
        print("Done (completed/skipped):")
        for item in done:
            _print_item(item)
        print()

    if not items:
        print("  (no entries)")

    return 0


def media_history() -> int:
    """Show recent watch history stats and entries."""
    if not os.path.exists(_HISTORY_FILE):
        print(f"[tools] No history file: {_HISTORY_FILE}")
        return 0
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as e:
        print(f"[tools] FAIL: could not read history file: {e}")
        return 1

    if not isinstance(entries, list):
        print("[tools] FAIL: unexpected history format")
        return 1

    total = len(entries)
    by_prov: dict = {}
    by_outcome: dict = {}
    for e in entries:
        p = e.get("provider", "unknown")
        by_prov[p] = by_prov.get(p, 0) + 1
        o = e.get("playback_outcome", "unknown")
        by_outcome[o] = by_outcome.get(o, 0) + 1

    print(f"=== Watch History  ({total} total entries) ===")
    print()
    print("By provider:")
    for prov, cnt in sorted(by_prov.items(), key=lambda x: -x[1]):
        print(f"  {prov:<12}  {cnt}")
    print()
    print("By outcome:")
    _BADGE = {"in_progress": "▶", "completed": "✓", "skipped": "»"}
    for outcome, cnt in sorted(by_outcome.items(), key=lambda x: -x[1]):
        badge = _BADGE.get(outcome, " ")
        print(f"  {badge} {outcome:<14}  {cnt}")
    print()

    recent = sorted(entries, key=lambda e: e.get("watched_at", ""), reverse=True)[:15]
    print(f"Most recent {len(recent)} entries:")
    for e in recent:
        badge = _BADGE.get(e.get("playback_outcome", ""), " ")
        prov  = e.get("provider", "?")[:3]
        title = (e.get("title") or e.get("url", "?"))[:50]
        pct   = e.get("progress_pct", 0)
        date  = e.get("watched_at", "")[:10]
        print(f"  {badge} [{prov}] {title:<50}  {pct:3.0f}%  {date}")

    return 0
