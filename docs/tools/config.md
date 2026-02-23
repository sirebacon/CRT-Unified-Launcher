# Config Tools

Module: `tools/config.py` (proposed) | Entry: `python crt_tools.py config <subcommand>`

**Status: Proposed.** All tools in this group are planned.

These tools read and validate the configuration layer -- `re_stack_config.json` for the RE stack,
and the LaunchBox wrapper profiles. They never write config.

---

## config dump

```
python crt_tools.py config dump
```

Displays all resolved configuration values from `re_stack_config.json` with their types and
sources (file value vs built-in default). Helps confirm the config file is being read and parsed
correctly.

**Sections shown:**

**Paths:**
```
moonlight_dir    : D:\Emulators\MoonlightPortable-x64-6.1.0  [from file]
  Moonlight.exe  : D:\Emulators\MoonlightPortable-x64-6.1.0\Moonlight.exe  exists: yes
```

**Moonlight rects:**
```
idle_rect        : x=69  y=99  w=1598  h=851  [from file]
crt_rect         : x=1170  y=-80  w=1410  h=1110  [from file]
```

**Display tokens:**
```
re_primary_token         : "SudoMaker Virtual Display"
crt_token                : "NVIDIA GeForce RTX 4090 Laptop GPU"
crt_target_refresh_hz    : 60
restore_primary_token    : "Intel(R) UHD Graphics"
```

**Required display groups:**
```
internal_display   : ["Internal Display", "Intel(R) UHD Graphics"]
crt_display        : ["CP-1262HE", "NVIDIA GeForce RTX 4090 Laptop GPU"]
moonlight_display  : ["SudoMaker Virtual Display"]
```

**Audio tokens:**
```
re_device_token      : "CP-1262HE (NVIDIA High Definition Audio)"
restore_device_token : "Speakers (Realtek(R) Audio)"
```

**Timers:**
```
vdd_attach_timeout_seconds  : 15
fullscreen_confirm_seconds  : 2.0
```

**Game profiles:**
```
re1  : integrations/launchbox/wrapper/profiles/re1-gog.json  exists: yes
re2  : integrations/launchbox/wrapper/profiles/re2-gog.json  exists: yes
re3  : integrations/launchbox/wrapper/profiles/re3-gog.json  exists: yes
```

**Config file:** `re_stack_config.json` (project root)

---

## config check

```
python crt_tools.py config check
```

Validates the config against live system state. Each check is labeled PASS / WARN / FAIL.

**Checks performed:**

| Check | FAIL condition |
|-------|---------------|
| Config file readable | File missing or JSON parse error |
| `moonlight_dir` exists | Directory not found |
| `Moonlight.exe` exists | File not found under `moonlight_dir` |
| Display token resolves (`crt_token`) | No attached display matches the token |
| Display token resolves (`re_primary_token`) | No attached display matches the token |
| Display token resolves (`restore_primary_token`) | No attached display matches the token |
| All required_groups resolve | Any group has no matching attached display |
| Audio backend available | Neither `AudioDeviceCmdlets` nor `nircmd` detected |
| Audio token resolves (`re_device_token`) | No playback device matches the token |
| Audio token resolves (`restore_device_token`) | No playback device matches the token |
| All profile JSONs exist and parse | Missing file or JSON error in any profile |
| Profile `process_name` non-empty | Profile loaded but no process names declared |

**Sample output (all passing):**

```
Config check: re_stack_config.json

  PASS  Config file readable
  PASS  moonlight_dir exists
  PASS  Moonlight.exe found
  PASS  crt_token resolves -> \\.\DISPLAY5 (NVIDIA / CP-1262HE)
  PASS  re_primary_token resolves -> \\.\DISPLAY9 (SudoMaker Virtual Display)
  PASS  restore_primary_token resolves -> \\.\DISPLAY1 (Intel UHD)
  PASS  required_groups: all 3 groups resolve
  PASS  Audio backend: AudioDeviceCmdlets
  PASS  re_device_token resolves -> CP-1262HE (NVIDIA High Definition Audio)
  PASS  restore_device_token resolves -> Speakers (Realtek(R) Audio)
  PASS  re1 profile OK (process_name: ["biohazard.exe"])
  PASS  re2 profile OK (process_name: ["re2.exe"])
  PASS  re3 profile OK (process_name: ["re3.exe"])

  13/13 checks passed.
```

**Sample output (with failures):**

```
  FAIL  crt_token "NVIDIA GeForce RTX 4090 Laptop GPU" -> no attached display matches
        (Is the CRT connected and powered on?)
  WARN  Audio backend: none found
        Install AudioDeviceCmdlets or add nircmd.exe to PATH
```

Run `config check` before the first session on a new machine, or after any hardware change.
Also useful after editing `re_stack_config.json` to confirm no typos in token strings.

---

## config check --wrapper

```
python crt_tools.py config check --wrapper profiles/re1-gog.json
```

Validates a LaunchBox wrapper profile against the wrapper schema. Checks:

- Required fields are present (`process_name`, `path`)
- `path` exists on disk (the game or emulator executable)
- `_gameplay_title` and `_config_title` are present on profiles that use `position_only: true`
  (RE GOG profiles use title-based gameplay detection, not window-class matching)
- `process_name` list is non-empty
- No unknown top-level keys (warns on unexpected fields that may be typos)

Note: RE GOG profiles do not contain a `crt_rect` -- the Moonlight window rect comes from
`re_stack_config.json`, not the wrapper profile. A validator must not require `crt_rect` in the
profile or it will reject all valid RE profiles.

**Sample output:**

```
Wrapper profile: integrations/launchbox/wrapper/profiles/re1-gog.json

  PASS  process_name: ["biohazard.exe"]
  PASS  position_only: true
  PASS  _gameplay_title: "RESIDENT EVIL"
  PASS  _config_title: "CONFIGURATION"
  WARN  path not found: D:\GOG Galaxy\Games\Resident Evil\Biohazard.exe
        (Is the game installed at this path?)

  4/5 checks passed, 1 warning.
```
