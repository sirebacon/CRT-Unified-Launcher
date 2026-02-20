# TODO: Generic Wrapper Scaling

Detailed execution plans:

- `docs/roadmaps/generic-wrapper-phase-1-plan.md`
- `docs/roadmaps/generic-wrapper-phase-2-plan.md`
- `docs/roadmaps/generic-wrapper-phase-3-plan.md`
- `docs/roadmaps/generic-wrapper-phase-4-plan.md`

## Goal

Make `integrations/launchbox/wrapper/launchbox_generic_wrapper.py` scale cleanly from a few emulators to many per-game LaunchBox entries without turning `crt_config.json` into a monolith.

## Proposed Direction

- Keep `crt_config.json` focused on global/shared settings.
- Move game-specific wrapper config to profile files under:
  - `integrations/launchbox/wrapper/profiles/`

## Priority Roadmap

### Phase 1 — COMPLETE

- [x] Add `--profile-file <path>` argument with mutual-exclusion group vs `--config-key`.
- [x] Load launch data from profile file (path, dir, rect, filters, launch args).
- [x] Single resolver function with precedence: CLI > profile > crt_config.json defaults.
- [x] Profile files: re1-gog.json, re2-gog.json, re3-gog.json, template.json.
- [x] Docs updated with profile-based LaunchBox examples.
- [x] Stable slug IDs. Filename == profile ID. Lowercase exe names in process filters.
- [ ] Document quoting rules for paths with spaces in generic-wrapper.md.

### Phase 2 — COMPLETE

- [x] `--dry-run` mode: prints resolved config + launch command, exits without launching.
- [x] `--validate-only` mode: validates profile + resolved exe, exits without launching.
- [x] Profile schema validation with clear per-field errors (type, range, required keys,
  path existence, profile_version).
- [x] `profile_version` field enforcement (supported: version 1).
- [x] Startup summary log line showing resolved mode, slug, exe, rect, position_only.

### Phase 3 — COMPLETE

- [x] Profile inheritance: `"base": "other.json"` — single-level shallow merge.
- [x] Variable expansion: `%PROJECT_ROOT%` and `%GAME_DIR%` in string and list values.
  - `%ROM_PATH%` not implemented — ROM path arrives as a passthrough arg, not a named
    value at profile-load time. Needs a design decision before implementing.
- [x] `position_only` flag: only enforce x,y position; do not fight window size.
  (Originally planned as `enforce_rect`. Scope adjusted based on RE1/RE2/RE3 testing.)
- [x] Centralized defaults file: `profiles/defaults.json` for shared timing values.
  Precedence: CLI > profile > defaults.json > crt_config.json > hardcoded defaults.

### Phase 4 — COMPLETE

- [x] Per-slug rotating debug logs: rotates at 1 MB, keeps 3 copies.
- [x] Last-launch summary: `runtime/last_launch_summary.json` written on every exit.
- [x] `scripts/generate_lb_commands.py`: generates LaunchBox command lines from profiles.
- [x] `scripts/check_launchbox_drift.py`: detects drift between profiles and LaunchBox
  emulator config. Best-effort, non-fatal warnings only.

## Testing Checklist

- [ ] Validate profiles with missing required keys.
- [ ] Validate invalid paths and type mismatches.
- [ ] Verify CLI-overrides-profile precedence.
- [ ] Verify fallback from profile to shared defaults.
- [ ] Verify behavior when `psutil` is unavailable.
- [ ] Verify stop-flag behavior (`wrapper_stop_enforce.flag`).
- [ ] Verify primary-rect handoff behavior.
- [ ] Verify RE1/RE2/RE3 profile launches from LaunchBox. (Blocked — see CRT display issue below.)

## RE1/RE2/RE3 Specific Tasks

- [x] Create profile: `re1-gog.json` — `D:\GOG Galaxy\Games\Resident Evil\Biohazard.exe`
- [x] Create profile: `re2-gog.json` — `D:\GOG Galaxy\Games\Resident Evil 2\Resident Evil 2.exe`
- [x] Create profile: `re3-gog.json` — `D:\GOG Galaxy\Games\Resident Evil 3\bio3 Uncensored.EXE`

### Known window title sequence

RE1: `CONFIGURATION` → `MOD SELECTION` → `RESIDENT EVIL ® PC`
RE2: `CONFIGURATION` → `RESIDENT EVIL 2 ® PC`
RE3: `CONFIGURATION` → `RESIDENT EVIL ™ 3 NEMISIS PC`

See `_window_sequence` in each profile file.

### CRT display blocker (on hold)

RE1 live-tested. Config and mod selection menus snap to CRT correctly. Game window
does not render on CRT — root cause is DirectDraw exclusive fullscreen, which always
renders to the Windows primary display regardless of window position. `SetWindowPos`
cannot redirect a DirectDraw render surface.

See `docs/runbooks/re-gog-crt-display.md` for full investigation notes.

- [ ] Check RE1/RE2/RE3 CONFIGURATION menus for a windowed mode toggle.
- [ ] Check game directories for INI/CFG files with display or adapter settings.
- [ ] Evaluate making the CRT the Windows primary display as a session-level workaround.
- [ ] Tune `max_lock_seconds` / `fast_seconds` per title once display issue is resolved.

## Definition of Done

- [x] New profile workflow is documented and tested.
- [x] Existing `--config-key` workflows keep working unchanged.
- [ ] Adding a new game requires only:
  - creating one profile file
  - setting LaunchBox to use the generic wrapper with that profile
