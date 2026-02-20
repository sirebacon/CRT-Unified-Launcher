"""Patch coordinator.

apply_all(patches) -> backup_dir
    Collects all target file paths, backs them up, then applies each patch in
    order.  On any failure: restores from backup, cleans up the backup dir,
    and re-raises the exception so the caller can report it.

restore_all(backup_dir) -> bool
    Restores all patched files from the backup directory, then cleans it up.
    Returns True if every file was restored successfully.  On partial failure
    each failed file is logged with manual copy instructions; cleanup still
    runs.
"""
from typing import List

from session import backup
from session.patches import launchbox as lb_patch
from session.patches import retroarch as ra_patch


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_paths(patches: List[dict]) -> List[str]:
    """Return an ordered, deduplicated list of all files a patch list will touch."""
    paths: List[str] = []
    seen: set = set()

    def add(p: str) -> None:
        if p and p not in seen:
            seen.add(p)
            paths.append(p)

    for patch in patches:
        t = patch.get("type")
        if t == "retroarch_cfg":
            add(patch["path"])
        elif t == "launchbox_emulator":
            add(patch["path"])
        elif t == "launchbox_settings":
            add(patch["bigbox_path"])
            add(patch["settings_path"])

    return paths


def _apply_patch(patch: dict) -> None:
    t = patch["type"]
    if t == "retroarch_cfg":
        ra_patch.apply(patch["path"], patch["set_values"])
    elif t == "launchbox_emulator":
        lb_patch.apply_emulator(patch["path"], patch["emulators"])
    elif t == "launchbox_settings":
        lb_patch.apply_settings(
            patch["bigbox_path"],
            patch["settings_path"],
            patch.get("monitor_index", 1),
            patch.get("disable_splash_screens", True),
        )
    else:
        raise ValueError(f"Unknown patch type: {t!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_all(patches: List[dict]) -> str:
    """Backup all patch targets and apply all patches in order.

    Returns the backup directory path (caller must eventually call
    restore_all() or pass it to backup.cleanup()).

    On failure: restores all files from the backup, deletes the backup dir,
    and re-raises the original exception.
    """
    paths = _collect_paths(patches)
    backup_dir = backup.backup_files(paths)
    try:
        for patch in patches:
            _apply_patch(patch)
    except Exception:
        backup.restore_files(backup_dir)
        backup.cleanup(backup_dir)
        raise
    return backup_dir


def restore_all(backup_dir: str) -> bool:
    """Restore all patched files from backup and delete the backup directory.

    Returns True only if every file was restored successfully.  Partial
    failures are logged with manual copy instructions; cleanup still runs.
    """
    ok = backup.restore_files(backup_dir)
    backup.cleanup(backup_dir)
    return ok
