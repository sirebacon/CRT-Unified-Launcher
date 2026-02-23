# Usage

## Starting the Launcher

```powershell
python crt_station.py
```

Menu options:

```
1. [GAMING] Launch RetroArch
2. [GAMING] Launch LaunchBox CRT Watcher
3. [GAMING] Launch LaunchBox (Session)
4. [CINEMA] Launch Plex
5. [GAMING] Launch Resident Evil (Manual Mode)
6. [TOOLS]  Open Tools Menu
7. [EXIT]   Close Menu
```

---

## Option 3 - LaunchBox Gaming Session (Recommended)

The primary gaming workflow. Patches emulator configs, launches LaunchBox/BigBox, and moves emulator windows to the CRT as you play.

### Normal start (LaunchBox not running)

1. Select option 3.
2. The launcher patches `retroarch.cfg`, `Emulators.xml`, and BigBox/LaunchBox settings.
3. LaunchBox opens on the main screen.
4. Launch a game from BigBox - the emulator window moves to the CRT automatically.
5. When done: press `Ctrl+C` to end the session (see below).

### Reattach (LaunchBox already running)

If LaunchBox/BigBox is already open, option 3 reattaches the watcher. Emulator configs are still patched. No new LaunchBox instance is launched.

### Ctrl+C behaviour

- Single `Ctrl+C` - soft stop: moves all emulator windows back to the main screen and pauses tracking. Session stays alive. BigBox remains open so you can launch another game.
- Second `Ctrl+C` within 8 seconds - full shutdown: ends the session, restores all configs.

When you close an emulator (quit a game) after a soft stop, tracking for that emulator automatically resumes for the next launch.

### Dry-run validation

Before running a live session, verify the manifest and patches:

```powershell
python validate_session.py --manifest profiles/gaming-manifest.json
```

This backs up, patches, and immediately restores - no permanent changes.

For updating/tuning already-profiled apps, see `docs/configuration.md`:
- `Updating Already Profiled Applications`

---

## Option 5 - Resident Evil (Manual Mode)

This is the current supported Resident Evil workflow.

What manual mode does:

1. Ensures Moonlight is running and the Moonlight virtual display (VDD) is attached.
2. Opens the selected RE game folder and Windows Display Settings.
3. Prompts you to manually set display resolutions and primary display.
4. Verifies the expected 3-display setup.
5. Moves Moonlight to the CRT and switches audio to the CRT device.
6. Waits for you to launch the RE game manually.
7. On game exit or `Ctrl+C`, moves Moonlight back and restores audio.

Notes:

- You still restore the primary display manually after the session.
- Automatic RE mode (`start`) remains in the codebase but is on hold due to inconsistent behavior.

Direct command equivalent:

```powershell
python launch_resident_evil_stack.py manual --game re1
```

Use `re2` or `re3` for the other games.

---

## Option 6 - Tools Menu

The Tools submenu contains:

1. Restore Default Settings
2. Recover Resident Evil Stack
3. Restore Display & Audio
4. Back

Use these for recovery/maintenance tasks.

---

## Option 1 - RetroArch Standalone

Launches RetroArch directly using the `retroarch-session.json` profile and locks its window to the CRT for the duration.

## Option 2 - LaunchBox CRT Watcher (Legacy)

The older watcher approach. Launches LaunchBox and monitors for game windows using hardcoded process logic. Still functional but option 3 is preferred.

## Option 4 - Plex

Launches Plex Desktop and locks its window to the CRT. `Ctrl+C` restores the window and exits.

## Tools Menu - Restore Default Settings

Restores backed-up config files (retroarch.cfg, Emulators.xml, etc.) from the most recent backup without starting a session. Use this if a session exited uncleanly and configs were not restored.

## Tools Menu - Recover Resident Evil Stack

Runs `python launch_resident_evil_stack.py restore` as a recovery command for interrupted RE sessions or older automatic-mode sessions.

## Tools Menu - Restore Display & Audio

Attempts to restore the primary display and audio defaults using the RE stack restore helpers.

---

## Calibration Utilities

Window inspector (find process/class/title info):

```powershell
python tools\inspectRetro.py
```

Plex live calibration:

```powershell
python tools\plex_callibrate.py
```

