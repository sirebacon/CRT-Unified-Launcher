# Session Tools

Module: `tools/session.py` (proposed) | Entry: `python crt_tools.py session <subcommand>`

**Status: Proposed.** All tools in this group are planned.

RE stack scope: `session state` reads the state file written by auto mode -- it is only meaningful
if auto mode was run. The other subcommands (`log`, `flag`, `processes`) are useful in both
manual and auto mode contexts.

---

## session state

```
python crt_tools.py session state
```

**Mode: Auto** -- reads `runtime/re_stack_state.json`, which is written by
`apply_re_mode_system_state()` at auto-mode session start.

Shows the saved pre-session display state:

- `previous_primary_device_name` -- the display that was primary before the RE session started
- `crt_mode` -- the CRT display mode at session start (`device_name`, `width`, `height`, `hz`)
- File mtime -- when the state was last written

Note: the state file contains display state only. Audio restore uses the static
`restore_device_token` from `re_stack_config.json`, not a saved snapshot.

**Sample output:**

```
State file: runtime/re_stack_state.json  (written 2026-02-22 14:03:17)

previous_primary_device_name : \\.\DISPLAY1
crt_mode:
  device_name : \\.\DISPLAY5
  resolution  : 1920x1080
  refresh_hz  : 60
```

**If no state file exists:**

```
No state file found (runtime/re_stack_state.json).
Either auto mode has never run or the file was cleaned up after restore.
```

Use this after an interrupted auto-mode session to understand what state the restore path will
target.

---

## session log

```
python crt_tools.py session log
python crt_tools.py session log --lines 50
python crt_tools.py session log --follow
```

Tails the RE stack log at `runtime/re_stack.log`.

`--lines N` -- show the last N lines (default: 30)
`--follow` -- follow the log live (like `tail -f`); exit with `Ctrl+C`

**Sample output:**

```
[2026-02-22 14:03:10] [re-stack] Moonlight: process running (PID 4812).
[2026-02-22 14:03:11] [re-stack] VDD: already attached.
[2026-02-22 14:03:12] [re-stack] Required display 'internal_display' matched: \\.\DISPLAY1 via token 'Intel(R) UHD Graphics'
[2026-02-22 14:03:12] [re-stack] Required display 'crt_display' matched: \\.\DISPLAY5 via token 'NVIDIA GeForce RTX 4090 Laptop GPU'
[2026-02-22 14:03:12] [re-stack] Required display 'moonlight_display' matched: \\.\DISPLAY9 via token 'SudoMaker Virtual Display'
[2026-02-22 14:03:15] [re-stack] Moonlight moved to CRT rect: x=1170 y=-80 w=1410 h=1110
```

**Log location:** `runtime/re_stack.log` (relative to project root)

---

## session flag

```
python crt_tools.py session flag
python crt_tools.py session flag --clear
```

Checks or clears the `wrapper_stop_enforce.flag` stop flag.

**What the flag does:** When the flag file exists, `launchbox_generic_wrapper.py` disengages its
window lock loop. The session watcher writes this flag on soft stop (single `Ctrl+C`) and full
shutdown (second `Ctrl+C`).

`session flag` (no args) -- reports whether the flag is present and when it was written.

`session flag --clear` -- deletes the flag file. Use this if a session left the flag behind and
the wrapper is not enforcing on the next launch.

**Sample output:**

```
Stop flag: wrapper_stop_enforce.flag
  Status  : PRESENT  (written 2026-02-22 14:15:42)

  Wrappers will NOT enforce window position while this flag exists.
  Run with --clear to remove it.
```

**If the flag is absent:**

```
Stop flag: wrapper_stop_enforce.flag
  Status  : not present  (wrappers will enforce normally)
```

---

## session processes

```
python crt_tools.py session processes
```

Lists running processes relevant to the CRT launcher:

- Moonlight (`Moonlight.exe`)
- RE game processes from all known profiles (e.g. `biohazard.exe`, `re2.exe`)
- Active `launchbox_generic_wrapper.py` subprocesses
- LaunchBox / BigBox (`launchbox.exe`, `bigbox.exe`) -- session status
- Apollo / ApolloDisplayHost -- VDD owner

For each matched process: PID, process name, start time, and (where available) the command line.

**Sample output:**

```
Moonlight            PID 4812   started 14:03:05   Moonlight.exe
launchbox            PID 7203   started 09:15:00   LaunchBox.exe
ApolloDisplayHost    PID 1944   started 09:14:58   ApolloDisplayHost.exe

RE game processes    : none running
Wrapper processes    : none running
Stop flag            : not present
```

**Backing functions:** `session/re_game.py` -- `is_re_game_running()`, `re_process_names()`,
`find_wrapper_pids()`; `psutil` for process enumeration.
