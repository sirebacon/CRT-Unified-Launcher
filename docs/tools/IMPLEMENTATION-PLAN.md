# Tools Framework Implementation Plan

Date: 2026-02-22

## Purpose

Prioritized implementation plan for the proposed `crt_tools.py` diagnostics/recovery framework documented in `docs/tools/`.

This plan assumes:

- Resident Evil **manual mode** is the supported workflow
- RE auto mode is on hold
- We want maximum value early with minimal risk

---

## Guiding Principles

1. Build read-only diagnostics first.
2. Reuse `session/*` functions directly (thin wrappers).
3. Keep `crt_tools.py` independent from session orchestration.
4. Add mutating commands only after verification/readback tools exist.
5. Prioritize tools useful for the current manual RE workflow.

---

## Phase 0 - Docs Hygiene (P0)

Goal: make `docs/tools/` accurate enough to implement from without surprises.

Tasks:

1. Normalize encoding / remove mojibake in `docs/tools/*.md`.
2. Add a top-level note in `docs/tools/README.md` that the framework is **proposed** (not implemented yet).
3. Fix accuracy mismatches:
   - `docs/tools/config.md` wrapper profile validation assumptions (current RE profiles differ from old wrapper schema examples)
   - `docs/tools/session.md` wording about saved audio state (RE state file currently stores display state only)
4. Mark commands by mode relevance more clearly:
   - `Manual`
   - `Auto`
   - `Both`

Deliverable:

- `docs/tools/` becomes implementation-ready and aligned with current manual-mode direction.

---

## Phase 1 - Foundation + Highest-Value Diagnostics (P1)

Goal: create a usable `crt_tools.py` CLI with the most valuable read-only commands.

### 1. CLI Scaffold

Files:

- `crt_tools.py`
- `tools/__init__.py`
- `tools/cli.py`

Requirements:

- `python crt_tools.py --help`
- `python crt_tools.py <category> --help`
- unified error format (`[tools] FAIL: ...`)
- no side effects on import

### 2. Display Diagnostics (Start with `display dump`)

File:

- `tools/display.py`

Implement first:

- `display dump`

Data sources:

- `session/display_api.py`

Minimum output:

- attached displays
- current primary
- positions
- current mode (`w/h/hz`)
- token resolution summary (RE / restore / CRT)

Stretch (optional in Phase 1):

- rational refresh via `QueryDisplayConfig`

### 3. Prereqs Check

File:

- `tools/prereqs.py`

Implement:

- `prereqs`

Checks:

- `pywin32`
- `psutil`
- audio backend availability
- Moonlight paths
- Apollo process presence (best effort)
- VDD attached (warn if not attached but Apollo running)
- config file readability
- RE profile paths exist

### 4. Config Diagnostics

File:

- `tools/config.py`

Implement:

- `config dump`
- `config check`

Minimum `config dump`:

- paths
- Moonlight rects
- display tokens
- audio tokens
- timing values
- RE profile paths

Minimum `config check`:

- path existence
- display token resolution
- required display groups resolve
- audio backend available
- profile files exist + parse

Deliverable (Phase 1):

- `python crt_tools.py display dump`
- `python crt_tools.py prereqs`
- `python crt_tools.py config dump`
- `python crt_tools.py config check`

---

## Phase 2 - Manual-Mode Support Tools (P1)

Goal: add tools most useful during current RE manual-mode sessions.

### Window Tools

File:

- `tools/windows.py`

Implement:

- `window list`
- `window move`

Why:

- immediate debugging/recovery for Moonlight + RE folder window placement

### Audio Tools

File:

- `tools/audio.py`

Implement:

- `audio status`
- `audio set`
- `audio restore`

Why:

- manual mode switches audio and needs easy recovery

### Session Log

File:

- `tools/session.py`

Implement:

- `session log`

Why:

- useful in manual and auto contexts
- easy to implement

Deliverable (Phase 2):

- `window list`, `window move`
- `audio status`, `audio set`, `audio restore`
- `session log`

---

## Phase 3 - Calibration Migration (P2)

Goal: move Moonlight calibration utilities into the tools framework without breaking existing aliases.

File:

- `tools/calibration.py`

Implement:

- `calibrate adjust`
- `calibrate set-crt`
- `calibrate set-idle`
- `calibrate overlap`

Later in phase:

- `calibrate set-crt-offsets` (relative calibration)

Notes:

- Keep `launch_resident_evil_stack.py adjust-moonlight/set-crt-pos/set-idle-pos` working as compatibility commands.
- Prefer delegating to the new tool implementations once stable.

---

## Phase 4 - Recovery Commands (P2)

Goal: independent recovery commands for display/window/audio without running full RE restore.

Implement:

- `display restore`
- `window restore`
- `audio restore` (if not already done in Phase 2)
- `session processes`
- `session flag`

Why later:

- Tools submenu and existing restore commands already cover basic recovery
- Lower urgency than diagnostics/calibration

---

## Phase 5 - Advanced / Auto-Mode-Oriented Diagnostics (P3)

Goal: deeper diagnostics and legacy-auto-mode support if needed later.

Implement:

- `display modes`
- `display vdd`
- `display token`
- `session state`
- `window watch`
- `processes` expansions / Apollo diagnostics
- rational refresh in `display dump` (if deferred earlier)

These are valuable, but less urgent for the current manual-mode-first workflow.

---

## Suggested Exact Build Order

1. `crt_tools.py`
2. `tools/__init__.py`
3. `tools/cli.py`
4. `tools/display.py` (`dump`)
5. `tools/prereqs.py`
6. `tools/config.py` (`dump`, `check`)
7. `tools/windows.py` (`list`, `move`)
8. `tools/audio.py` (`status`, `set`, `restore`)
9. `tools/session.py` (`log`)
10. `tools/calibration.py` (`adjust`, `set-crt`, `set-idle`)
11. `tools/calibration.py` (`overlap`)
12. Recovery + advanced tools

---

## Success Criteria

This framework is successful when:

1. Most RE manual-mode troubleshooting can be done without editing code.
2. `launch_resident_evil_stack.py inspect` is no longer the primary diagnostic command.
3. Adding a new diagnostic command is a small, isolated change in one `tools/*.py` module.
4. The CLI remains consistent (`python crt_tools.py <category> <subcommand>`).

