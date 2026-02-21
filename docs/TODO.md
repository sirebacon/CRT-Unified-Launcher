# TODO

Single source of truth for active work items.

## Now (High Priority)

- [ ] Verify per-core RetroArch overrides for line/edge artifacts on problematic systems.
- [ ] Update `docs/video-stack/measurements.md` with current confirmed RetroArch rect (`x=-1221` if still correct).
- [ ] Record actual OSSC/VoidScaler output mode observed in normal play (best-effort note, even if firmware visibility is limited).
- [ ] Validate option 3 session flow end-to-end after latest Ctrl+C behavior changes:
  - single Ctrl+C soft stop
  - second Ctrl+C (within 8s) full shutdown
  - config restore success

## Next (Medium Priority)

- [ ] Tighten emulator profile filters (`process_name`, `class_contains`, `title_contains`) for Dolphin/PPSSPP/PCSX2 with live `--debug` testing.
- [ ] Decide whether to support parent-process fallback matching (Steam/GOG launcher chains) in option 3.
- [ ] Document known-good per-core RetroArch settings in a compact reference table.

## Later (Low Priority)

- [ ] Evaluate retiring option 2 (legacy watcher) only after option 3 parity is confirmed in real use.
- [ ] Add a small automated smoke test checklist doc for every release/update.

## Notes

- Prefer measured behavior over listing/spec claims when they conflict.
- Keep CRT hardware baseline fixed; tune per-core/per-profile first.
