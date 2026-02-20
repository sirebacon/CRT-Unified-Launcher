# Session Watcher Upgrade Plan: Option 3

Goal: build a data-driven replacement for option 2 in `crt_master.py`, while keeping option 2 intact until option 3 is proven.

Detailed phase plan: `docs/roadmaps/session-watcher-phase-plan.md`

## Current option 2 behavior

Option 2 currently does two things:

1. Config patching (`launchbox_session_mode.py`)
- Backs up and patches:
  - `retroarch.cfg`
  - `Emulators.xml`
  - `BigBoxSettings.xml`
  - `Settings.xml`
- Restores from backup when session ends.

2. Runtime watcher (`launchbox_crt_watcher.py`)
- Polls windows and moves matched targets to CRT bounds.
- Uses hardcoded process logic for emulator and parent-process matching.
- On Ctrl+C, signals wrappers and restores windows.

## Why change

The core issue is not patching itself. The issue is hardcoded emulator/process behavior spread across Python scripts. Adding or tuning emulators requires code edits.

Option 3 should move emulator-specific behavior into data (manifest + profiles), so Python stays generic.

## Target architecture

Primary runtime files:

- `launch_session.py` (orchestrator)
- `session/manifest.py` (load + validate manifest)
- `session/backup.py` (backup/restore files)
- `session/patcher.py` (dispatch patch handlers)
- `session/watcher.py` (multi-profile window loop)
- `session/window_utils.py` (shared Win32 helpers)
- `session/patches/retroarch.py`
- `session/patches/launchbox.py`

Data files:

- `profiles/gaming-manifest.json`
- `profiles/launchbox-session.json`
- `profiles/retroarch-session.json`
- `profiles/dolphin-session.json`
- `profiles/ppsspp-session.json`
- `profiles/pcsx2-session.json`

## Manifest contract (must be versioned)

The manifest must include a required version field:

- `schema_version` (integer)

The loader must reject unknown versions with a clear error.

Example skeleton:

```json
{
  "schema_version": 1,
  "primary": "launchbox-session.json",
  "watch": ["retroarch-session.json"],
  "patches": []
}
```

## Non-negotiable guardrails

1. Fail closed on patch errors:
- If any patch apply step fails, abort and restore everything from backup.

2. Restore failure handling:
- If restore itself fails, continue attempting remaining files.
- Log each failed restore with source/destination paths.
- Print explicit manual recovery instructions.
- See `docs/runbooks/session-restore-recovery.md`.

3. Single-session lock:
- Use a lockfile (for example `runtime/session.lock`) to prevent concurrent option 3 sessions.
- Clear lock in `finally`.

4. Shutdown ordering:
- Move tracked windows to primary first.
- Then write `wrapper_stop_enforce.flag`.

5. Double Ctrl+C handling:
- During cleanup/restore, ignore second interrupt and continue cleanup.

## Decision gates before option 3 retirement

1. Parent-process scope decision (Steam/GOG):
- Either support parent-process fallback in option 3, or explicitly accept this as out-of-scope with documented impact.
- **Decision (Phase 4):** Steam/GOG parent-process fallback is OUT OF SCOPE for option 3 v1. The watcher tracks processes by name from the watch profiles. Games launched through Steam or GOG launchers will not be tracked unless their process name appears in a watch profile. This is an accepted known gap — option 2 must not be retired until this gap is confirmed to not matter in practice or a later version resolves it.

2. Lockfile location:
- **Decision (Phase 4):** Lockfile path is `.session.lock` at the project root (same directory as `crt_master.py` and `launch_session.py`). This makes it easy to locate and delete manually after a hard crash. The file contains the PID of the running session process.

3. LaunchBox-running-at-start behavior:
- Refuse to start if LaunchBox is already running, with clear message.

4. Locked-file behavior:
- Validate writability before applying patches.
- Abort cleanly if any required target file is locked.

## Parity expectations vs option 2

Option 3 must match option 2 in:

- Effective config patch results
- Window movement outcomes
- Cleanup reliability on Ctrl+C and on primary app exit

It may improve:

- Data-driven extensibility
- Logging and diagnostics
- Session lifecycle safety

## Migration policy

- Keep option 2 live until option 3 is validated in real use.
- When retiring option 2, move legacy scripts to `old programs/` first (do not hard delete immediately).
