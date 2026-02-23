# Tools Reference -- Index

All diagnostic and settings tools for CRT-Unified-Launcher.

**RE stack scope:** Supported workflow is **manual mode** (`launch_resident_evil_stack.py manual --game re1|re2|re3`). Auto mode is on hold. Tools marked **Auto** apply only if auto mode is resumed.

---

## Documents

| Document | Module | Tools |
|----------|--------|-------|
| [display.md](display.md) | `tools/display.py` | dump, modes, vdd, token, restore |
| [windows.md](windows.md) | `tools/windows.py` | list, watch, move, restore |
| [audio.md](audio.md) | `tools/audio.py` | status, set, restore |
| [session.md](session.md) | `tools/session.py` | state, log, flag, processes |
| [config.md](config.md) | `tools/config.py` | dump, check, wrapper validation |
| [calibration.md](calibration.md) | `tools/calibration.py` | adjust, set-crt, set-idle, offsets, overlap |
| [prereqs.md](prereqs.md) | `tools/prereqs.py` | prereqs check |
| [gaming-session.md](gaming-session.md) | *(existing scripts)* | validate, debug runs |

---

## Module Architecture

> **Implementation status:**
> - **Done (Phases 1 & 2):** `crt_tools.py`, `tools/cli.py`, `display dump`, `config dump/check`,
>   `prereqs`, `window list/watch/move`, `audio status/set/restore`, `session log/processes/flag`,
>   `calibrate adjust/set-crt/set-idle/overlap`
> - **Planned (Phases 4 & 5):** `display restore`, `window restore`, `display modes/vdd/token`,
>   `session state`, `config check --wrapper`, `calibrate set-crt-offsets`

### Entry point

```
crt_tools.py                   Project root -- routes all tool commands
```

All tools run as:
```
python crt_tools.py <category> <subcommand> [options]
```

### Package structure

```
tools/
  __init__.py
  cli.py           argparse routing for all categories
  display.py       display dump, modes, vdd, token, restore
  windows.py       window list, watch, move, restore
  audio.py         audio status, set, restore
  session.py       session state, log, flag, processes
  config.py        config dump, check
  calibration.py   calibrate adjust, set-crt, set-idle, set-crt-offsets, overlap
  prereqs.py       prereqs check
```

The existing `tools/` directory holds legacy scripts (`inspectRetro.py`, `plex_callibrate.py`, etc.). These stay untouched alongside the new package.

### Design rules

**Thin wrappers over `session/`.**
All logic lives in `session/display_api.py`, `session/window_utils.py`, `session/audio.py`, etc.
Tool modules call those functions, format the results, and return. No logic is duplicated.

**Functions return data; CLI formats it.**
Each tool function returns a plain dict or dataclass. The CLI layer (`cli.py`) formats for terminal output. Functions are importable for scripting:

```python
from tools.display import display_dump
state = display_dump()
print(state["displays"][0]["rational_refresh_hz"])
```

**Read-only by default.**
Mutable tools (`display restore`, `audio set`, `window move`) print what they will do and require `--force` to apply without prompting.

**No side effects on import.**
Config and device enumeration happen when a function is called, not at import time.

**Unified error format.**
```
[tools] FAIL: display dump -- reason here
```

### Migration from `launch_resident_evil_stack.py`

| Current command | Migrates to | Notes |
|-----------------|-------------|-------|
| `launch_resident_evil_stack.py inspect` | `crt_tools.py display dump` | Extended version replaces it |
| `launch_resident_evil_stack.py adjust-moonlight` | `crt_tools.py calibrate adjust` | Same logic, new home |
| `launch_resident_evil_stack.py set-crt-pos` | `crt_tools.py calibrate set-crt` | Same logic, new home |
| `launch_resident_evil_stack.py set-idle-pos` | `crt_tools.py calibrate set-idle` | Same logic, new home |
| `launch_resident_evil_stack.py manual --game re1` | stays on launcher | Session command, not a tool |
| `launch_resident_evil_stack.py restore` | stays on launcher | Session command, not a tool |

