# Audio Tools

Module: `tools/audio.py` (proposed) | Entry: `python crt_tools.py audio <subcommand>`

**Status: Proposed.** All tools in this group are planned.

Backing module: `session/audio.py` -- PowerShell runner, device selection, backend detection.

---

## audio status

```
python crt_tools.py audio status
```

Reports the current audio configuration:

- Which switching backend is available: `AudioDeviceCmdlets`, `nircmd`, or `none`
- All active playback devices and their display names (from `Get-AudioDevice -List`)
- Which device is currently set as default
- The device tokens configured in `re_stack_config.json` (`re_device_token`,
  `restore_device_token`) and whether each token resolves to a known device

**Sample output:**

```
Audio backend    : AudioDeviceCmdlets
Default playback : Speakers (Realtek(R) Audio)

Playback devices:
  [1]  Speakers (Realtek(R) Audio)              [DEFAULT]
  [2]  CP-1262HE (NVIDIA High Definition Audio)
  [3]  Headphones (USB Audio Device)

Config tokens:
  re_device_token     : "CP-1262HE (NVIDIA High Definition Audio)"  -> matches [2]
  restore_device_token: "Speakers (Realtek(R) Audio)"               -> matches [1]
```

Use `audio status` before a session to confirm both tokens resolve, so a failed audio switch
won't be a surprise mid-session.

**Backing function:** `session/audio.py` -- `audio_tool_status()`

---

## audio set

```
python crt_tools.py audio set "CP-1262HE"
python crt_tools.py audio set "CP-1262HE" --force
```

Sets the default Windows playback device to the first device whose name contains the given token
(case-insensitive substring).

Without `--force`, prints the resolved device name and prompts for confirmation. With `--force`,
applies immediately.

**Backends (tried in order):**
1. `AudioDeviceCmdlets` (PowerShell module) -- preferred
2. `nircmd.exe` -- fallback; sets all three nircmd role indexes (Console=0, Multimedia=1,
   Communications=2)
3. Neither available -- prints an install reminder and returns failure

**Sample output:**

```
Setting default audio to: CP-1262HE (NVIDIA High Definition Audio)
[re-stack] Default audio set: CP-1262HE
```

**If the token does not match any device:**

```
[re-stack] Audio device not found for token: CP-1262HE
```

**Backing function:** `session/audio.py` -- `set_default_audio_best_effort(name_token)`

---

## audio restore

```
python crt_tools.py audio restore
python crt_tools.py audio restore --force
```

Restores the default playback device to the token configured as `restore_device_token` in
`re_stack_config.json` (default: `Speakers (Realtek(R) Audio)`).

Without `--force`, prints the target device and prompts for confirmation.

**Use for:** recovery when the session ended without restoring audio (e.g. after a crash).

---

## Prerequisites

Audio switching requires one of:

| Tool | Install |
|------|---------|
| `AudioDeviceCmdlets` | `Install-Module -Name AudioDeviceCmdlets` in PowerShell (admin) |
| `nircmd.exe` | Download from [nirsoft.net](https://www.nirsoft.net/utils/nircmd.html); place on PATH |

`AudioDeviceCmdlets` is preferred -- `nircmd` is a fallback for systems where PowerShell modules
cannot be installed.

Check which backend is available: `python crt_tools.py audio status`

Check backend only: `python crt_tools.py prereqs` (see prereqs.md)
