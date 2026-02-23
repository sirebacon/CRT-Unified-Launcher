# Calibration Tools

Module: `tools/calibration.py` (proposed) | Entry: `python crt_tools.py calibrate <subcommand>`

**Status: Mixed.** `adjust`, `set-crt`, and `set-idle` exist today as subcommands of
`launch_resident_evil_stack.py`. The migration moves them to `crt_tools.py calibrate` with the
same behavior. `set-crt-offsets` and `overlap` are new additions.

---

## calibrate adjust

```
python crt_tools.py calibrate adjust
```

**Existing command:** `python launch_resident_evil_stack.py adjust-moonlight`

Interactive keyboard-driven tool to position and size the Moonlight window live, then save the
result to `re_stack_config.json`.

**Prerequisites:** Moonlight must be open before running this command.

**Controls:**

| Key | Action |
|-----|--------|
| Arrow keys | Move window left / right / up / down |
| `[` / `]` | Decrease / increase width |
| `-` / `=` | Decrease / increase height |
| `1` - `9` | Set step size: 1, 5, 10, 25, 50, 100, 200, 500, 1000 px |
| `i` | Save current position as idle (restore) rect |
| `c` | Save current position as CRT rect |
| `q` or `Esc` | Quit without saving |

The live position is shown on the same line, updating as you move:

```
=== Moonlight Window Adjuster  (Moonlight) ===
  Arrow keys   move x/y          [ / ]   narrower / wider
  - / =        shorter / taller  1-9     step size
  i  save idle rect              c       save CRT rect
  q / Esc      quit without saving

  x=  1170  y=   -80  w=  1410  h=  1110  step=  10px
```

**Saves to:** `re_stack_config.json` under `moonlight.crt_rect` (key `c`) or
`moonlight.idle_rect` (key `i`). Both can be saved in the same session.

**Backing module:** `session/moonlight_adjuster.py` -- `adjust_moonlight()`

---

## calibrate set-crt

```
python crt_tools.py calibrate set-crt
```

**Existing command:** `python launch_resident_evil_stack.py set-crt-pos`

Captures the current Moonlight window rect and saves it as the CRT rect
(`moonlight.crt_rect`) in `re_stack_config.json`.

Use this as a quick alternative to the interactive adjuster when you have already positioned
Moonlight manually (e.g. via Windows drag) and just want to record the position.

**Sample output:**

```
[re-stack] Moonlight window: 'Moonlight'  x=1170, y=-80, w=1410, h=1110
[re-stack] Saved as Moonlight CRT rect in re_stack_config.json.
```

**Backing module:** `session/moonlight_adjuster.py` -- `capture_moonlight_pos("crt_rect")`

---

## calibrate set-idle

```
python crt_tools.py calibrate set-idle
```

**Existing command:** `python launch_resident_evil_stack.py set-idle-pos`

Captures the current Moonlight window rect and saves it as the idle (restore) rect
(`moonlight.idle_rect`) in `re_stack_config.json`.

This is where Moonlight returns to after a session. Run this when Moonlight is sitting where
you want it to live when no session is active.

**Backing module:** `session/moonlight_adjuster.py` -- `capture_moonlight_pos("idle_rect")`

---

## calibrate set-crt-offsets

```
python crt_tools.py calibrate set-crt-offsets
python crt_tools.py calibrate set-crt-offsets --from-current
```

**Status: Proposed (new).** Saves a CRT calibration as *relative offsets* from the live CRT
display bounds, rather than as absolute screen coordinates.

This is the hardening plan's preferred calibration format. Absolute `crt_rect` coordinates
break after a primary display switch shifts the virtual desktop origin (e.g. when SudoMaker
moves to `(0,0)`, all other display positions shift). Relative offsets are computed at session
time from the live CRT display rect, so they survive topology changes.

**How offsets work:**

```
live_crt_rect  = get_crt_display_rect(crt_tokens)   # e.g. (1920, 0, 1920, 1080)
window_rect    = live_crt_rect + offsets + deltas

x  = crt_x + x_offset   # e.g.  1920 + (-110) = 1810
y  = crt_y + y_offset   # e.g.  0    + (-80)  = -80
w  = crt_w + w_delta    # e.g.  1920 + 130    = 2050  (overscan)
h  = crt_h + h_delta    # e.g.  1080 + 150    = 1230  (overscan)
```

**With `--from-current`:** reads the current Moonlight window rect and the current CRT display
rect, computes the offsets, and writes them to `re_stack_config.json` as `crt_calibration`:

```json
{
  "crt_calibration": {
    "mode": "relative_to_crt",
    "x_offset": -110,
    "y_offset": -80,
    "w_delta": 130,
    "h_delta": 150
  }
}
```

**Without `--from-current`:** opens the interactive adjuster, then computes offsets from the
saved position and the live CRT rect before writing.

---

## calibrate overlap

```
python crt_tools.py calibrate overlap --window "moonlight" --display crt
python crt_tools.py calibrate overlap --window "moonlight" --display crt --threshold 0.95
```

**Status: Proposed (new).** Checks the overlap ratio between a window's current rect and a
display's bounds. This is the post-move verification check from the hardening plan.

Returns a ratio from 0.0 (no overlap) to 1.0 (window is fully inside the display). Also shows
the raw rects and any out-of-bounds pixels.

**Sample output:**

```
Window  : Moonlight  x=1170  y=-80  w=1410  h=1110  (HWND 0x001C04)
Display : CP-1262HE  x=1920  y=0    w=1920  h=1080

Intersection: x=1920  y=0  w=1160  h=1000
Window area : 1,565,100 px
Overlap area: 1,160,000 px
Overlap ratio: 0.741  (threshold: 0.95)  BELOW THRESHOLD

  Window is 250px left of display and 110px below display bottom.
  Consider re-running 'calibrate adjust' or 'calibrate set-crt-offsets'.
```

**Backing function:** `_rect_overlap_ratio()` -- currently private in `session/re_manual_mode.py`.
The hardening plan moves it to `session/window_utils.py` so both this tool and the placement
helpers can use it.

---

## Quick Reference: Existing Calibration Commands

| Old command | New command | Notes |
|-------------|-------------|-------|
| `python launch_resident_evil_stack.py adjust-moonlight` | `python crt_tools.py calibrate adjust` | Identical behavior |
| `python launch_resident_evil_stack.py set-crt-pos` | `python crt_tools.py calibrate set-crt` | Identical behavior |
| `python launch_resident_evil_stack.py set-idle-pos` | `python crt_tools.py calibrate set-idle` | Identical behavior |

During migration the old commands remain as aliases. Both forms work.
