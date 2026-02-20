# Runbook: Resident Evil GOG — CRT Display Issue

## Summary

The GOG versions of RE1, RE2, and RE3 cannot be redirected to a secondary CRT monitor
by moving their windows with `SetWindowPos`. This is a fundamental limitation of the
DirectDraw engine used by these 1997-era PC ports.

## What We Tested

Tested RE1 (`Biohazard.exe`) via `launchbox_generic_wrapper.py --profile-file re1-gog.json --debug`.

### Window sequence observed

1. Config menu window — small Win32 dialog (~339×418), spawns on primary monitor
2. Mod selection window — small Win32 dialog (~467×307), spawns on primary monitor
3. Game window — small pre-init Win32 window (~431×347), spawns on primary monitor,
   then jumps to fullscreen resolution (1286×1000 or 1707×1067) once DirectX initializes

The wrapper successfully snapped windows 1 and 2 to the CRT rect.

### Full rect enforcement (original behavior)

With full rect enforcement active during game window initialization:
- Wrapper moved game window to CRT rect
- Game fought back to its fullscreen size
- Repeated `SetWindowPos` calls during DirectX initialization caused an access violation crash
- Exit code: `3221225477` (0xC0000005, STATUS_ACCESS_VIOLATION)

### Position-only enforcement (`position_only: true`)

With `SWP_NOSIZE` — only x,y enforced, size left to the game:
- No crash
- Game window frame moved to CRT (x=-1211)
- Game rendered black on CRT, actual game content rendered on primary monitor

## Root Cause

These games use **DirectDraw exclusive fullscreen**. DirectDraw exclusive fullscreen always
renders to the **Windows primary display**, regardless of where the window is positioned.
`SetWindowPos` moves the window chrome/frame but does not redirect the DirectDraw render
surface to a different display adapter.

This is a hardware/driver-level binding, not a window position issue. No amount of
`SetWindowPos` manipulation will fix it.

## What Does Not Work

- Full rect enforcement → crash (access violation during DirectX init)
- Position-only enforcement (`SWP_NOSIZE`) → no crash, but rendering stays on primary monitor
- Shortening `max_lock_seconds` → still crashes if enforcement is active during DX init
- Any window-move approach → cannot redirect a DirectDraw render surface

## What Would Fix It

### Option 1 — Windowed mode (preferred if available)

If the game's CONFIGURATION tool has a windowed mode toggle:
- Enable windowed mode
- The game renders inside its window, wherever the window is
- The wrapper can then position it correctly on the CRT
- **Status: unknown — need to check RE1/RE2/RE3 config menus for windowed option**

### Option 2 — Set CRT as Windows primary display

DirectDraw exclusive fullscreen goes to the primary display by definition.
If the CRT is made the primary monitor in Windows display settings, the game renders
there with no wrapper intervention needed. The wrapper would still be useful for
getting the config/mod selection menus onto the CRT during startup.

- **Status: viable but requires changing Windows display settings per session**

### Option 3 — Game config files

Some GOG releases store display adapter or window position settings in INI files,
registry keys, or other config files in the game directory. If found, these could
be used to hardcode the game to the correct display.

- **Status: not yet investigated — check `D:\GOG Galaxy\Games\Resident Evil\` for INI/CFG files**

## Current Profile State

All three profiles (`re1-gog.json`, `re2-gog.json`, `re3-gog.json`) have:

```json
"position_only": true
```

This prevents the crash but does not fix rendering. The config and mod selection menus
are correctly snapped to the CRT. The game window is moved to CRT coordinates but
renders on the primary monitor.

**RE2 and RE3 have not been live-tested yet.** They likely have the same root cause
but should be confirmed.

## Next Steps

1. Check RE1/RE2/RE3 CONFIGURATION menus for a windowed mode option.
2. Check game directories for INI or CFG files with display settings.
3. If neither yields a solution, evaluate making the CRT the Windows primary display.
