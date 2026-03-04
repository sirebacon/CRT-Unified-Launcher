# Component Map

This map is organized by runtime boundaries, not by folder alphabetically.

## Ownership Model

Use these owner tags to keep code changes modular and reviews focused:

- `Platform`: menu, launch routing, shared config, cross-mode plumbing
- `Gaming`: session watcher/patching and emulator CRT enforcement
- `Media`: mpv session orchestration, controls, state, provider contract
- `Providers`: site-specific media resolver/provider modules
- `Browser`: browser-backed playback adapter and extension assets
- `RE Stack`: Moonlight + RE workflows and restore logic
- `Tools`: diagnostics/recovery CLI command modules

## 1) Entry Scripts

| File | Responsibility | Key Dependencies | Owner |
|---|---|---|---|
| `crt_station.py` | Interactive top-level menu and mode dispatch | `launch_session.py`, `launch_youtube.py`, `launch_plex.py`, `launch_resident_evil_stack.py`, `crt_tools.py` | `Platform` |
| `launch_session.py` | Gaming session startup/reattach, patch lifecycle, watcher loop wiring | `session/manifest.py`, `session/patcher.py`, `session/watcher.py` | `Gaming` |
| `launch_youtube.py` | Thin media entrypoint | `youtube/launcher.py` | `Media` |
| `launch_plex.py` | Plex launch + window lock + restore | `profiles/plex-session.json`, Win32 window APIs | `Platform` |
| `launch_resident_evil_stack.py` | RE stack CLI (`manual`, `inspect`, `restore`) | `session/re_*`, `session/display_api.py`, `session/moonlight.py`, `session/audio.py` | `RE Stack` |
| `crt_tools.py` | CRT diagnostics/recovery CLI entrypoint | `tools/cli.py` | `Tools` |
| `validate_session.py` | Dry-run session patch/restore validation | `session/manifest.py`, `session/patcher.py` | `Gaming` |

## 2) Session/Gaming Core (`session/`)

| Module | Responsibility | Notes for Maintainers | Owner |
|---|---|---|---|
| `manifest.py` | Load and validate manifest/watch entries | First stop for profile/manifest schema issues | `Gaming` |
| `patcher.py` | Apply and restore patch sets | Calls `backup.py` and `patches/*` | `Gaming` |
| `patches/launchbox.py` | LaunchBox XML patching | Affects `Data/Emulators.xml`, `BigBoxSettings.xml`, `Settings.xml` | `Gaming` |
| `patches/retroarch.py` | RetroArch cfg key/value patching | Handles line-based cfg edits | `Gaming` |
| `backup.py` | Backup/restore file copies and cleanup | Recovery behavior depends on this | `Gaming` |
| `watcher.py` | Enforcement loop for emulator windows + Ctrl+C soft/full stop logic | Writes/clears `wrapper_stop_enforce.flag` | `Gaming` |
| `window_utils.py` | Shared Win32 process/window helpers | Used by gaming, media, wrappers, RE stack | `Platform` |
| `display_api.py` | Display discovery, mode handling, primary switch logic | High-risk system behavior; test carefully | `Platform` |
| `audio.py` | Default playback device switching (PowerShell backends) | RE stack and tools rely on this | `Platform` |
| `moonlight.py` | Moonlight process/window placement and CRT re-anchor helpers | RE flows depend on stable geometry handling | `RE Stack` |
| `vdd.py` | Virtual display adapter checks/attach handling | Used by RE preflight/recovery paths | `RE Stack` |
| `re_manual_mode.py` | Supported RE manual flow orchestration | Current recommended RE mode | `RE Stack` |
| `re_auto_mode.py` | Legacy/experimental automatic RE flow | Keep behavior conservative unless explicitly revisiting auto mode | `RE Stack` |
| `re_preflight.py` | RE prechecks for display prerequisites | Called before moving into stack flow | `RE Stack` |
| `re_state.py` | Runtime RE state persistence/restore helpers | Affects restore reliability after interruption | `RE Stack` |
| `re_config.py` | RE config parsing helpers | Keep config parsing centralized here | `RE Stack` |
| `re_game.py` | RE process/wrapper detection helpers | Used for guardrails and flow gates | `RE Stack` |
| `mpv_ipc.py` | JSON IPC client for mpv named pipe | Shared by media session controls/telemetry | `Media` |
| `moonlight_adjuster.py` | Interactive Moonlight rect capture/update helpers | Calibration utilities consume this | `RE Stack` |

## 3) Media Session (`youtube/` + `media/`)

### 3.1 Orchestrator and generic session behavior

| Module | Responsibility | Owner |
|---|---|---|
| `youtube/launcher.py` | Main media runtime: provider dispatch, mpv command build, key loop, autoplay, telemetry, browser-tier dispatch | `Media` |
| `youtube/player.py` | mpv window waiting/move/save geometry helpers | `Media` |
| `youtube/controls.py` | NOW PLAYING and status line rendering | `Media` |
| `youtube/adjust.py` | Adjust-mode key handling for x/y/w/h | `Media` |
| `youtube/telemetry.py` | IPC-driven playback telemetry | `Media` |
| `youtube/state.py` | History/favorites/session/bookmark/zoom persistence | `Media` |
| `youtube/queue.py` | Queue loading/saving/playlist temp file generation | `Media` |
| `youtube/config.py` | Config loading, local override merge, clipboard helper, quality preset helpers | `Media` |

### 3.2 Provider system

