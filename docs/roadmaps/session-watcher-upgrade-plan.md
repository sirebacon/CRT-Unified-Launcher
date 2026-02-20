# Session Watcher Upgrade Plan: Option 3

**Goal:** Build a hybrid replacement for the LaunchBox CRT Watcher (option 2) as option 3 in `crt_master.py`. Option 2 stays untouched as the proven fallback.

---

## What Option 2 Currently Does

Option 2 is two separate steps.

### Step 1 — Config patching (`launchbox_session_mode.py`)

Runs before LaunchBox opens. Backs up four files then patches them:

| File | What gets patched |
|---|---|
| `retroarch.cfg` | Sets windowed mode (`video_fullscreen=false`, `video_windowed_fullscreen=false`), no decorations, fixes aspect ratio |
| `Emulators.xml` | Redirects each emulator's `ApplicationPath` to a wrapper `.bat`; strips fullscreen flags from platform command lines (`-f`, `--fullscreen`, `-C Dolphin.Display.Fullscreen=True`, `-fullscreen`) |
| `BigBoxSettings.xml` | Sets `PrimaryMonitorIndex`, disables splash screens |
| `Settings.xml` | Disables LaunchBox splash screens |

All four files are restored from backup when the session ends. If the session crashes, they are left in the patched state until the next restore.

### Step 2 — Runtime watcher (`launchbox_crt_watcher.py`)

Runs alongside LaunchBox. Polls all windows every 0.5s:

- Deliberately **skips** RetroArch, PPSSPP, Dolphin, PCSX2 — those are moved by their own wrapper `.bat` processes
- Catches everything else on `target_processes` (Steam/GOG Galaxy launched games, etc.) and moves them to the CRT rect
- Also matches windows whose parent process is in `target_parent_processes` (steam.exe, galaxyclient.exe, goggalaxy.exe)
- On Ctrl+C: writes `wrapper_stop_enforce.flag` (signals wrapper processes to stop), then moves all tracked windows back to the primary monitor

---

## The Problem with Option 2

The config manipulation is not the problem — it is genuinely necessary. Emulators need to be in windowed mode and pointing at wrapper scripts for window positioning to work at all. Skipping that step breaks everything.

**The real problem is that the manipulation is hardcoded in Python.** `launchbox_session_mode.py` has explicit knowledge of RetroArch, PPSSPP, Dolphin, and PCSX2 baked into the code. `launchbox_crt_watcher.py` has a hardcoded process list. Adding a fifth emulator means editing Python files in multiple places.

---

## What Option 3 Should Do

The same end result as option 2 — config patching + window locking — but both driven by data instead of hardcoded logic.

- Config manipulation instructions live in the session manifest (JSON), not in Python
- Window watching is driven by session profiles
- Adding a new emulator = add a JSON block to the manifest and create a session profile
- No Python changes required

---

## Core Design Principle

> The Python files become generic engines that know *how* to apply patch types.
> The manifest files define *what* to patch for each specific emulator.

The per-emulator knowledge moves out of Python and into data files. The Python surface becomes small, stable, and emulator-agnostic.

---

## Proposed Architecture

### Files

```
launch_session.py               new orchestrator script

profiles/
  gaming-manifest.json          new — single file that drives the entire session
  launchbox-session.json        existing — primary app window profile
  retroarch-session.json        existing — window profile
  dolphin-session.json          needs creating
  ppsspp-session.json           needs creating
  pcsx2-session.json            needs creating
```

### Session manifest: `profiles/gaming-manifest.json`

The manifest defines everything for a session in one file — what configs to patch and what windows to watch.

