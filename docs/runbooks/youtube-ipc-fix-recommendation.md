# YouTube IPC Fix Recommendation

## Summary

Current behavior is split:

- Write controls work (`pause`, `seek`, `volume`, `mute`, `set_property`)
- mpv-owned property reads do not work (`time-pos`, `playlist-pos`, `playlist-count`)

## Definition Of Done (Signoff)

The IPC fix is considered done when all items below are true:

- No deadlock/input freeze during rapid control use.
- `get_property("time-pos")` is non-`None` during normal playback.
- `get_property("playlist-pos")` and `get_property("playlist-count")` are non-`None`
  during playlist playback.
- Bookmark save/jump and session resume position work end-to-end.
- Rollback path (`youtube_ipc_duplex=false`) restores legacy behavior immediately.
- Logs clearly show timeout/failure class without spamming.

## Current Feature Status

- Feature: playlist index display
  - Before: broken
  - Current: still `None` (mpv-owned read path)

- Feature: bookmark time / session resume position
  - Before: broken
  - Current: still `None` (mpv-owned read path)

The root issue is IPC design on Windows named pipes:

- Write-only mode avoids deadlock but cannot read mpv-owned properties
- Background reader + synchronous handle can deadlock when read/write overlap

## Current Architecture Assessment

Overall architecture is mostly correct for this feature set.

What is already good:
- The YouTube code is modularized well (`youtube/launcher.py`, `youtube/adjust.py`,
  `youtube/controls.py`, `youtube/state.py`, etc.).
- Main loop behavior is stable and responsive for write-only controls.
- UI/menu flow does not need a redesign to support the IPC fix.

What is mismatched:
- `session/mpv_ipc.py` currently exposes `get_property()` as a cache lookup based on
  values written by `set_property()`.
- `youtube/launcher.py` uses `get_property()` for mpv-owned runtime values:
  - playlist index display (`playlist-pos`, `playlist-count`)
  - bookmark time (`time-pos`)
  - session save/resume position (`time-pos`, `playlist-pos`)

Conclusion:
- The architecture is correct to implement reliable property reads.
- The blocking issue is the IPC transport layer, not the higher-level YouTube design.

## Recommended Design

Use a **single duplex named-pipe handle** and **serialized request/response I/O**.

### Key rules

1. Open one handle with `GENERIC_READ | GENERIC_WRITE`
2. No background reader thread
3. Guard all pipe I/O with one lock
4. Use `request_id` on every IPC request
5. Write command, then read responses until matching `request_id`

This avoids concurrent `ReadFile`/`WriteFile` deadlocks and still supports real property reads.

## Why This Is Better

- Restores `get_property("time-pos")` for bookmarks/resume
- Restores `get_property("playlist-pos"/"playlist-count")` for playlist index display
- Keeps command reliability by avoiding multi-threaded pipe contention
- Does not require changing the user workflow

## Scope Boundary

This fix should stay scoped to IPC internals plus small timeout/fallback handling in
YouTube call sites. Avoid refactoring menu/UX modules while doing this.

## Module Boundary Contract

To keep the change modular and low-risk, enforce these boundaries:

1. `session/mpv_ipc.py` (transport/protocol only)
- Owns named-pipe connection, request IDs, read/write serialization, timeouts.
- Exposes a small stable API:
  - `connect()`, `close()`
  - command methods (`seek`, `toggle_pause`, `set_property`, etc.)
  - `get_property(name)`
- No YouTube menu/UI logic.

2. `youtube/launcher.py` (orchestration only)
- Uses `MpvIpc` API only; does not implement pipe/protocol internals.
- Keeps fallback behavior when property reads fail (`None`).
- No low-level pipe handling code.

3. `youtube/adjust.py` (feature behavior only)
- Uses `get_property()` for zoom preset save.
- No direct protocol parsing or pipe state management.

4. `youtube/controls.py` (presentation only)
- No IPC calls.
- Renders current state passed from launcher.

5. `youtube/config.py` (feature-flag/config only)
- Owns IPC mode flag configuration if rollout is gated.
- No transport implementation.

### Review Gate

Reject changes that:
- add named-pipe protocol details outside `session/mpv_ipc.py`
- add UI/menu responsibilities inside `session/mpv_ipc.py`
- duplicate fallback logic across multiple YouTube modules

