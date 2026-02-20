# TODO: Generic Wrapper Scaling

## Goal

Make `integrations/launchbox/wrapper/launchbox_generic_wrapper.py` scale cleanly from a few emulators to many per-game LaunchBox entries without turning `crt_config.json` into a monolith.

## Proposed Direction

- Keep `crt_config.json` focused on global/shared settings.
- Move game-specific wrapper config to profile files under:
  - `integrations/launchbox/wrapper/profiles/`

## Priority Roadmap

### Phase 1 (Immediate)

- [ ] Add `--profile-file <path>` support to generic wrapper.
- [ ] Allow wrapper to load launch data from profile:
  - `path`, `dir`
  - optional `x`, `y`, `w`, `h`
  - optional filters (`process_name`, `class_contains`, `title_contains`)
  - optional launch args (`arg_pre`, `set_values`)
- [ ] Keep backward compatibility with current `--config-key` mode.
- [ ] Define precedence rules:
  - CLI args override profile
  - profile overrides shared defaults
- [ ] Add 3 profile files:
  - `re1-gog.json`
  - `re2-gog.json`
  - `re3-gog.json`
- [ ] Add one reusable example/template profile in `profiles/`.
- [ ] Update docs with profile-based LaunchBox examples.

### Phase 2 (Stability)

- [ ] Add profile schema validation with clear errors:
  - required keys
  - key types
  - value ranges (timings, dimensions)
  - file/path existence checks
- [ ] Add `--validate-only` mode (no launch, validation only).
- [ ] Add `--dry-run` mode (print resolved config + command, no launch).
- [ ] Add `profile_version` field and enforce supported versions.
- [ ] Add startup summary log line showing resolved profile + overrides.

### Phase 3 (Scale Features)

- [ ] Add profile inheritance:
  - base profile + per-game override
  - shallow/explicit merge rules documented
- [ ] Add variable expansion support:
  - `%PROJECT_ROOT%`
  - `%GAME_DIR%`
  - `%ROM_PATH%` (if passed through)
- [ ] Add capability flags per profile:
  - `enforce_rect`
  - `allow_fullscreen`
  - `lock_timeout_strategy`
- [ ] Add centralized defaults file for wrapper tuning values.

### Phase 4 (Operations)

- [ ] Add per-game rotating debug logs.
- [ ] Add compact "last launch summary" output file.
- [ ] Add tooling to generate/sync LaunchBox command lines from profiles.
- [ ] Add consistency check to detect LaunchBox drift from profile settings.

## Naming and Conventions

- [ ] Use stable slug IDs for profile names (example: `re1-gog`).
- [ ] Keep filename == profile ID where possible.
- [ ] Prefer lowercase executable names in process filters.
- [ ] Document quoting rules for paths with spaces.

## Testing Checklist

- [ ] Validate profiles with missing keys.
- [ ] Validate invalid paths and type mismatches.
- [ ] Verify CLI-overrides-profile precedence.
- [ ] Verify fallback from profile to shared defaults.
- [ ] Verify behavior when `psutil` is unavailable.
- [ ] Verify stop-flag behavior (`wrapper_stop_enforce.flag`).
- [ ] Verify primary-rect handoff behavior.
- [ ] Verify RE1/RE2/RE3 profile launches from LaunchBox.

## RE1/RE2/RE3 Specific Tasks

- [ ] Create profile: `re1-gog.json` for:
  - `D:\GOG Galaxy\Games\Resident Evil\Biohazard.exe`
- [ ] Create profile: `re2-gog.json` for:
  - `D:\GOG Galaxy\Games\Resident Evil 2\Resident Evil 2.exe`
- [ ] Create profile: `re3-gog.json` for:
  - `D:\GOG Galaxy\Games\Resident Evil 3\bio3 Uncensored.EXE`
- [ ] Document fullscreen strategy:
  - keep enforcement active during startup only
  - disable or shorten lock window if fullscreen mode fights repositioning
- [ ] Tune default lock durations for these titles and record known-good values.

## Definition of Done

- [ ] New profile workflow is documented and tested.
- [ ] Existing wrapper workflows keep working unchanged.
- [ ] Adding a new game requires only:
  - creating one profile file
  - setting LaunchBox to use generic wrapper with that profile
