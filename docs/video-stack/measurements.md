# Measurements and Calibration Anchors

## PC Output

- Resolution: 1280 x 960

## Estimated Usable Space

Based on current CRT Unified Launcher usage:

- Estimated usable resolution: 1060 x 835
- Horizontal crop: 220 px total (about 110 px per side if centered)
- Vertical crop: 125 px total (about 62/63 px top/bottom if centered)
- Visible area ratio: about 72% of full 1280 x 960
- Cropped/overscanned area: about 28%

## Likely Active Rectangle (Working Hypothesis)

- Full timing likely remains 1280 x 960.
- Effective visible active area appears around 1060 x 835.
- Likely near-centered margins:
  - Left/right: about 110 px
  - Top/bottom: about 62 to 63 px

Aspect clue:

- 1060 / 835 = about 1.269 (narrower than 4:3 = 1.333).
- Suggests stronger horizontal clipping, or conservative width estimate.

## Current Project-Calibrated Values

From current project config/profile values:

- Session/default CRT target rect (`launcher_integration`): `x=-1211, y=43, w=1057, h=835`
- LaunchBox session profile rect (`profiles/launchbox-session.json`): `x=-1211, y=43, w=1057, h=835`
- Dolphin rect (`crt_config.json`): `x=-1211, y=43, w=1060, h=835`
- PCSX2 rect (`crt_config.json`): `x=-1211, y=43, w=1057, h=848`
- Restore-to-main rect (`primary_on_exit`): `x=100, y=100, w=1280, h=720`
- Session poll cadence (`poll_seconds`): `0.5`

Session patch value currently used for RetroArch:

- `video_aspect_ratio = 1.265868`
