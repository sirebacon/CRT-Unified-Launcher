# YouTube Transition Auto-Reapply Safety Review

## Context
We confirmed from logs that window reapply can report success and then drift shortly after playlist transitions (late mpv-driven resize).

Current evidence appears in `runtime/youtube.log` lines like:
- `transition: reapply window ok ...`
- followed by `transition-watch: late drift detected ...`

## Goal
Add automatic corrective reapply during transition watch windows without breaking manual controls or causing window-fight loops.

## Findings (Code Review)

### 1. High Risk: Auto-correct can fight Adjust mode
- Location: `youtube/launcher.py` transition-watch block.
- If we issue corrective `move_window()` while user is in Adjust mode, user movement can be overridden.
- Requirement: disable correction when `adjust_mode == True`.

### 2. High Risk: Stale/invalid HWND
- Current flow keeps one `hwnd` captured near startup.
- During long sessions, window handle can become invalid/recreated by player/runtime behavior.
- Requirement: validate handle before correction and reacquire by PID when invalid.

### 3. Medium Risk: Window-fight loop with mpv
- If mpv keeps resizing during transition, naive correction every watch tick can thrash.
- Requirement: bounded correction budget + cooldown between attempts.

### 4. Medium Risk: No transition-level final verdict
- Current logs provide per-sample details but no final summary for each transition watch.
- Requirement: log one terminal summary at watch end (settled/failed, attempts, final rect).

### 5. Low Risk: Log readability issue
- Some title logs show encoding artifact (`→`).
- Requirement: standardize ASCII-friendly logging for easier triage.

## Safety Constraints (Must-Haves)

1. Corrective reapply only during active transition watch window.
2. Never correct while in Adjust mode.
3. Validate/reacquire HWND before correction.
4. Use retry budget (example: max 6 corrections/watch).
5. Use cooldown (example: >= 350 ms between corrections).
6. Stop watch early after stable rect observed repeatedly (example: 2-3 consecutive stable checks).
7. Emit one end-of-watch summary log line.

## Proposed Implementation Design

### Transition Watch State
Track per-transition state:
- `watch_active`
- `watch_until`
- `target_rect`
- `attempts_used`
- `max_attempts`
- `last_correct_at`
- `stable_hits`
- `required_stable_hits`

### Drift Handling
When drift is detected during watch:
- If in Adjust mode: log skip reason and do not correct.
- Else if attempt budget exhausted: log exhausted and continue watch (no correction).
- Else if cooldown elapsed:
  - validate/reacquire HWND
  - call `move_window(..., strip_caption=True)`
  - increment attempts
  - log correction attempt

### HWND Reacquire Method (Explicit)
If existing `hwnd` is invalid during correction:
1. Check validity first (`IsWindow(hwnd)` or equivalent).
2. If invalid, attempt reacquire using mpv PID via `find_window(pid, [], [])`.
3. Optional fallback: short `wait_for_window(pid, timeout=1.0)` if immediate lookup fails.
4. If still unavailable:
   - skip corrective move for that tick
   - log `hwnd_unavailable`
   - continue watch until timeout/budget end.

### Watch Completion
On watch end (timeout or early stability):
- log summary:
  - `result=settled` or `result=failed`
  - `attempts_used`
  - `final_rect`
  - `target_rect`

Canonical summary log format:
- `transition-watch-end result=settled attempts=2 stable_hits=2 target=(x=...,y=...,w=...,h=...) final=(x=...,y=...,w=...,h=...) reason=stable_hits`
- `transition-watch-end result=failed attempts=6 stable_hits=0 target=(x=...,y=...,w=...,h=...) final=(x=...,y=...,w=...,h=...) reason=budget_exhausted`

## Acceptance Criteria

1. No corrective move is performed during Adjust mode.
2. For induced drift scenarios, corrective moves occur and settle to target rect within watch limits.
3. No infinite correction loops (attempt cap enforced).
4. Logs clearly show transition lifecycle:
   - detect -> initial reapply -> watch -> correction attempts (if any) -> final verdict.

## Rollout Plan

1. Implement guarded auto-correct in transition-watch block.
2. Keep detailed logs enabled for at least one test cycle.
3. Validate with playlist skip + natural end transitions.
4. If stable, optionally reduce log verbosity from INFO/WARN to DEBUG for high-frequency lines.

## Open Questions for Review

Resolved defaults for implementation:
1. `youtube_transition_max_attempts=6`
2. `youtube_transition_watch_sec=3.0`
3. Correction is disabled during manual actions that take control (`A`, and watch reset on `R`/`U`).
4. Keep config flag support enabled for rapid rollback/tuning.

## Failure Behavior Policy (Required)

When transition watch ends with `result=failed`, behavior must be explicit and predictable.

Recommended default policy:
1. Do not force additional hidden corrections beyond retry budget.
2. Emit one clear warning log with final rect mismatch.
3. Keep playback running normally (no forced quit/pause).
4. Show a short on-screen hint once (optional) advising `R` to re-snap.

Alternative policy (optional config):
- `force_final_snap_on_watch_fail=true`:
  - perform one final forced `move_window()` at watch end.
  - still log final outcome after the forced snap check.

## Interaction Priority Rules

Define what happens if user interacts while watch is active:

1. `A` (Adjust mode):
   - Immediately suspend/cancel active transition watch.
   - Never auto-correct while in Adjust mode.

2. `R` (Snap to preset CRT area):
   - Cancel active watch.
   - Apply new target immediately.
   - Start a fresh watch against the new target.

3. `U` (Unsnap to profile area):
   - Cancel active watch.
   - Apply profile target immediately.
   - Start a fresh watch against the profile target.

4. Any other key:
   - Does not cancel watch by default.

## Runtime Config Toggles (Safe Rollout)

Add these keys to `crt_config.json` (or YouTube provider config section):

- `youtube_transition_autocorrect_enabled` (bool, default `true`)
- `youtube_transition_watch_sec` (float, default `3.0`)
- `youtube_transition_max_attempts` (int, default `6`)
- `youtube_transition_cooldown_ms` (int, default `350`)
- `youtube_transition_required_stable_hits` (int, default `2`)
- `force_final_snap_on_watch_fail` (bool, default `false`)

Purpose:
- Enable quick disable/tuning without code edits.
- Support safe rollback if a specific environment behaves differently.

Default values for first rollout:
- `youtube_transition_autocorrect_enabled=true`
- `youtube_transition_watch_sec=3.0`
- `youtube_transition_max_attempts=6`
- `youtube_transition_cooldown_ms=350`
- `youtube_transition_required_stable_hits=2`
- `force_final_snap_on_watch_fail=false`

## Minimal Test Matrix

Before enabling broadly, run this matrix and capture logs:

1. Natural transition:
   - let playlist advance without keypress.
   - verify watch settles and final verdict is `settled`.

2. Manual skip stress:
   - press next/previous repeatedly.
   - ensure no infinite correction loops; attempt cap respected.

3. Hidden controls path:
   - let controls auto-hide, then transition.
   - verify corrections still run and top status remains usable.

4. Adjust interaction:
   - enter Adjust mode near transition time.
   - verify auto-correct is suspended and no user-fight occurs.

5. Last-item/near-end behavior:
   - test final playlist transitions.
   - verify watch end summary is emitted even near session stop.
