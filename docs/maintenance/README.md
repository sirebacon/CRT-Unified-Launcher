# Maintenance Docs

Status: Active maintainer reference for the current codebase.

This section is for day-2 operations: where code lives, what each module owns, and what to retest after edits.

## Files

- `docs/maintenance/component-map.md`
  - Canonical map of launchers, session modules, media providers, tools, integrations, configs, runtime artifacts, owner tags, and dependency diagrams.
- `docs/maintenance/change-impact-checklist.md`
  - Edit-to-test matrix so maintainers can quickly validate the right flows after making changes.

## Fast Workflow

1. Find the subsystem in `component-map.md`.
2. Make changes in the owning module only (keep cross-module coupling minimal).
3. Run the corresponding checks from `change-impact-checklist.md`.
4. If behavior changed, update runbooks under `docs/runbooks/` and the architecture summary in `docs/architecture.md`.

## Scope Note

`integrations/aniwatch-js/node_modules/` is vendored dependency content. Do not document or edit individual files there unless dependency debugging requires it.
