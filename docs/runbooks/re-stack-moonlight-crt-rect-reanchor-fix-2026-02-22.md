# RE Stack Moonlight CRT Rect Re-Anchor Fix

Date: 2026-02-22

Status: Mitigation added (needs more real-world confirmation)

## Symptom

After the RE stack switched primary display to the SudoMaker virtual display, Moonlight could land with the edge/bar visible inside the CRT usable area even though the move step logged success.

Example log pattern:

- `ChangeDisplaySettingsEx` primary methods fail
- fallback succeeds via `SetDisplayConfig`
- Moonlight move uses configured `moonlight.crt_rect`
- window moves, but appears misaligned on CRT

## Root Cause (Observed)

`moonlight.crt_rect` in `re_stack_config.json` is stored as an absolute desktop rect (`x/y/w/h`).

When primary display switching falls back to `SetDisplayConfig`, Windows can re-root desktop coordinates. The saved absolute rect can then point to the wrong location relative to the CRT display even if width/height are still correct.

## Fix Implemented

File: `session/moonlight.py`

Added re-anchoring logic for configured Moonlight CRT rects:

1. Read current live CRT display bounds (`get_crt_display_rect`).
2. If a configured `crt_rect` exists, compare its overlap with the live CRT bounds.
3. Compute a candidate rect by preserving the saved offset relative to the CRT, normalized in whole-monitor-width/height steps.
4. Use the candidate rect if it improves overlap with the current CRT display.

This keeps the user's tuned overscan/edge offsets, but adapts to desktop-origin shifts caused by topology changes.

## Expected Log Signal

When re-anchoring triggers, a log line is emitted:

- `[re-stack] Re-anchored configured CRT rect to current CRT display origin: ...`

## Verification Performed

Direct test of `move_moonlight_to_crt(...)` after patch:

- Live CRT detected: `\\.\DISPLAY5 x=3840, y=0, w=1280, h=960`
- Saved rect re-anchored from `x=1170, y=-80` to `x=3730, y=-80`
- Moonlight move returned success

## Follow-Up If Alignment Is Still Slightly Off

Re-save the Moonlight CRT rect under the current topology:

- `python launch_resident_evil_stack.py set-crt-pos`
- or `python launch_resident_evil_stack.py adjust-moonlight`