```json
{
  "primary": "launchbox-session.json",

  "watch": [
    "retroarch-session.json",
    "dolphin-session.json",
    "ppsspp-session.json",
    "pcsx2-session.json"
  ],

  "patches": [
    {
      "type": "retroarch_cfg",
      "path": "D:\\Emulators\\RetroArch-Win64\\retroarch.cfg",
      "set": {
        "video_fullscreen": "false",
        "video_windowed_fullscreen": "false",
        "video_window_show_decorations": "false",
        "video_force_aspect": "false",
        "video_aspect_ratio_auto": "false"
      }
    },
    {
      "type": "launchbox_emulator",
      "title": "retroarch",
      "strip_args": ["-f"],
      "wrapper_bat": "..\\CRT-Unified-Launcher\\integrations\\launchbox\\wrapper\\launchbox_retroarch_wrapper.bat"
    },
    {
      "type": "launchbox_emulator",
      "title": "ppsspp",
      "strip_args": ["--fullscreen"],
      "wrapper_bat": "..\\CRT-Unified-Launcher\\integrations\\launchbox\\wrapper\\launchbox_ppsspp_wrapper.bat"
    },
    {
      "type": "launchbox_emulator",
      "title": "dolphin",
      "strip_args": ["-C Dolphin.Display.Fullscreen=True"],
      "wrapper_bat": "..\\CRT-Unified-Launcher\\integrations\\launchbox\\wrapper\\launchbox_dolphin_wrapper.bat"
    },
    {
      "type": "launchbox_emulator",
      "title": "pcsx2",
      "strip_args": ["-fullscreen"],
      "wrapper_bat": "..\\CRT-Unified-Launcher\\integrations\\launchbox\\wrapper\\launchbox_pcsx2_wrapper.bat"
    },
    {
      "type": "launchbox_settings",
      "bigbox_monitor_index": 1,
      "disable_splash_screens": true
    }
  ]
}
```

### `launch_session.py` — what it does

1. Read manifest
2. Back up all files referenced by patches
3. Apply all patches (same logic as session mode, but driven by manifest data)
4. Launch primary app (LaunchBox)
5. Poll all watch profiles simultaneously — lock each emulator window to its profile rect as it appears
6. On Ctrl+C:
   - Write `wrapper_stop_enforce.flag`
   - Move all open emulator windows back to primary rect
   - Restore all backed-up config files

### Patch types the engine needs to handle

| Type | What it does |
|---|---|
| `retroarch_cfg` | Set key=value pairs in RetroArch's cfg format; restore from backup on exit |
| `launchbox_emulator` | In Emulators.xml: set `ApplicationPath` to wrapper bat, strip specified args from platform command lines; restore from backup on exit |
| `launchbox_settings` | In BigBoxSettings.xml and Settings.xml: set monitor index, disable splash screens; restore from backup on exit |

These three handlers cover everything option 2 currently does. The Python implements the handlers generically — the manifest supplies the specifics.

### `launchbox_session_mode.py` role going forward

It stays as-is for option 2. For option 3, a new generic patch engine (inside `launch_session.py` or a shared module) reads from the manifest instead. The existing per-emulator logic in `launchbox_session_mode.py` is not touched.

---

## Modularization

`launch_session.py` as a single monolithic file would be hard to maintain — the same problem as option 2 in a different form. The logic should be split across focused modules so each piece can be read, tested, and changed independently.

### Proposed module structure

```
launch_session.py               thin orchestrator — argument parsing and sequencing only

session/
  __init__.py
  manifest.py                   manifest loading and validation
  backup.py                     generic file backup and restore
  patcher.py                    patch coordinator — dispatches to patch handlers
  watcher.py                    multi-target window poll loop
  window_utils.py               shared Win32 window API helpers
  patches/
    __init__.py
    retroarch.py                RetroArch cfg format handler
    launchbox.py                LaunchBox XML handler (emulator entries + settings)
```

### What each module owns

**`launch_session.py`** — 30–50 lines. Parses arguments, calls the other modules in order, handles the top-level exit sequence. Contains no business logic. If you read only this file you should understand the full session flow.

**`session/manifest.py`** — loads the manifest JSON, validates the schema, checks that all referenced profile files and patch target files exist before anything is touched. Returns a clean object the rest of the code can use without worrying about missing keys. Manifest validation lives here and nowhere else.

**`session/backup.py`** — copies files to a temp directory before patching, restores them on exit. Knows nothing about what the files contain or what format they are in. Purely file operations. Can be tested independently with any files.

**`session/patcher.py`** — thin coordinator. Reads the `type` field from each patch entry in the manifest and dispatches to the correct handler in `patches/`. Calls `backup.py` before applying. Calls `backup.py` again on restore. Contains no format-specific logic itself.

**`session/patches/retroarch.py`** — reads and writes RetroArch's custom `key = "value"` cfg format. Sets the keys specified in the manifest. No XML, no LaunchBox knowledge.

**`session/patches/launchbox.py`** — reads and writes LaunchBox XML files using `xml.etree.ElementTree`. Handles both the `launchbox_emulator` patch type (Emulators.xml) and the `launchbox_settings` patch type (BigBoxSettings.xml, Settings.xml). Both share the same XML parsing helpers so they stay in one file.

**`session/watcher.py`** — the multi-target poll loop. Loads session profiles, watches for each process, locks windows to their profile rects, detects when the primary app exits, handles cursor visibility, writes the stop flag on exit. Has no knowledge of config patching or backup.

