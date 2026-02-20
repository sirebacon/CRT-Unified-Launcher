"""Dry-run validation for a session manifest.

Loads the manifest, backs up all patch targets, applies all patches, then
immediately restores from backup.  Production files are left byte-identical to
their state before the script ran.

Use this after editing the manifest or patch profiles to confirm everything
is correct before running a live session.

Usage:
    python validate_session.py --manifest profiles/gaming-manifest.json
    python validate_session.py --manifest profiles/gaming-manifest.json --keep-backup
"""
import argparse
import sys

from session import backup as bk
from session import manifest as m
from session import patcher


def main() -> int:
    p = argparse.ArgumentParser(
        description="Dry-run: validate manifest, apply patches, restore immediately."
    )
    p.add_argument("--manifest", required=True, help="Path to a gaming-manifest.json file.")
    p.add_argument(
        "--keep-backup",
        action="store_true",
        help="Keep the backup directory after restore so you can inspect the patched files.",
    )
    args = p.parse_args()

    # Step 1: load and validate manifest (schema + file-existence checks).
    print(f"[validate] Loading manifest: {args.manifest}")
    try:
        manifest = m.load(args.manifest)
    except ValueError as exc:
        print(exc)
        return 1
    except Exception as exc:
        print(f"[validate] Cannot read manifest: {exc}")
        return 1

    print(
        f"[validate] Manifest OK — {len(manifest.patches)} patch(es), "
        f"{len(manifest.watch)} watch profile(s)."
    )

    # Step 2: back up and apply all patches.
    print("[validate] Backing up patch targets and applying patches...")
    try:
        backup_dir = patcher.apply_all(manifest.patches)
    except Exception as exc:
        # apply_all already restored and cleaned up on failure.
        print(f"[validate] FAILED during patch apply: {exc}")
        return 1

    print(f"[validate] Patches applied. Backup at: {backup_dir}")

    # Step 3: restore immediately.
    print("[validate] Restoring all files to original state...")
    ok = bk.restore_files(backup_dir)

    if args.keep_backup:
        print(f"[validate] Backup kept at: {backup_dir}")
    else:
        bk.cleanup(backup_dir)

    if ok:
        print("[validate] PASS — all files restored to original state.")
        return 0
    else:
        print(
            "[validate] PARTIAL FAILURE — some files could not be restored. "
            "See manual copy instructions above."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
