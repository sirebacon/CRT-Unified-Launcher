# Usage

## Starting the Launcher

```powershell
python crt_master.py
```

Menu options:

```
1. [GAMING] Launch RetroArch
2. [GAMING] Launch LaunchBox CRT Watcher
3. [GAMING] Launch LaunchBox (Session)
4. [CINEMA] Launch Plex
5. [TOOLS]  Restore Default Settings
6. [EXIT]   Close Menu
```

---

## Option 3 — LaunchBox Gaming Session (Recommended)

The primary gaming workflow. Patches emulator configs, launches LaunchBox/BigBox, and moves emulator windows to the CRT as you play.

### Normal start (LaunchBox not running)

1. Select option 3.
2. The launcher patches `retroarch.cfg`, `Emulators.xml`, and BigBox/LaunchBox settings.
3. LaunchBox opens on the main screen.
4. Launch a game from BigBox — the emulator window moves to the CRT automatically.
5. When done: press Ctrl+C to end the session (see below).

### Reattach (LaunchBox already running)

If LaunchBox/BigBox is already open, option 3 reattaches the watcher. Emulator configs are still patched. No new LaunchBox instance is launched.

### Ctrl+C behaviour

- **Single Ctrl+C** — soft stop: moves all emulator windows back to the main screen and pauses tracking. Session stays alive. BigBox remains open so you can launch another game.
- **Second Ctrl+C within 5 seconds** — full shutdown: ends the session, restores all configs.

When you close an emulator (quit a game) after a soft stop, tracking for that emulator automatically resumes for the next launch.

### Dry-run validation

Before running a live session, verify the manifest and patches:

```powershell
python validate_session.py --manifest profiles/gaming-manifest.json
```

This backs up, patches, and immediately restores — no permanent changes.

---

## Option 1 — RetroArch Standalone

Launches RetroArch directly using the `retroarch-session.json` profile and locks its window to the CRT for the duration.

---

## Option 2 — LaunchBox CRT Watcher (Legacy)

The older watcher approach. Launches LaunchBox and monitors for game windows using hardcoded process logic. Still functional but option 3 is preferred.

---

## Option 4 — Plex

Launches Plex Desktop and locks its window to the CRT. Ctrl+C restores the window and exits.

---

## Option 5 — Restore Default Settings

Restores backed-up config files (retroarch.cfg, Emulators.xml, etc.) from the most recent backup without starting a session. Use this if a session exited uncleanly and configs were not restored.

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
