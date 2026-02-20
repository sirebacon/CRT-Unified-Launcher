# Generic Wrapper Phase 2 Plan (Stability)

## Objective

Make profile execution safe and predictable through validation and non-launch test modes.

## Scope

- Schema validation for profile files.
- `--validate-only` mode.
- `--dry-run` mode.
- `profile_version` support.
- Startup summary output for resolved config.

## Implementation Sequence

1. Define profile schema (required keys, types, optional keys, version).
2. Implement validation layer with actionable error messages.
3. Add `--validate-only` command path.
4. Add `--dry-run` command path (show resolved launch command/config).
5. Add `profile_version` check and compatibility handling.
6. Add launch summary logging for normal runs.

## Deliverables

- Reliable validation with clear failures before launch.
- Two safe non-launch execution modes for debugging and CI checks.
- Versioned profile contract.

## Acceptance Criteria

- Invalid profiles fail fast with precise reasons.
- `--validate-only` exits without starting emulator.
- `--dry-run` prints resolved command and exits.
- Version mismatches produce explicit guidance.

## Risks and Mitigations

- Risk: over-strict validation blocks real-world configs.
  - Mitigation: allow optional keys and warn vs fail where appropriate.
- Risk: drift between schema and docs.
  - Mitigation: keep a single canonical schema section and reference it in docs.
