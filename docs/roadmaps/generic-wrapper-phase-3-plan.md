# Generic Wrapper Phase 3 Plan (Scale Features)

## Objective

Reduce profile duplication and support larger game libraries with reusable building blocks.

## Scope

- Profile inheritance (`base` + override).
- Variable expansion:
  - `%PROJECT_ROOT%`
  - `%GAME_DIR%`
  - `%ROM_PATH%`
- Capability flags:
  - `enforce_rect`
  - `allow_fullscreen`
  - `lock_timeout_strategy`
- Centralized defaults file for wrapper tuning.

## Implementation Sequence

1. Add defaults file support and merge logic.
2. Add inheritance mechanics (single parent first; no deep graph initially).
3. Add variable expansion after merge, before validation.
4. Add capability flags into runtime logic.
5. Update docs with examples of base profiles and game overrides.

## Deliverables

- Base profile pattern for shared settings.
- Cleaner per-game profiles with fewer repeated fields.
- Explicit behavior toggles per game.

## Acceptance Criteria

- Child profile can override base values deterministically.
- Variables expand consistently and safely.
- Capability flags produce expected behavior changes at runtime.
- Defaults apply when profiles omit optional tuning values.

## Risks and Mitigations

- Risk: merge complexity creates hidden behavior.
  - Mitigation: keep merge rules shallow/explicit and documented.
- Risk: variable expansion can mask path errors.
  - Mitigation: show resolved values in `--dry-run` output.
