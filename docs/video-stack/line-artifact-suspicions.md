# Line/Edge Artifact Suspicions

This note summarizes likely causes of the odd edge/line behavior seen in RetroArch, based on:

- `docs/video-stack/README.md`
- `docs/video-stack/components.md`
- `docs/video-stack/device-listings.md`
- `docs/video-stack/measurements.md`
- Current session/profile behavior in CRT Unified Launcher

## Current Observations

- N64 is working without visible edge/line problems.
- Some other RetroArch cores/systems show edge bending or odd lines.
- Plex content does not show the same issue.
- CRT hardware has already been tuned to a stable "best practical" state.

## Most Likely Explanation (Primary)

The issue is mainly per-system/per-core output interacting with the active image area, not a single hardware failure.

Why:
- N64 being stable proves the chain can produce a clean image.
- Different RetroArch cores output different timings/resolutions/active areas.
- The measured visible area is smaller than full frame (`docs/video-stack/measurements.md`), so edge regions are sensitive.
- Border garbage/blanking behavior varies by system and can appear as odd edge lines.

## Secondary Stack-Level Contributors

Given this chain:

PC -> StarTech HDMI2VGA -> OSSC (VoidScaler) -> HDMI-to-YPbPr converter -> CRT

small timing/format differences can compound across active devices:

- EDID/format negotiation at StarTech stage
- OSSC/VoidScaler scaling and active-area shaping
- Converter limitations (HDCP/deep-color/downscaler limits) and format constraints
- CRT native overscan/edge geometry

This can make one core/system look perfect while another exposes edge artifacts.

### Revised confidence on hypothesis 3 (timing variance across cores)

The PC always outputs a fixed resolution (1280x960) to the CRT monitor regardless of which
RetroArch core is running. The signal chain therefore sees an identical input for all cores —
there is no mechanism by which a different core causes a different timing at the HDMI2VGA,
OSSC, or HD2YPBPR stage. Chain-level timing variance is a static property of this setup, not
a per-core variable. This reduces hypothesis 3 from "medium confidence" to low.

The observed core-to-core differences must originate from what each core renders inside the
RetroArch window (overscan content, active image area, border behavior), not from signal chain
variance. This further strengthens hypothesis 1 as the dominant explanation.

### HD2YPBPR / OSSC output resolution — open question

The HD2YPBPR device listing documents these constraints:
- No downscaler
- No 480i support
- Supported HDMI inputs: 480p, 576i/p, 720p, 1080i, 1080p

The CRT is noted as "configured for 240p/480i." This raises a question: what is the
OSSC/VoidScaler actually outputting to the HD2YPBPR, and what YPbPr format reaches the CRT?

If the OSSC outputs 480p → HD2YPBPR converts to 480p component → CRT displays it, the chain
is coherent. If there is a mismatch (e.g. OSSC outputting a format the HD2YPBPR handles
imperfectly), that would be a static chain problem affecting all content equally — which
contradicts the N64-is-fine evidence. So a mismatch here is unlikely to be the cause of
core-specific artifacts, but the actual OSSC output resolution is worth documenting for
completeness. This has not been recorded yet.

## Why Plex Looks Fine

Plex has stable modern video timings and does not carry retro border/blanking behavior.
Retro cores switch modes and present varied active image boundaries, so edge artifacts are
easier to reveal there.

## Working Hypothesis Priority

1. Per-core/per-system active-area and overscan differences (highest confidence).
2. Horizontal edge clipping sensitivity in current visible rectangle (high confidence).
3. Multi-stage conversion timing variance across specific core outputs (low confidence —
   revised down; PC output is fixed at 1280x960 regardless of core, so the chain sees
   identical input for all cores).
4. Fundamental CRT miscalibration (low confidence, because N64 and Plex can look stable).

## Practical Direction

- Keep CRT hardware geometry as baseline (do not retune globally).
- Tune per-core overrides first (crop overscan, scaling/aspect choices).
- Add `video_crop_overscan = "true"` to `profiles/gaming-manifest.json` retroarch_cfg patch
  as a global baseline; use per-core overrides to disable it only where it crops too
  aggressively (e.g. cuts HUD or text).
- Use measured safe area from `docs/video-stack/measurements.md` as the operational baseline.
- Treat stack listing claims as secondary; prioritize measured behavior in this project.
- Record the actual OSSC/VoidScaler output resolution when known, for chain documentation.

## Notes on measurements.md

The coordinate values in `docs/video-stack/measurements.md` still reflect the old calibrated
x=-1211 values. Current project-active RetroArch rect is x=-1221. That document should be
updated when recalibration is confirmed stable.

## Operational Observation: If Video Works, Treat It as Working

Given current OSSC/VoidScaler visibility limits, exact internal mode handling is not always verifiable.

Project operating rule for this stack:

1. If video output is stable and playable on the CRT, treat the chain state as working.
2. Prioritize observed behavior (sync stability, latency feel, geometry consistency) over theoretical mode assumptions.
3. Focus fixes on per-core/per-system tuning (overrides, crop, aspect, profile rects) before changing hardware-chain assumptions.

Working criteria used in practice:

- Stable sync (no rolling/dropouts in normal play)
- Acceptable latency
- Predictable geometry after overrides
- Repeatable behavior session-to-session