**`session/window_utils.py`** — low-level Win32 helpers: `find_window`, `move_window`, `get_rect`, `enum_windows`, `pids_for_root`. No business logic, just thin wrappers around the Win32 API. Shared between the session watcher and `launch_generic.py`.

### Why this breakdown stops here

Some modules were considered for further splitting and rejected:

- **`manifest.py`** — loading and validation are tightly coupled. You validate as you load. Splitting into a loader and a validator creates two files that always change together and can never be used independently.
- **`watcher.py`** — the poll loop, window locking, cursor visibility, stop flag, and primary exit detection are all part of one continuous runtime behaviour. Splitting them creates artificial seams in what is fundamentally one loop.
- **`patches/launchbox.py`** — splitting into `emulator.py` and `settings.py` would duplicate the shared XML helpers (`_set_text`, `_save_tree`) or require a third XML utility file. More overhead than benefit.
- **`window_utils.py`** — small flat helpers that are always used together. No natural split.

### Why `window_utils.py` matters beyond this project

`launch_generic.py` currently has its own copies of all these Win32 helpers inline. Once `session/window_utils.py` exists, `launch_generic.py` can import from it and remove its duplicates. Any bug fix or improvement to window finding applies everywhere at once. This is the most immediate maintainability win from the whole modularization effort.

### Adding a new patch type in the future

1. Add a new file to `session/patches/` (e.g. `pcsx2_ini.py`)
2. Add one dispatch entry in `session/patcher.py`
3. Add the patch block to the manifest

No existing files are touched. This is the open/closed principle in practice — the system is open for extension and closed for modification.

### `launchbox_session_mode.py` role going forward

Not touched. Remains the implementation for option 2. If option 2 is eventually retired, this file is deleted. Nothing in the new module structure depends on it.

### Dependency flow

```
launch_session.py
  ├── session/manifest.py           no dependencies on other session modules
  ├── session/backup.py             no dependencies on other session modules
  ├── session/patcher.py
  │     ├── session/backup.py
  │     ├── session/patches/retroarch.py
  │     └── session/patches/launchbox.py
  └── session/watcher.py
        └── session/window_utils.py

launch_generic.py
  └── session/window_utils.py       shared
```

Each module only knows about the layer below it. The orchestrator knows about everything. No circular dependencies.

---

## Edge Cases

### Partial patch failure
If one patch in the list fails (e.g. Emulators.xml is locked by LaunchBox, retroarch.cfg is read-only), should the session abort and restore everything, or continue with whatever patches succeeded?

**Recommendation:** Abort and restore on any patch failure. A partial patch leaves the system in an inconsistent state — some emulators would have wrapper bats redirected, others would not. Failing cleanly is safer than proceeding.

### LaunchBox exits on its own
Option 2 keeps running until Ctrl+C regardless of whether LaunchBox is still open. If LaunchBox is closed by the user rather than via Ctrl+C, the watcher keeps running and configs stay patched indefinitely.

`launch_session.py` should detect when LaunchBox exits and treat it as a clean session end — write the stop flag, restore windows, restore configs, and exit. This is better behaviour than option 2.

### Two watch profiles matching the same process
Unlikely given that profiles use specific process names, but if two profiles both list `retroarch.exe`, the watcher would try to move the same window to two different rects on alternate poll cycles, causing it to flicker between positions.

**Recommendation:** Validate the manifest on load and reject duplicate process names across watch profiles.

### LaunchBox is already running when session starts
Option 2 always assumes a fresh LaunchBox launch. If LaunchBox is already open, `apply_crt_session_mode` patches configs that LaunchBox has already read — the patches have no effect until LaunchBox restarts.

`launch_session.py` should detect this and either warn the user or refuse to start, rather than silently applying patches that won't take effect.

### Patch file locked by another process
Windows file locking can prevent writing to XML files if LaunchBox or an emulator has them open. The backup step itself could fail if a file is locked.

**Recommendation:** Check all patch target files are writable before starting the backup. Report which file is locked and exit cleanly if any are inaccessible.

### Stop flag written too early
If `wrapper_stop_enforce.flag` is written before the emulator windows are moved back to primary, the wrapper process stops enforcing the CRT rect — but the window is still on the CRT. The window move then needs to succeed independently.

**Recommendation:** Move windows first, then write the stop flag. Order matters.

### Session restore interrupted
If Ctrl+C is pressed a second time during the restore/cleanup sequence, the restore is cut short. Config files could be partially restored.

