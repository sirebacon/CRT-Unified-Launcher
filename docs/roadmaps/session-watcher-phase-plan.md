# Session Watcher Phase Plan

Detailed execution plan for `docs/roadmaps/session-watcher-upgrade-plan.md`.

Option 2 remains active throughout this plan.

## Phase 1: Foundation

Objective:
- Create shared window/file infrastructure without behavior changes.

Scope:
- Add `session/` package.
- Extract shared Win32 helpers into `session/window_utils.py`.
- Update `launch_generic.py` to import from `session/window_utils.py`.
- Add `session/backup.py` for generic backup/restore.

Deliverables:
- `session/__init__.py`
- `session/window_utils.py`
- `session/backup.py`
- Updated `launch_generic.py`

Acceptance:
- `launch_generic.py` behavior unchanged.
- Backup/restore works for arbitrary file sets.

## Phase 2: Schema and patch engine

Objective:
- Lock the manifest contract first, then build patch handlers against that contract.

Scope:
- Add `schema_version` contract.
- Build `session/manifest.py` validation and load.
- Build patch handlers:
  - `session/patches/retroarch.py`
  - `session/patches/launchbox.py`
- Build `session/patcher.py` dispatcher.
- Include option 2 XML fields in patch schema:
  - `UseStartupScreen`
  - `StartupLoadDelay`
  - `HideMouseCursorInGame`

Deliverables:
- `session/manifest.py`
- `session/patcher.py`
- `session/patches/__init__.py`
- `session/patches/retroarch.py`
- `session/patches/launchbox.py`

Acceptance:
- Unknown manifest version is rejected clearly.
- Missing files/fields are reported in one pass.
- Apply failure aborts and restores.
- Restore failure logs each failed file and prints manual steps.

## Phase 3: Profiles and dry-run validation

Objective:
- Prepare profile data and prove patch parity safely before runtime wiring.

Scope:
- Create:
  - `profiles/dolphin-session.json`
  - `profiles/ppsspp-session.json`
  - `profiles/pcsx2-session.json`
  - `profiles/gaming-manifest.json`
- Add validation command (or dry-run mode) that performs:
  - manifest load
  - backup
  - patch apply
  - restore
  - no persistent changes

Deliverables:
- New profiles and manifest
- `validate_session.py` or equivalent dry-run path

Acceptance:
- Dry-run passes against production files.
- Files are byte-identical before/after dry-run.
- Patch output matches option 2 behavior.

## Phase 4: Watcher and orchestrator

Objective:
- Make option 3 runnable end-to-end.

Decision gates before coding:
1. Decide Steam/GOG parent-process support for v1.
2. Confirm lockfile path and stale-lock handling policy.

Scope:
- Build `session/watcher.py`.
- Build `launch_session.py`.
- Add lockfile guard to block concurrent option 3 sessions.
- Wire option 3 in `crt_master.py`.

Required runtime behavior:
- Detect primary app exit and run same cleanup path as Ctrl+C.
- Cleanup order:
  - move windows to primary
  - write `wrapper_stop_enforce.flag`
  - restore configs
- Ignore second Ctrl+C during cleanup.

Deliverables:
- `session/watcher.py`
- `launch_session.py`
- Updated `crt_master.py` option 3

Acceptance:
- Option 3 works for LaunchBox + RetroArch + Dolphin + PPSSPP + PCSX2.
- Locked-file precheck failure aborts cleanly.
- Lockfile always removed in `finally`.

## Phase 5: Migration and retirement

Objective:
- Validate option 3 in real workflows, then retire option 2 safely.

Scope:
- Side-by-side comparison runs.
- Edge-case verification.
- Remove option 2 from active menu.
- Move legacy scripts to `old programs/` instead of deleting.

Deliverables:
- Option 2 removed from active path.
- Legacy watcher/session scripts archived.
- Upgrade docs marked complete.

Acceptance:
- Option 3 parity confirmed (or gaps explicitly accepted).
- Parent-process decision resolved/documented.
- No active references to option 2 code paths.
