# Moonlight + CRT Left-Cutoff Issue Summary

Date: 2026-02-21

Status: Resolved (2026-02-21)

## Environment

Windows PC with CRT video chain:

`PC -> StarTech HDMI2VGA -> OSSC (VoidScaler firmware) -> HD2YPBPR HDMI-to-component -> Sony Trinitron CRT (KV-27FV300)`

## Goal

Accurate fullscreen 4:3 display for Resident Evil via Moonlight.

Known-good target when possible:

- Host/game display: `1280x960 @ 60` (4:3)
- Moonlight client stream/display: `1280x960 @ 60` (4:3)

## Observed Problem

- At `1280x960 @ 60`, CRT image is shifted/cropped on the left edge (left side cut off / edge bar issue).
- If CRT-side resolution is changed to `1280x800`, the left-edge issue disappears.
- `1280x800` is `16:10`, so it is not aspect-accurate for 4:3 content.
- Enabling VDD changes CRT geometry/position.
- Disabling VDD returns CRT geometry to normal.
- CRT can still report `60 Hz` even while this shift behavior occurs.

## VDD Context Verified In This Environment

- Two virtual drivers observed during testing:
  - `oem564.inf` = MikeTheTech (`mttvdd`)
  - `oem565.inf` = SudoMaker
- Active runtime VDD config:
  - `C:\VirtualDisplayDriver\vdd_settings.xml`
- Template/source copy in app folder:
  - `D:\Emulators\VDD.Control.25.7.23\Dependencies\vdd_settings.xml`
- Editing `Dependencies\vdd_settings.xml` did not change runtime behavior.
- `Restart Driver` reloads config from `C:\VirtualDisplayDriver\vdd_settings.xml`.
- `Locate Driver Location` did not sync/update the active XML in this setup.

## Working Hypothesis

Primary suspicion is timing/scaling/topology interaction rather than nominal refresh mismatch:

- Even when Windows reports `60 Hz`, enabling VDD likely changes display topology and timing characteristics enough to shift image in this analog chain.
- `1280x800` likely masks the issue by changing active width/aspect handling rather than preserving true 4:3 geometry.

## Open Data Gaps (Need To Capture)

1. OSSC detected input timing in both states:
   - State A: VDD disabled (image normal)
   - State B: VDD enabled (left cutoff)
   - Capture: OSSC-reported H/V timing, sync mode, and any clock/phase values shown.
2. Host GPU scaling state used during failing tests:
   - GPU vendor/control panel mode
   - Scaling mode (`No scaling`, `Preserve aspect`, `Full screen`)
   - Scaling performed on (`Display` or `GPU`)
3. Moonlight actual stream negotiation during failing tests:
   - Requested resolution/FPS vs actual stream resolution/FPS
   - Any client-side stretch/fill option state
4. VDD activation topology details:
   - Whether both `mttvdd` and `SudoMaker` virtual displays were active at the same time
   - Virtual display count in each test state

## Diagnostic Checklist (Next Pass)

1. Disable VDD and verify baseline at `1280x960 @ 60` (host + Moonlight).
2. Record OSSC timing readout and host GPU scaling mode (baseline snapshot).
3. Enable VDD only (no other changes), reproduce left cutoff, record OSSC timing again.
4. Compare baseline vs VDD-on OSSC timing readouts.
5. Repeat with only one virtual driver active at a time:
   - Only `mttvdd`
   - Only `SudoMaker`
6. Keep a single known-good GPU scaling mode while testing VDD permutations.
7. If OSSC timing remains identical but image still shifts, treat as topology/scaling-path reconfiguration issue rather than raw timing drift.

## Current Ask

Need a stable settings strategy that preserves true 4:3 accuracy at `1280x960 @ 60` without left-edge cutoff, with priority on:

1. Consistent host GPU scaling configuration
2. Verified Moonlight negotiated 4:3 stream
3. Single-driver VDD strategy if dual-driver topology proves unstable

## Resolution (What Fixed It)

Confirmed host platform: Apollo.

Working fix:

1. In Apollo, open the paired client entry (PIN tab / client settings).
2. Set `Display Mode Override` to `1280x960x60`.
3. Save settings.
4. Fully disconnect Moonlight session and reconnect (no resume).

Result:

- Left-edge cutoff/shift issue was resolved while preserving 4:3 target behavior.

Notes:

- If this regresses later, check whether override is still set and whether any additional virtual display drivers were enabled concurrently.
