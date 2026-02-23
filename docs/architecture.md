# Architecture

## Entry Point

`crt_station.py` — interactive menu that dispatches to one of six modes.

## Gaming Session (Option 3)

The primary gaming workflow. All components live under `session/`.

```
launch_session.py
  └── session/manifest.py       load + validate gaming-manifest.json
  └── session/patcher.py        backup → patch → restore on exit
        └── session/patches/retroarch.py    retroarch.cfg key/value patching
        └── session/patches/launchbox.py    Emulators.xml, BigBoxSettings.xml, Settings.xml patching
  └── session/backup.py         numbered backup files, per-file restore failure logging
  └── session/watcher.py        multi-target poll loop
        └── session/window_utils.py   shared Win32 helpers
```

### Session Lifecycle

1. Load `crt_config.json` and `gaming-manifest.json`.
2. Check if primary (LaunchBox/BigBox) is already running:
   - **Fresh start**: apply patches, launch LaunchBox, run watcher.
   - **Reattach**: apply patches, skip launch (`proc=None`), run watcher.
3. Watcher poll loop (every ~0.5 s):
   - Check if LaunchBox/BigBox is still alive — exit if not.
   - Handle Ctrl+C (see below).
   - For each emulator watch target: find its window and snap it to its CRT rect.
4. On exit: restore all patched configs, remove lockfile.

### Ctrl+C Behaviour

- **Single Ctrl+C**: soft stop — moves all active emulator windows to the main screen and pauses tracking. Session stays alive; BigBox remains open for the next game launch.
- **Second Ctrl+C within 8 seconds**: full shutdown — ends watcher, restores all configs.
- A paused emulator auto-resumes tracking when its process exits (game closed).

### Data Files

- `profiles/gaming-manifest.json` — lists primary profile, watch profiles, and patches to apply
- `profiles/launchbox-session.json` — primary process names and CRT rect (not tracked by watcher, stays on main screen)
- `profiles/retroarch-session.json`, `dolphin-session.json`, `ppsspp-session.json`, `pcsx2-session.json` — emulator window tracking targets

### Single-Session Guard

A lockfile at `.session.lock` (project root) prevents concurrent sessions. Always removed in `finally`. Contains the session PID for diagnostics.

### Validation

`validate_session.py --manifest profiles/gaming-manifest.json` — dry run: backs up, patches, and immediately restores. No permanent changes.

---

## LaunchBox Generic Wrapper

`integrations/launchbox/wrapper/launchbox_generic_wrapper.py`

Runs as a LaunchBox emulator `ApplicationPath` target. Launches the emulator, finds its window during startup, and snaps it to the CRT rect for a configurable lock period.

Runtime flow:
1. Parse arguments (profile mode or config-key mode).
2. Load `crt_config.json` and optional profile file.
3. Build launch command (emulator exe + args + ROM path from LaunchBox passthrough).
4. Launch process.
5. During lock window: find window, move to rect when it drifts.
6. Exit with emulator exit code.

Stop conditions: lock timeout expires, `wrapper_stop_enforce.flag` written by session watcher, or window lands on primary-monitor restore rect.

See `docs/launchbox/generic-wrapper.md` for full CLI reference.

---

## LaunchBox Legacy Watcher (Option 2)

`launchbox_crt_watcher.py` — older single-script watcher. Still functional but not the recommended path. Uses hardcoded process logic rather than profiles.

---

## Plex (Option 4)

`launch_plex.py` — launches Plex Desktop, locks its window to the CRT rect, restores on Ctrl+C or exit.

---

## Resident Evil Stack — Moonlight Streaming Mode (Option 5 + Tools Recovery)

`launch_resident_evil_stack.py` — orchestrates a Moonlight-based CRT streaming session for Resident Evil 1/2/3 (GOG).

Current status:

- Supported workflow: guided manual mode (`manual --game re1|re2|re3`, menu option `5`)
- Automatic mode (`start`) remains in the codebase but is on hold due to inconsistent behavior

```
launch_resident_evil_stack.py      CLI + logging + dispatch
  └── re_stack_config.json         All configurable tokens, paths, timeouts
  └── session/re_manual_mode.py    Guided manual mode flow (supported)
  └── session/re_auto_mode.py      Automatic mode flow (on hold / legacy)
  └── session/re_preflight.py      Shared preflight helpers
  └── session/display_api.py       Display enumeration, primary switching, refresh rate, CRT rect
  └── session/vdd.py               Moonlight virtual display presence check + recovery re-attach
  └── session/audio.py             Audio device switching (AudioDeviceCmdlets or nircmd)
  └── session/moonlight.py         Moonlight process management and window placement
  └── session/window_utils.py      Shared Win32 window helpers (also used by gaming session)
```

### Manual Mode Session Flow (Current)