## Concerns And Risk Points

Even though the design is straightforward, this change can break currently stable
controls if implemented carelessly.

Primary risks:

1. Input freeze risk
- Blocking IPC reads in the main control loop can stall key handling.
- This is the biggest user-visible failure mode.

2. Request/response mismatch
- If `request_id` handling is incorrect, a response can be matched to the wrong request.
- This causes confusing behavior (wrong values, intermittent failures).

3. Pipe state/reconnect edge cases
- Pipe resets or mpv startup timing can leave stale handle state.
- Commands may fail or appear delayed if reconnect logic is weak.

4. Regression of write controls
- Pause/seek/volume currently work reliably in write-only mode.
- IPC refactor must not regress these controls.

5. Timeout tuning
- Timeouts that are too long feel frozen.
- Timeouts that are too short can make property reads appear flaky.

6. Error handling clarity
- Silent IPC failures make diagnosis difficult.
- Logging must clearly distinguish command-send failure vs property-read timeout.

## Mitigations

1. Strict short read timeout defaults
- Keep property reads bounded (example: 100–250ms per request path in loop contexts).

2. Single I/O lock
- Serialize all pipe read/write operations to prevent concurrent pipe operations.

3. Non-fatal fallbacks
- On read failure, return `None` and continue.
- Keep playback controls responsive even when property reads fail.

4. Keep command path simple
- Preserve existing command wrappers; route through the same request function.

5. Incremental rollout with feature flag
- Add config flag (example: `youtube_ipc_duplex=true`).
- If issues appear, disable flag and return to write-only behavior immediately.

6. Focused logging
- Log request type, timeout, and failure class.
- Avoid noisy logs but keep enough detail for root-cause analysis.

## Recommended Rollout Plan

1. Implement duplex IPC transport behind a feature flag.
2. Enable only for `get_property` first; keep command methods on stable path.
3. Validate playlist index + bookmark/session readback in real runs.
4. Migrate command methods to the same transport once readback is stable.
5. Remove legacy path after multiple stable sessions.

## Deadlock Fix Plan (Explicit)

### Objective

Eliminate Windows named-pipe deadlocks while restoring reliable mpv property reads.

### Design

1. One duplex handle, no background reader
- Open mpv IPC once with `GENERIC_READ | GENERIC_WRITE`.
- Remove background `ReadFile` thread entirely.
- Avoid concurrent read/write on the same synchronous handle.

2. Single I/O lock
- Add one lock in `MpvIpc`.
- Every IPC call (`command`, `get_property`) acquires the same lock.
- Inside lock: write request -> read response(s) -> release lock.

3. Request/response correlation
- Send JSON with `request_id` on every request.
- Read line-delimited responses until matching `request_id` arrives.
- Ignore/store non-matching asynchronous messages safely.

4. Strict bounded reads
- Use short timeouts for property reads (target: 100–250ms in loop contexts).
- On timeout, return `None` (non-fatal) and continue.
- Never allow indefinite blocking in the main control loop.

5. Broken-pipe handling
- On pipe failure, invalidate the handle.
- Reconnect on next operation (or explicit reconnect path).
- Do not spin/retry forever in one call path.

### Why this prevents deadlock

Deadlock was caused by concurrent blocking `ReadFile` and `WriteFile` activity on the
same synchronous pipe handle. Serializing all I/O in one request/response critical
section removes that overlap entirely.

### Key implementation pitfalls to avoid

1. Splitting write and read outside the same lock (reintroduces interleaving risk)
2. Missing/incorrect `request_id` matching (response mix-up)
3. Overly long timeouts (input lag/frozen feel)
4. Silent pipe failures (hard to diagnose)

### Validation checklist (deadlock-focused)

1. No input freeze during rapid key presses for 5+ minutes.
2. `time-pos` readable while pause/seek/volume commands continue to work.
3. `playlist-pos` / `playlist-count` readable during playlist autoplay.
4. Recover cleanly after mpv restart without app restart.

## Proposed Implementation

### 1) `session/mpv_ipc.py`

- Replace cache-only `get_property()` with real request/response
- Add:
  - `_send_request(command, timeout)`
  - `_read_line(timeout)`
  - `_next_request_id`
  - `_io_lock`