Once `crt_tools.py` is built, the old commands can be kept as aliases that delegate to it.

### Implementation order

1. `tools/display.py` + `crt_tools.py display dump` -- replaces `inspect`, adds rational refresh. Highest value.
2. `tools/prereqs.py` + `crt_tools.py prereqs` -- fast to build, high value for setup.
3. `tools/config.py` + `crt_tools.py config dump|check` -- config resolution with live cross-check.
4. `tools/windows.py` + `crt_tools.py window list` -- replaces `inspectRetro.py`.
5. `tools/audio.py`, `tools/session.py` -- fill in remaining read-only categories.
6. `tools/calibration.py` -- migrate `adjust-moonlight`, add `set-crt-offsets`.
7. Recovery commands (`display restore`, `audio restore`, `window restore`).

Each step is independent. Stop at any point and what exists is fully usable.

---

## Quick Reference -- Existing Tools

| Command | What it does |
|---------|-------------|
| `python launch_resident_evil_stack.py inspect` | Display tokens, primary, audio tool |
| `python launch_resident_evil_stack.py adjust-moonlight` | Interactive Moonlight window adjuster |
| `python launch_resident_evil_stack.py set-crt-pos` | Save Moonlight CRT rect |
| `python launch_resident_evil_stack.py set-idle-pos` | Save Moonlight idle rect |
| `python launch_resident_evil_stack.py restore` | Full RE stack restore |
| `python launch_resident_evil_stack.py manual --game re1` | Start RE1 manual session |
| `python validate_session.py --manifest profiles/gaming-manifest.json` | Dry-run session validation |
| `python launch_generic.py --profile-file <profile> --debug` | Single-profile debug run |
| `python tools\inspectRetro.py` | Legacy window inspector (hardcoded to Dolphin) |
| `python tools\plex_callibrate.py` | Plex live calibration |
| `crt_station.py -> Tools -> Restore Default Settings` | Restore backed-up configs |
| `crt_station.py -> Tools -> Recover Resident Evil Stack` | Run RE stack restore |
| `crt_station.py -> Tools -> Restore Display & Audio` | Display + audio reset only |

## Quick Reference -- Proposed Tools

All commands: `python crt_tools.py <category> <subcommand>`

| Command | Module | Priority | Mode |
|---------|--------|----------|------|
| `display dump` | `tools/display.py` | High | Both |
| `display modes [--display crt]` | `tools/display.py` | Medium | Both |
| `display vdd` | `tools/display.py` | High | Both |
| `display token "..."` | `tools/display.py` | High | Both |
| `display restore [--primary-only]` | `tools/display.py` | High | Both |
| `window list [--filter "..."]` | `tools/windows.py` | High | Both |
| `window watch "..."` | `tools/windows.py` | Medium | Both |
| `window move --title "..." --display crt` | `tools/windows.py` | Medium | Both |
| `window restore` | `tools/windows.py` | Medium | Both |
| `audio status` | `tools/audio.py` | High | Both |
| `audio set "..."` | `tools/audio.py` | Medium | Both |
| `audio restore` | `tools/audio.py` | Medium | Both |
| `session state` | `tools/session.py` | Medium | Auto |
| `session log [--lines N]` | `tools/session.py` | Medium | Both |
| `session flag [--clear]` | `tools/session.py` | Low | Both |
| `session processes` | `tools/session.py` | Medium | Both |
| `config dump` | `tools/config.py` | High | Both |
| `config check` | `tools/config.py` | High | Both |
| `calibrate adjust` | `tools/calibration.py` | High | Both |
| `calibrate set-crt` | `tools/calibration.py` | High | Both |
| `calibrate set-idle` | `tools/calibration.py` | High | Both |
| `calibrate set-crt-offsets` | `tools/calibration.py` | High | Both |
| `calibrate overlap --window "..." --display crt` | `tools/calibration.py` | Medium | Both |
| `prereqs` | `tools/prereqs.py` | High | Both |

