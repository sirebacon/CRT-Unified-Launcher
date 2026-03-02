"""Queue file loading/saving for multi-URL playback."""

import json
import os
from typing import List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNTIME = os.path.join(_PROJECT_ROOT, "runtime")
_QUEUE_PATH = os.path.join(_RUNTIME, "youtube_queue.json")
_TEMP_PLAYLIST_PATH = os.path.join(_RUNTIME, "youtube_queue_temp.txt")


def load_queue_file(path: str) -> List[str]:
    """Load URLs from a .txt (one per line) or .json (list of strings or {url} dicts)."""
    try:
        if path.lower().endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            urls = []
            for item in data:
                if isinstance(item, str):
                    urls.append(item.strip())
                elif isinstance(item, dict):
                    u = item.get("url", "").strip()
                    if u:
                        urls.append(u)
            return [u for u in urls if u]
        else:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    except Exception as e:
        print(f"[youtube] Could not load queue file {path!r}: {e}")
        return []


def load_saved_queue() -> List[str]:
    """Load the persisted queue from runtime/youtube_queue.json."""
    return load_queue_file(_QUEUE_PATH)


def save_queue(urls: List[str]) -> None:
    """Save URL list to runtime/youtube_queue.json."""
    os.makedirs(_RUNTIME, exist_ok=True)
    with open(_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_temp_playlist(urls: List[str]) -> str:
    """Write URLs to runtime/youtube_queue_temp.txt, return path."""
    os.makedirs(_RUNTIME, exist_ok=True)
    with open(_TEMP_PLAYLIST_PATH, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")
    return _TEMP_PLAYLIST_PATH