- Keep convenience methods (`seek`, `toggle_pause`, etc.) as wrappers over `_send_request()`
- Keep cache only as optional fallback/optimization, not source of truth

### 2) `youtube/launcher.py`

- Keep existing property call sites:
  - `playlist-pos`, `playlist-count` for on-screen playlist index
  - `time-pos` for bookmarks and session save
- Add timeout-safe fallbacks:
  - if read fails, keep previous displayed values
  - do not break playback controls

### 3) `youtube/adjust.py`

- `[P]` save preset reads `video-zoom/pan` via real IPC
- If read fails, show clear message and keep session running

## IPC Message Handling Policy (Explicit)

When waiting for a specific `request_id` response:

1. Parse every newline-delimited JSON message from mpv.
2. If message has matching `request_id`:
- treat as the response for the in-flight request and return it.
3. If message has a different `request_id`:
- store it in a small pending-response map keyed by `request_id`.
4. If message is an async event (no `request_id`, e.g. property-change):
- store/update event cache (optional) or ignore safely.
5. Before reading from pipe for a request:
- check pending-response map first for an already-buffered match.

Guardrails:
- bound pending-response map size (avoid unbounded growth)
- drop oldest entries beyond limit with debug log
- never block indefinitely for unmatched responses

## `MpvIpc` API Contract (Implementation)

`connect(retries, delay) -> bool`
- `True` when duplex pipe handle is ready.
- `False` when connection cannot be established.

`close() -> None`
- idempotent; safe to call multiple times.
- clears handle state.

`command(*cmd_args, timeout=...) -> bool`
- sends command via request/response path.
- returns `True` on success response.
- returns `False` on timeout/pipe error/protocol error.

`get_property(name, timeout=...) -> Any | None`
- returns property value on success.
- returns `None` on timeout/pipe error/protocol error/missing value.
- must not raise for normal runtime failures.

Reconnect semantics:
- on broken-pipe errors, invalidate handle immediately.
- next call may attempt reconnect (or caller reconnect policy).
- no infinite retries in one call.

## Feature Flag + Rollback Contract

Suggested config key:
- `crt_config.json` -> `youtube_ipc_duplex` (bool)

Example snippet:

```json
{
  "youtube_ipc_duplex": false
}
```

Defaults:
- rollout phase 1: `false` by default, enable manually for testing
- rollout phase 2: switch default to `true` after stable validation

Behavior:
- `youtube_ipc_duplex=false`: current stable/write-only behavior
- `youtube_ipc_duplex=true`: new duplex request/response behavior

Rollback:
1. Set `youtube_ipc_duplex` back to `false`
2. Restart YouTube mode
3. Confirm controls responsive and no freezes

## Validation Checklist

1. No key-input freeze during active playback
2. `time-pos` returns non-`None` during playback
3. `playlist-pos` / `playlist-count` return non-`None` on playlist URLs
4. Bookmark save/jump and resume position work end-to-end
5. Playlist index updates reliably while videos advance
6. On IPC timeout, app remains responsive and controls still work

## Reproducible Test Procedure

1. Baseline run
- Start YouTube mode with a playlist URL.
- Confirm playback starts and controls work.

2. Rapid-input deadlock test (5 minutes)
- Repeatedly press: seek left/right, pause/resume, volume up/down, next/prev.
- Pass: no frozen input, no stuck command loop.

3. Property-read test
- During playback, log and verify non-`None` values for:
  - `time-pos`
  - `playlist-pos`
  - `playlist-count`
- Pass: values update over time and reflect playlist transitions.

4. Bookmark/session test
- Save bookmark, jump to bookmark, quit.
- Relaunch same URL and verify resume prompt/position.
- Pass: bookmark and resume both functional.

5. mpv restart recovery test
- Kill mpv during session, relaunch YouTube mode.
- Pass: no app crash; IPC reconnect path works in next run.

6. Rollback test
- Flip `youtube_ipc_duplex=false`, rerun YouTube mode.
- Pass: legacy controls remain functional and responsive.

## Scope Note

This should be treated as a dedicated IPC reliability task (not just a UI fix),
because multiple user-facing features depend on accurate mpv property reads.
