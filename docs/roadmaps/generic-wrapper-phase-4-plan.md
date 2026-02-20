# Generic Wrapper Phase 4 Plan (Operations)

## Objective

Operationalize the system for long-term maintenance, troubleshooting, and LaunchBox consistency.

## Scope

- Per-game rotating debug logs.
- Compact last-launch summary artifact.
- Tooling to generate/sync LaunchBox command lines from profiles.
- Drift check between LaunchBox emulator config and wrapper profile definitions.

## Implementation Sequence

1. Add structured logging with per-game log file naming and rotation policy.
2. Add `last_launch_summary.json` (or similar) with resolved inputs/results.
3. Build a sync tool that emits LaunchBox wrapper command lines from profile files.
4. Build a verification tool to detect mismatches (drift) in LaunchBox config.
5. Add operator docs for routine usage and troubleshooting.

## Deliverables

- Better observability for startup and window-lock issues.
- Faster recovery/debug through summarized last run data.
- Repeatable LaunchBox integration changes without manual drift.

## Acceptance Criteria

- Logs rotate and do not grow unbounded.
- Last-launch summary is written on success/failure.
- Sync tool can generate expected LaunchBox command lines for known profiles.
- Drift checker reports actionable mismatches.

## Risks and Mitigations

- Risk: tooling depends on local LaunchBox XML structure differences.
  - Mitigation: make parser tolerant and surface non-fatal warnings.
- Risk: operational artifacts clutter repo.
  - Mitigation: output artifacts to a dedicated runtime folder and ignore in Git.
