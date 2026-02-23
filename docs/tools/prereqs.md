# Prereqs Tool

Module: `tools/prereqs.py` (proposed) | Entry: `python crt_tools.py prereqs`

**Status: Proposed.**

---

## prereqs

```
python crt_tools.py prereqs
```

Checks all dependencies required to run the CRT launcher and RE stack. Each item is labeled
PASS / WARN / FAIL. Run this on a new machine or after a system update.

---

### Python packages

| Check | FAIL condition |
|-------|---------------|
| `pywin32` importable | `import win32api` fails -- display/window APIs unavailable |
| `psutil` importable | `import psutil` fails -- process tracking unavailable |

**Install:**

```
pip install pywin32 psutil
```

---

### Audio switching backend

| Check | Result |
|-------|--------|
| `AudioDeviceCmdlets` available | PASS -- preferred backend |
| `nircmd.exe` on PATH | PASS (fallback) -- only checked if AudioDeviceCmdlets is absent |
| Neither found | FAIL -- audio switching will not work |

**Install AudioDeviceCmdlets (preferred):**

```powershell
Install-Module -Name AudioDeviceCmdlets
```

**Install nircmd (fallback):**

Download `nircmd.exe` from nirsoft.net and place it on the system PATH, or in the project root.

---

### Moonlight

| Check | FAIL condition |
|-------|---------------|
| `moonlight_dir` path exists | Directory configured in `re_stack_config.json` not found |
| `Moonlight.exe` exists | Executable not found under `moonlight_dir` |

**Config key:** `moonlight_dir` in `re_stack_config.json`

---

### Apollo (VDD owner)

| Check | FAIL condition |
|-------|---------------|
| Apollo process running | Neither `ApolloDisplayHost.exe` nor `Apollo.exe` found |
| SudoMaker VDD attached | No attached display matches `SudoMaker Virtual Display` token |

Apollo manages the SudoMaker virtual display. If Apollo is not running, the VDD will not be
attached and the RE stack will fail at the VDD wait step.

**Note:** The VDD check is WARN (not FAIL) if the VDD is not currently attached but Apollo is
running -- Apollo may not have attached it yet, or it may be in recovery mode.

---

### Config file

| Check | FAIL condition |
|-------|---------------|
| `re_stack_config.json` readable | File missing or JSON parse error |
| All display tokens non-empty | Any required token is an empty string |
| All game profile paths exist | A profile path in `game_profiles` does not point to a file |

---

### Sample output (all passing)

```
Prereqs check

Python packages:
  PASS  pywin32
  PASS  psutil

Audio backend:
  PASS  AudioDeviceCmdlets

Moonlight:
  PASS  moonlight_dir: D:\Emulators\MoonlightPortable-x64-6.1.0
  PASS  Moonlight.exe found

Apollo / VDD:
  PASS  Apollo process running (ApolloDisplayHost.exe  PID 1944)
  PASS  SudoMaker VDD attached  (\\.\DISPLAY9)

Config:
  PASS  re_stack_config.json readable
  PASS  Display tokens non-empty
  PASS  re1, re2, re3 profiles found

12/12 checks passed.  Ready to run.
```

---

### Sample output (with failures)

```
Python packages:
  PASS  pywin32
  FAIL  psutil  -> not installed
        pip install psutil

Audio backend:
  FAIL  AudioDeviceCmdlets -> not found
  FAIL  nircmd -> not found
        Install AudioDeviceCmdlets or add nircmd.exe to PATH

Apollo / VDD:
  WARN  SudoMaker VDD not attached
        Apollo is running but VDD is not in the active topology.
        Start a session normally -- Apollo should attach the VDD on connect.

3/5 checks passed, 1 warning, 2 failures.
```
