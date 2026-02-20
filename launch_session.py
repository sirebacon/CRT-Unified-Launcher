"""Session orchestrator — option 3 implementation.

Loads a session manifest, applies config patches, launches the primary app
(LaunchBox), runs the multi-target window watcher, then restores all configs
when the session ends.

Usage:
    python launch_session.py --manifest profiles/gaming-manifest.json
    python launch_session.py --manifest profiles/gaming-manifest.json --debug
"""
import argparse
import json
import os
import subprocess
import sys
import time
from typing import List, Optional, Tuple

try:
    import psutil
except ImportError:
    psutil = None

from session import manifest as mf
from session import patcher
from session import watcher

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
LOCKFILE = os.path.join(PROJECT_ROOT, ".session.lock")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Session orchestrator. Patches configs, locks windows, "
                    "restores everything on exit."
    )
    p.add_argument("--manifest", required=True, help="Path to a gaming-manifest.json.")
    p.add_argument("--debug", action="store_true", help="Pass debug flag to watcher.")
    return p.parse_args()


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _check_locked_files(paths: List[str]) -> List[str]:
    """Return any paths that cannot be opened for writing right now."""
    locked = []
    for path in paths:
        try:
            with open(path, "a"):
                pass
        except OSError:
            locked.append(path)
    return locked


def _is_running(process_names: List[str]) -> bool:
    """Return True if any process matching a name in process_names is alive."""
    if psutil is None:
        return False
    target = {n.lower() for n in process_names}
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"].lower() in target:
                return True
        except Exception:
            pass
    return False


def _restore_rect(cfg: dict) -> Tuple[int, int, int, int]:
    p = cfg.get("launcher_integration", {}).get(
        "primary_on_exit", {"x": 100, "y": 100, "w": 1280, "h": 720}
    )
    return int(p["x"]), int(p["y"]), int(p["w"]), int(p["h"])


def _collect_patch_paths(patches: List[dict]) -> List[str]:
    """Same path-collection logic as patcher._collect_paths — used for pre-checks."""
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # --- Lockfile guard ---
    if os.path.exists(LOCKFILE):
        print(f"[session] A session is already running.")
        print(f"[session] Lock file: {LOCKFILE}")
        print("[session] If no session is running, delete the lock file manually.")
        return 1

    # --- Load config and manifest ---
    try:
        cfg = _load_config()
    except Exception as exc:
        print(f"[session] Cannot read crt_config.json: {exc}")
        return 1

    print(f"[session] Loading manifest: {args.manifest}")
    try:
        manifest = mf.load(args.manifest)
    except ValueError as exc:
        print(exc)
        return 1
    except Exception as exc:
        print(f"[session] Cannot read manifest: {exc}")
        return 1

    print(
        f"[session] Manifest OK — {len(manifest.patches)} patch(es), "
        f"{len(manifest.watch)} watch profile(s)."
    )

    # --- Load primary profile ---
    try:
        with open(manifest.primary.profile, "r", encoding="utf-8-sig") as f:
            primary_profile = json.load(f)
    except Exception as exc:
        print(f"[session] Cannot read primary profile: {exc}")
        return 1

    exe = primary_profile.get("path", "")
    cwd = primary_profile.get("dir", os.path.dirname(exe) if exe else "")
    primary_process_names: List[str] = primary_profile.get("process_name", [])

    # --- Pre-flight checks ---
    if not exe or not os.path.exists(exe):
        print(f"[session] Primary executable not found: {exe}")
        return 1

    if _is_running(primary_process_names):
        print(f"[session] Primary is already running: {primary_process_names}")
        print("[session] Close it before starting a session.")
        return 1

    patch_paths = _collect_patch_paths(manifest.patches)
    locked = _check_locked_files(patch_paths)
    if locked:
        print("[session] The following patch files are locked by another process:")
        for p in locked:
            print(f"  - {p}")
        print("[session] Close any program using these files and try again.")
        return 1

    # --- Write lockfile ---
    try:
        with open(LOCKFILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as exc:
        print(f"[session] Cannot write lockfile: {exc}")
        return 1

    backup_dir: Optional[str] = None
    proc: Optional[subprocess.Popen] = None

    try:
        # --- Apply patches ---
        print("[session] Applying patches...")
        try:
            backup_dir = patcher.apply_all(manifest.patches)
        except Exception as exc:
            print(f"[session] Patch failed — no files were changed: {exc}")
            return 1

        print("[session] Patches applied.")

        # --- Launch primary ---
        print(f"[session] Launching primary: {exe}")
        proc = subprocess.Popen([exe], cwd=cwd if cwd else None)
        print(f"[session] Primary PID: {proc.pid}")

        # --- Run watcher ---
        restore_rect = _restore_rect(cfg)
        poll_seconds = float(
            cfg.get("launcher_integration", {}).get("poll_seconds", 0.5)
        )
        watch_paths = [entry.profile for entry in manifest.watch]

        watcher.run(
            proc=proc,
            primary_profile_path=manifest.primary.profile,
            watch_profile_paths=watch_paths,
            restore_rect=restore_rect,
            poll_seconds=poll_seconds,
            debug=args.debug,
        )

    finally:
        # --- Restore patches ---
        if backup_dir is not None:
            print("[session] Restoring configs...")
            ok = patcher.restore_all(backup_dir)
            if ok:
                print("[session] Configs restored.")
            else:
                print("[session] WARNING: some configs could not be restored automatically.")
                print("[session] See manual copy instructions above.")

        # --- Remove lockfile ---
        try:
            os.remove(LOCKFILE)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