**Recommendation:** Block keyboard interrupt during the exit sequence. Catch the second Ctrl+C and log a warning but continue the restore to completion.

---

## Open Questions and Missing Ideas

### Parent process matching gap
Option 2's watcher catches PC games launched through Steam or GOG Galaxy by checking the window's parent process chain (`target_parent_processes`: steam.exe, galaxyclient.exe, goggalaxy.exe). The profile-based approach only watches explicitly listed processes — any game not in the manifest is ignored.

If you play PC games through LaunchBox (not just emulated games), this is a gap. Options:
- Add a `catch_all` section to the manifest that defines parent-process-based matching as a fallback
- Accept this as out of scope and add explicit profiles per PC game title
- Revisit this once the core system is working

### LaunchBox XML emulator fields beyond strip_args and wrapper_bat
The current `launchbox_emulator` patch type in the manifest draft covers `wrapper_bat` and `strip_args`. Option 2 also sets per-emulator XML fields: `UseStartupScreen=false`, `StartupLoadDelay=0`, `HideMouseCursorInGame=false`. These should be included in the `launchbox_emulator` patch type as optional fields, otherwise the new system is missing behaviour the old one had.

### Cursor visibility
`launchbox_crt_watcher.py` calls `force_cursor_visible()` on every poll cycle. This prevents the cursor from disappearing while the watcher is active. The new system needs to replicate this or make it a manifest option (`"keep_cursor_visible": true`).

### BigBox as primary
The manifest's `primary` field points at a session profile. There is no reason it has to be LaunchBox — it could be `bigbox-session.json` for a full BigBox CRT session. This works automatically given the design; it just needs a BigBox session profile to be created and the manifest updated. Worth noting as an explicit future option.

### Multiple manifests
The manifest pattern naturally supports having more than one manifest file — for example, a `retro-gaming-manifest.json` for emulators and a `pc-gaming-manifest.json` for PC games with different emulators and patches. `crt_master.py` could offer both as separate menu options without any code changes.

### Manifest validation before patching
Before touching any files, `launch_session.py` should validate the manifest: check that all referenced session profiles exist, all patch target files exist, all wrapper bats exist. Report every missing file upfront rather than failing mid-patch.

### Debug logging
The generic wrapper has per-slug rotating debug logs. `launch_session.py` should have something equivalent — a session log that captures which patches were applied, which windows were found and moved, and the full exit sequence. Useful for diagnosing why a specific emulator didn't move.

### Migration path from option 2 to option 3
When option 3 is confirmed working, retiring option 2 means removing the menu entry. Before that, it may be worth running both options simultaneously in separate terminal windows to compare behaviour side by side. The two options are independent enough that this is safe — they use separate scripts and separate backup directories.

---

## Comparison

| | Option 2 (keep) | Option 3 (build) |
|---|---|---|
| Config patching | Yes — hardcoded in Python | Yes — data-driven from manifest |
| Window watching | Hardcoded process list | Profile-driven |
| Adding an emulator | Edit Python files | Add JSON block + create profile |
| Per-emulator rect | Single shared CRT rect for all | Each profile has its own rect |
| Restore on exit | File backup restore + window move | File backup restore + window move |
| Risk on crash | Configs left in patched state | Same — configs left in patched state |
| Stop flag handshake | Yes | Must be implemented |

---

## Build Order

This is subject to change as design is finalised. Nothing is built until the design is agreed.

1. Finalise manifest schema (patch types, all fields including missing XML emulator fields)
2. Create missing session profiles (`dolphin-session.json`, `ppsspp-session.json`, `pcsx2-session.json`)
3. Create `profiles/gaming-manifest.json` with all patches and watch list
4. Build `session/window_utils.py` — extract shared Win32 helpers from `launch_generic.py`; update `launch_generic.py` to import from it
5. Build `session/backup.py` — generic file backup and restore
6. Build `session/patches/retroarch.py` — RetroArch cfg format handler
7. Build `session/patches/launchbox.py` — LaunchBox XML handler
8. Build `session/patcher.py` — coordinator that dispatches to patch handlers and calls backup
9. Build `session/manifest.py` — manifest loading, validation, file existence checks
10. Build `session/watcher.py` — multi-target poll loop using `window_utils.py`
11. Build `launch_session.py` — thin orchestrator wiring all modules together
12. Wire option 3 in `crt_master.py` to `launch_session.py --manifest profiles/gaming-manifest.json`
13. Test option 3 alongside option 2
14. Retire option 2 when option 3 is confirmed stable
