# Display Tools

Module: `tools/display.py` (proposed) | Entry: `python crt_tools.py display <subcommand>`

**Status: Proposed.** All tools in this group are planned. The migration note shows the existing
equivalent command where one exists.

---

## display dump

```
python crt_tools.py display dump
```

Dumps the full state of all displays currently attached to the Windows desktop. This is the
primary diagnostic for "why is my display behaving wrong?" and replaces the narrower
`launch_resident_evil_stack.py inspect`.

**What it shows for each attached display:**

- `device_name` -- Windows GDI name (e.g. `\\.\DISPLAY5`)
- `device_string` -- Adapter name (e.g. `NVIDIA GeForce RTX 4090 Laptop GPU`)
- `monitor_strings` -- Physical monitor name(s) attached to this adapter (e.g. `CP-1262HE`)
- `position` -- Desktop origin `(x, y)` of this display
- `resolution` -- Current `WxH` from `EnumDisplaySettings`
- `refresh_hz` -- Integer refresh from `EnumDisplaySettings`
- `rational_refresh` -- Rational `N/D` refresh from `QueryDisplayConfig` (e.g. `60000/1000` = 60.000 Hz)
- `is_primary` -- Whether this is the current primary display
- `state_flags` -- Raw `DISPLAY_DEVICE_*` flags for advanced diagnostics

**Summary line after each display:**

```
[PRIMARY] \\.\DISPLAY1  Intel(R) UHD Graphics  pos=(0,0)  1920x1200@60Hz  (rational: 60000/1000)
          \\.\DISPLAY5  NVIDIA GeForce RTX 4090  CP-1262HE  pos=(1920,0)  1920x1080@60Hz  (rational: 60000/1000)
          \\.\DISPLAY9  SudoMaker Virtual Display  pos=(3840,0)  1920x1080@60Hz  (rational: 60000/1000)
```

**Why rational refresh matters:** `EnumDisplaySettings` returns integer Hz. A display running at
60.002 Hz reads as 60 Hz from the integer field. `QueryDisplayConfig` returns `Numerator/Denominator`
and catches this. The enforcement loop's early-exit uses integer comparison -- if the rational rate
is not `60000/1000`, the loop will silently miss a drift. Use `display dump` to verify the actual
rational rate after a mode change.

**Migration from:** `python launch_resident_evil_stack.py inspect`

---

## display modes

```
python crt_tools.py display modes
python crt_tools.py display modes --display crt
```

Lists all modes the driver reports for an attached display, enumerated via `EnumDisplaySettings`
with index enumeration. Useful when checking which refresh rates are available before editing config.

Without `--display`, lists modes for all attached displays. The `--display` flag accepts a token
substring (e.g. `crt`, `nvidia`, `sudomaker`, `DISPLAY5`).

**Sample output:**

```
\\.\DISPLAY5  NVIDIA / CP-1262HE
  [0]  1920x1080  @60Hz
  [1]  1920x1080  @50Hz
  [2]  1920x1080  @30Hz
  [3]  1280x720   @60Hz
  ...
```

---

## display vdd

```
python crt_tools.py display vdd
```

Checks the status of the SudoMaker Virtual Display Adapter (VDD). Reports:

- Whether any SudoMaker adapter is detected (scans ALL display adapters, not just attached)
- Which `\\.\DISPLAYn` slot it occupies (DISPLAY9-18 are the SudoMaker slots)
- Whether it is currently attached to the Windows desktop topology
- The modes available from the driver (index enumeration, same as recovery path in `vdd.py`)

This is the quickest diagnostic for "is the VDD attached?" without starting a session.

**VDD notes:**
- The SudoMaker VDD is an IddCx driver managed by Apollo. It cannot be re-attached via standard
  Windows display APIs (`SetDisplayConfig`, `ChangeDisplaySettingsEx`) once soft-disconnected.
- Recovery: enumerate driver modes by index and apply the first valid mode.
- If all adapters show `attached=False`, restart Apollo.

**Sample output:**

```
VDD status:
  Adapter found   : yes
  Device name     : \\.\DISPLAY9
  Device string   : SudoMaker Virtual Display Adapter
  Attached        : yes  (DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)
  Available modes : 6 modes; first valid = 1920x1080@60Hz
```

---

## display token

```
python crt_tools.py display token "CP-1262HE"
python crt_tools.py display token "SudoMaker Virtual Display"
```

Resolves a token string to the display it matches, showing exactly which adapter/monitor the
config token selects. Use this to verify that `re_stack_config.json` tokens actually match the
correct physical display.

Token matching is case-insensitive substring. The search checks `device_name`, `device_string`,
and all `monitor_strings` for each attached display.

**Sample output:**

```
Token: "CP-1262HE"
  Match found   : yes
  Device name   : \\.\DISPLAY5
  Device string : NVIDIA GeForce RTX 4090 Laptop GPU
  Monitor       : CP-1262HE
  Position      : (1920, 0)
  Resolution    : 1920x1080 @ 60 Hz

Token: "SudoMaker Virtual Display"
  Match found   : yes
  Device name   : \\.\DISPLAY9
  Device string : SudoMaker Virtual Display Adapter
  Position      : (3840, 0)
  Resolution    : 1920x1080 @ 60 Hz
```

Use this when adding a new game profile or changing config tokens to confirm the match before a
live session.

---

## display restore

```
python crt_tools.py display restore
python crt_tools.py display restore --primary-only
python crt_tools.py display restore --force
```

Restores primary display and CRT refresh rate to the configured defaults. Reads
`re_stack_config.json` for `restore_primary_token` and `crt_target_refresh_hz`.

Without `--force`, prints what it will do and prompts for confirmation. With `--force`, applies
immediately (safe for scripts or `crt_station.py` menu items).

`--primary-only` skips the CRT refresh restore (useful if only the primary drifted).

**What it does:**
1. Calls `set_primary_display_verified(restore_primary_token)` -- two-tier switch with 3 retries
2. Waits for the NVIDIA driver settling window (backoff: 1.5s, 2s, 3s, 4s)
3. Calls `restore_display_mode` or `set_display_refresh_best_effort` for the CRT

**NVIDIA quirk:** `CDS_UPDATEREGISTRY` is rejected on DISPLAY5 by the NVIDIA hybrid-GPU driver.
`display restore` always tries `flags=0` (dynamic apply) first, then falls back to
`CDS_UPDATEREGISTRY`. This is the same strategy used in `session/display_api.py`.

**Migration from:** partially covered by `python launch_resident_evil_stack.py restore`

---

## Backing Functions (session/display_api.py)

| Function | Used by |
|----------|---------|
| `enumerate_attached_displays()` | `display dump`, `display vdd`, preflight |
| `find_display_by_token(token)` | `display token`, all other callers |
| `current_primary_display()` | `display dump`, restore path |
| `get_display_mode(token)` | `display dump`, state save |
| `set_display_refresh_best_effort(token, hz)` | `display restore`, enforcement loop |
| `restore_display_mode(saved)` | `display restore`, `apply_restore_system_state` |
| `set_primary_display_verified(token)` | `display restore`, restore path |

All functions return plain dicts or booleans -- importable for scripting:

```python
from session.display_api import enumerate_attached_displays
for d in enumerate_attached_displays():
    print(d["device_name"], d["device_string"])
```

