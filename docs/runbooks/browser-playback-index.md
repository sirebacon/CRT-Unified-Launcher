# Browser Playback Modes - Index (Multi-Site)

## Status

Design only. Not implemented yet in launcher/provider code.

## Purpose

This index defines the modular documentation structure for browser playback modes that can
be reused across browser-only providers. Mode A and Mode B both
inherit shared contracts and launcher integration rules from the core doc.

## Read Order

1. Core (shared contract + architecture):
   - `docs/runbooks/browser-playback-core.md`
2. Mode A (system browser):
   - `docs/runbooks/browser-playback-mode-a-system-browser.md`
3. Mode B (Playwright fullscreen):
   - `docs/runbooks/browser-playback-mode-b-playwright.md`

## Inheritance Model

Both Mode A and Mode B inherit from the core document:

- provider directive contract
- launcher dispatch behavior
- config hierarchy and defaults
- logging/error conventions
- test gates and rollout sequencing rules

Mode-specific docs define only:

- launch implementation details
- mode-only config keys
- mode-only failure handling

Current agreed direction:

- Mode A: prioritize stable system-browser launch with re-anchor-to-internal-monitor support.
- Mode B: prioritize NOW PLAYING control integration via Playwright key bridge.

## Multi-Site Scope

These modes are intended for any provider that cannot use direct mpv playback reliably.
Each site is onboarded via a profile entry (window matching, key mappings, wait/fullscreen
strategy), not by duplicating mode logic.

## Modular Rule

Implementation must keep launch modes isolated:

- no mode-specific logic inside provider URL detection
- no hard-coupling Playwright code into Mode A path
- launcher dispatch remains mode-agnostic and driven by provider directive
