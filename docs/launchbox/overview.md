# LaunchBox / BigBox Integration Overview

## Purpose

Run LaunchBox/BigBox on the primary display while automatically moving launched emulator windows to CRT coordinates.

## Primary Integration: Session Mode (Option 3)

Session mode is the recommended approach. It handles everything in one flow:

1. Patches emulator configs (`retroarch.cfg`, `Emulators.xml`, `BigBoxSettings.xml`, `Settings.xml`).
2. Launches LaunchBox/BigBox on the main screen.
3. Monitors for emulator processes — moves their windows to the CRT as soon as they appear.
4. Restores all configs when the session ends.

Emulator wrapper scripts (under `integrations/launchbox/wrapper/`) are also part of this integration. The session patches `Emulators.xml` to point LaunchBox at these wrappers, which then handle per-game window stabilization during emulator startup.

See `docs/usage.md` for day-to-day workflow. See `docs/architecture.md` for the full component breakdown.

## Emulator Wrapper Scripts

Location: `integrations/launchbox/wrapper/`

Each emulator has a `.bat` file that LaunchBox calls as its `ApplicationPath`. The bat file invokes `launchbox_generic_wrapper.py` with the appropriate arguments for that emulator.

The generic wrapper:
- Launches the emulator and forwards the ROM path from LaunchBox.
- Locks the emulator window to the CRT rect during the startup period.
- Stops enforcing when the lock timeout expires or when `wrapper_stop_enforce.flag` is present (written by the session watcher on soft stop or shutdown).

For per-game profiles (GOG titles, etc.), see `integrations/launchbox/wrapper/profiles/`.

Full wrapper documentation: `docs/launchbox/generic-wrapper.md`

## Legacy Watcher Mode (Option 2)

`launchbox_crt_watcher.py` — an older single-script watcher that uses hardcoded process logic. Still functional. Use it if session mode does not suit your workflow.

## Known Limitations

- Steam and GOG games launched through their parent launcher will not be tracked unless their process name is listed in a watch profile.
- Two instances of the same emulator: only the first (by PID) is tracked.