| Module | Responsibility | Owner |
|---|---|---|
| `media/providers/base.py` | Provider interface and capability model | `Media` |
| `media/providers/registry.py` | Provider registration order and URL dispatch | `Media` |
| `media/providers/youtube.py` | Tier 1 yt-dlp-backed provider | `Providers` |
| `media/providers/aniwatch.py` | Tier 2 resolver-backed provider using Node bridge | `Providers` |
| `media/providers/wco.py` | Tier 2 WCO provider facade + cache + playlist metadata integration | `Providers` |
| `media/providers/wco_http.py` | WCO resolver HTTP chain and localhost proxy serving path | `Providers` |
| `media/providers/wco_playlist.py` | Episode list/next/prev derivation | `Providers` |
| `media/providers/wco_types.py` | WCO result dataclasses + validation | `Providers` |
| `media/providers/wco_utils.py` | WCO host/slug/url normalization helpers | `Providers` |
| `media/providers/kisscartoon.py` | Tier 3 browser-backed provider returning launch directives | `Providers` |
| `media/providers/generic.py` | Fallback provider for direct URL/file playback | `Providers` |

### 3.3 Browser-backed playback support (Tier 3)

| Module | Responsibility | Owner |
|---|---|---|
| `media/browser_launcher.py` | Mode A system-browser launch and Mode B Playwright launch, isolated profile and window placement logic | `Browser` |
| `media/browser_ext/crt_fullscreen/*` | Chrome extension assets used for fullscreen containment behavior in browser mode | `Browser` |

## 4) Integrations

| Path | Responsibility | Owner |
|---|---|---|
| `integrations/aniwatch-js/resolve.js` | HiAnime resolver subprocess entrypoint; prints JSON payload consumed by Python provider | `Providers` |
| `integrations/aniwatch-js/package*.json` | Resolver dependency pinning | `Providers` |
| `integrations/launchbox/wrapper/launchbox_generic_wrapper.py` | Generic LaunchBox-side launcher wrapper (window lock during startup) | `Gaming` |
| `integrations/launchbox/wrapper/launchbox_*_wrapper.py` | Emulator-specific wrapper aliases/shims | `Gaming` |
| `integrations/launchbox/wrapper/profiles/*.json` | Wrapper profile definitions with optional inheritance | `Gaming` |

## 5) CRT Tools (`tools/`)

`tools/cli.py` routes subcommands. Most behavior modules are pure command handlers:

- `tools/display.py`: display diagnostics and restore actions
- `tools/audio.py`: audio status/set/restore
- `tools/config.py`: config dump/check routines
- `tools/prereqs.py`: dependency/system checks
- `tools/windows.py`: window list/watch/move/restore actions
- `tools/session.py`: RE/session state, logs, process inspection
- `tools/preset.py`: preset list/apply/save
- `tools/calibration.py`: Moonlight calibration commands

## 6) Config and Profiles

| File | Purpose | Owner |
|---|---|---|
| `crt_config.json` | Global runtime config (paths, media keys, launcher/session settings) | `Platform` |
| `crt_config.local.json` | Local machine override (gitignored) merged by media config loader | `Platform` |
| `crt_config.local.json.example` | Template for local override keys | `Platform` |
| `crt_presets.json` | Named preset values for display/session tuning | `Platform` |
| `re_stack_config.json` | Resident Evil stack-specific tokens, timings, and display/audio settings | `RE Stack` |
| `profiles/*.json` | Session/watch rects and manifest for gaming/media | `Gaming` / `Media` |

## 7) Runtime Artifacts

| Path | Produced By | Purpose |
|---|---|---|
| `runtime/youtube.log` | `youtube/launcher.py` | Unified media/provider/session logs |
| `runtime/mpv.log` | mpv process launched by media session | mpv/ffmpeg/ytdl diagnostics |
| `runtime/re_stack.log` | RE stack launcher | RE flow diagnostics |
| `runtime/re_stack_state.json` | RE state helpers | Restore context after interruption |
| `wrapper_stop_enforce.flag` | Session watcher/tools | Stop signal for wrapper enforcement |
| `.session.lock` | Gaming session launcher | Single-session guard |

## 8) Dependency Diagrams

### 8.1 Top-Level Runtime

```text
crt_station.py
  |-- launch_session.py -----------------> session/* -----------------> profiles/* + crt_config.json
  |-- launch_youtube.py -> youtube/launcher.py
  |                         |-- media/providers/registry.py -> media/providers/*
  |                         |-- session/mpv_ipc.py + session/window_utils.py
  |                         |-- media/browser_launcher.py (Tier 3 only)
  |                         `-- runtime/youtube.log + runtime/mpv.log
  |-- launch_resident_evil_stack.py ----> session/re_* + session/display_api.py + re_stack_config.json
  `-- crt_tools.py -> tools/cli.py ------> tools/*
```

### 8.2 Media Provider Dispatch

```text
input URL
  -> media/providers/registry.py
     -> YouTubeProvider (Tier 1, yt-dlp)
     -> AniwatchProvider (Tier 2, Node resolver)
     -> WCOProvider (Tier 2, HTTP resolver + localhost proxy)
     -> KissCartoonProvider (Tier 3, browser launch directive)
     -> GenericProvider (fallback)

resolved payload
  -> youtube/launcher.py
     -> mpv path (requires_mpv=true)
     `-> browser_launcher path (requires_mpv=false)
```

## 9) Legacy and Transitional Surfaces

- `launchbox_crt_watcher.py` and `launchbox_session_mode.py` are older direct workflows. Current preferred path is `launch_session.py` + `session/*`.
- `launch_generic.py` is a historical standalone launcher and not the central orchestration path.
- `youtube/` currently holds active generic media logic; planned migration to `media/core/` is documented but not complete.