1. Ensure Moonlight is running.
2. Open the selected RE folder and Windows Display Settings.
3. User manually sets resolutions and primary display.
4. Script verifies internal + CRT + Moonlight displays are attached.
5. Script moves Moonlight to the CRT and switches audio to the CRT output.
6. User launches the game manually.
7. On game exit or Ctrl+C, script moves Moonlight back and restores audio.
8. User restores primary display manually.

### Why Moonlight Virtual Display Is Set As Primary

Resident Evil (GOG) respects the Windows primary monitor when choosing where to render. Setting the Moonlight virtual display (`SudoMaker Virtual Display Adapter`) as primary forces the game to render on it. Moonlight then streams that output to the CRT client.

### Primary Display Switching

Setting a virtual display as primary via `ChangeDisplaySettingsEx CDS_SET_PRIMARY` returns `DISP_CHANGE_FAILED (-1)` for some virtual display drivers. The stack uses a two-tier approach:

1. `ChangeDisplaySettingsEx` with three position variants (keep current position, zero position, no position change).
2. If all three fail: `SetDisplayConfig` — repositions all source modes so the target lands at `(0, 0)`, which is how Windows determines the primary monitor.

After the primary switch, the Windows virtual desktop coordinate space shifts (SudoMaker is now at 0,0). The Moonlight window must be explicitly moved to the internal display immediately, or it drifts into virtual display space and becomes invisible.

### VDD Lifecycle

The SudoMaker VDD is an IddCx-based virtual display driver managed by Apollo (the streaming host). IddCx drivers cannot be re-attached via standard Windows display APIs (`SetDisplayConfig SDC_TOPOLOGY_EXTEND` or `ChangeDisplaySettingsEx`) once soft-disconnected — these return error 87 or `DISP_CHANGE_BADMODE` respectively.

- **On `start`**: wait for VDD to appear (Apollo should have it attached). If soft-disconnected, attempt recovery by enumerating driver-supported modes via index (`EnumDisplaySettings(dev, 0)`, `(dev, 1)`, ...) and re-enabling with `ChangeDisplaySettingsEx`. Poll up to `VDD_ATTACH_TIMEOUT_SECONDS`.
- **On `restore`**: VDD is left attached. Only primary display and audio are restored. Unplugging the VDD is not done because re-attachment requires Apollo to restart if recovery mode fails.

The VDD stays attached between sessions as a harmless secondary display.

### Moonlight Window Lifecycle

| Phase | Moonlight window position |
|---|---|
| Before session | Internal display (wherever it was) |
| After VDD plug / before primary switch | Internal display |
| After primary switch | Explicitly moved to internal display (coordinate space shifted) |
| During config/launcher screens | Internal display (user sees config on laptop screen) |
| When gameplay window detected | Moved to CRT display bounds |
| After restore | Moved back to internal display |

### Gameplay Window Detection

Moonlight itself stays windowed (has a title bar) even when the game inside it goes fullscreen. WS_CAPTION detection is therefore unreliable as a CRT-move trigger.

Instead, each profile JSON declares a `gameplay_title` — a window title substring that appears only when the actual game window is open, not during the launcher/config screen:

| Profile | `gameplay_title` | Distinguishes from |
|---|---|---|
| `re1-gog.json` | `"RESIDENT EVIL"` | `"CONFIGURATION"`, `"MOD SELECTION"` |
| `re2-gog.json` | `"RESIDENT EVIL 2"` | `"CONFIGURATION"` |
| `re3-gog.json` | `"NEMISIS"` | `"CONFIGURATION"` |

The enforcement loop calls `is_gameplay_window_visible(gameplay_title)` once per second. When detected for 2 continuous seconds (`fullscreen_confirm_seconds`), Moonlight is moved to the CRT.

### Session Flow

1. Abort if a RE game process is already running.
2. Ensure Moonlight process is running.
3. Wait for Moonlight virtual display (SudoMaker VDD) to be attached.
4. Preflight: confirm internal + CRT + Moonlight displays are all attached.
5. Save current primary, set Moonlight virtual display as primary, set CRT refresh.
6. Move Moonlight window to internal display (corrects coordinate space shift from primary switch).
7. Switch audio to CRT output device.
8. Launch game wrapper (`launchbox_generic_wrapper.py`).
9. Enforcement loop:
   - Re-apply primary if it drifts.
   - Correct CRT refresh every ~5 s if it drifts.
   - Detect gameplay window via title; move Moonlight to CRT when confirmed.
10. On exit/crash/Ctrl+C: restore primary, audio, move Moonlight to internal.

See `docs/runbooks/resident-evil-stack-automation.md` for commands and troubleshooting.
See `docs/runbooks/resident-evil-stack-code-flow.md` for detailed function-level flow.

---

## Shared Utilities

- `session/window_utils.py` — all Win32 window operations used across the codebase
- `crt_config.json` — global coordinates, executable paths, polling cadence, restore rect
- `wrapper_stop_enforce.flag` — written by session watcher on soft stop or shutdown to signal wrapper scripts to disengage



