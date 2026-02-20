"""Generic file backup and restore.

Copies files byte-for-byte; knows nothing about file formats.

Usage:
    backup_dir = backup_files([r"C:\\path\\to\\a.cfg", r"C:\\path\\to\\b.xml"])
    # ... apply patches ...
    all_ok = restore_files(backup_dir)
    cleanup(backup_dir)

restore_files() never raises.  On a partial failure it prints manual copy
instructions for each failed file and returns False so the caller can decide
how to proceed.
"""
import json
import os
import shutil
import tempfile
from typing import List

_MANIFEST = "backup_manifest.json"


def backup_files(paths: List[str]) -> str:
    """Copy each file into a new temp directory.

    Returns the backup directory path.  Raises if any file cannot be read.
    The caller must call cleanup() when the backup is no longer needed.
    """
    backup_dir = tempfile.mkdtemp(prefix="crt_session_backup_")
    entries = []
    for i, src in enumerate(paths):
        ext = os.path.splitext(src)[1]
        dst_name = f"{i:04d}{ext}"
        shutil.copy2(src, os.path.join(backup_dir, dst_name))
        entries.append({"original": src, "backup": dst_name})
    with open(os.path.join(backup_dir, _MANIFEST), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
    return backup_dir


def restore_files(backup_dir: str) -> bool:
    """Restore all files to their original locations.

    On failure: logs each file with manual copy instructions and continues
    rather than aborting.  Returns True only if every file was restored.
    """
    manifest_path = os.path.join(backup_dir, _MANIFEST)
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as exc:
        print(f"[backup] Cannot read manifest: {exc}")
        print(f"         Backup directory: {backup_dir}")
        return False

    all_ok = True
    for entry in entries:
        src = os.path.join(backup_dir, entry["backup"])
        dst = entry["original"]
        try:
            shutil.copy2(src, dst)
        except Exception as exc:
            print(f"[backup] RESTORE FAILED: {dst}")
            print(f"         Reason  : {exc}")
            print(f"         Manual  : copy \"{src}\" \"{dst}\"")
            all_ok = False
    return all_ok


def cleanup(backup_dir: str) -> None:
    """Remove the backup directory and all its contents."""
    try:
        shutil.rmtree(backup_dir)
    except Exception as exc:
        print(f"[backup] Cleanup failed for {backup_dir}: {exc}")
