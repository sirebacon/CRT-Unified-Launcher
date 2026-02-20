# Generic Wrapper Phase 1 Plan (Immediate)

## Objective

Introduce profile-based configuration without breaking current `--config-key` workflows.

## Scope

- Add `--profile-file <path>` support.
- Load game-specific launch data from profile files.
- Define and implement precedence:
  - CLI overrides profile
  - profile overrides shared defaults
- Add RE1/RE2/RE3 profiles and one reusable template.
- Update docs and examples for LaunchBox usage.

## Implementation Sequence

1. Add profile model and loader in `launchbox_generic_wrapper.py`.
2. Add argument parsing for `--profile-file`.
3. Build resolved config object using precedence rules.
4. Keep existing `--config-key` flow as fallback/compat mode.
5. Create profile directory and files:
   - `integrations/launchbox/wrapper/profiles/re1-gog.json`
   - `integrations/launchbox/wrapper/profiles/re2-gog.json`
   - `integrations/launchbox/wrapper/profiles/re3-gog.json`
   - `integrations/launchbox/wrapper/profiles/template.json`
6. Add docs with command-line examples and migration notes.

## Deliverables

- `--profile-file` works end-to-end.
- Existing wrapper commands continue working unchanged.
- RE1/RE2/RE3 launch from profile files.
- Documentation reflects profile-first usage.

## Acceptance Criteria

- Wrapper launches correctly using profile only.
- CLI options can override profile values.
- `--config-key` mode remains functional.
- No regressions in current emulator wrappers.

## Risks and Mitigations

- Risk: ambiguous precedence.
  - Mitigation: codify precedence in one resolver function and document it.
- Risk: path quoting issues for spaced paths.
  - Mitigation: explicit docs and tests for quoted paths.
