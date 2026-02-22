# Resident Evil Stack Rationale (Why It Exists, Why Manual Mode)

Date: 2026-02-22

## Purpose

This document explains:

1. Why the Resident Evil stack exists
2. What problem it solves in this setup
3. Why manual mode is the current supported workflow
4. Why automatic mode is on hold

## Why A Dedicated Resident Evil Stack Exists

Resident Evil 1/2/3 (GOG) in this setup are not a normal "launch emulator and move one window" case.

They require coordination across:

- Moonlight (client window)
- Apollo / virtual display (SudoMaker VDD)
- Windows multi-monitor topology
- CRT output / refresh behavior
- Audio output routing
- Game launcher/config windows before gameplay

The standard LaunchBox / generic CRT workflows were not enough by themselves because Resident Evil behavior depends heavily on where Windows thinks the primary display is and when gameplay actually begins.

## What Problem The RE Stack Solves

The RE stack exists to make a repeatable CRT launch workflow for RE1/RE2/RE3 that:

- gets Moonlight and the virtual display into a usable state
- keeps setup/config screens visible while you prepare the game
- moves Moonlight to the CRT at the right time
- routes audio to the CRT output during play
- returns Moonlight/audio after the session

Without a dedicated flow, the process was too easy to break:

- wrong display selected
- wrong monitor primary
- Moonlight window on the wrong screen
- audio not on the CRT output
- inconsistent restore behavior after exit

## Why Manual Mode Is The Supported Workflow

Manual mode is supported because it is consistently usable on the real machine.

What manual mode does well:

- Automates the stable parts:
  - Moonlight launch check
  - VDD presence check
  - RE folder opening and placement
  - display verification (3 monitors expected)
  - Moonlight move to CRT
  - audio switch to CRT
  - Moonlight/audio restore on game exit or `Ctrl+C`
- Leaves the fragile parts to the user:
  - exact display resolution setup
  - primary display selection
  - game launch timing

This split is intentional. It keeps the workflow reliable while still removing repetitive setup work.

## Why Automatic Mode Is On Hold

Automatic mode was built to do more:

- switch primary display automatically
- enforce refresh automatically
- detect gameplay window timing
- move Moonlight automatically based on gameplay detection
- restore automatically

In practice, this was too finicky/inconsistent in this environment.

Main reasons:

- Windows display topology changes can shift desktop coordinates unexpectedly
- virtual display driver behavior is timing-sensitive
- primary-display switching is not consistently reliable across driver states
- refresh reporting/correction (`59` vs `60`) can be inconsistent
- Moonlight/window placement can succeed technically but still land wrong visually

The result was that "automation succeeded" did not always mean "the session is correct on the CRT."

That is the key reason manual mode is preferred: it reduces the number of unstable transitions and lets the user directly confirm the display state before the script continues.

## Decision Summary

Current decision:

- Use **manual mode** as the default/supported Resident Evil workflow
- Keep **automatic mode** in the codebase but treat it as on hold / legacy for now

Why this is the right tradeoff:

- better consistency
- easier troubleshooting
- faster real-world setup than repeatedly fixing failed automation
- preserves future option to revisit automation later

## Future Revisit Criteria (If We Return To Auto Mode)

Automatic mode should only be revisited if it becomes measurably reliable.

Minimum bar:

- repeatable display topology switching
- repeatable Moonlight placement on CRT
- exact/verified refresh behavior
- clean restore behavior across repeated runs

Until then, manual mode is the practical path.

