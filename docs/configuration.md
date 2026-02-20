# Configuration

Primary config file: `crt_config.json`

## Current Structure

The file commonly contains:

- app blocks:
  - `retroarch`
  - `plex`
  - `ppsspp`
  - `dolphin`
  - `pcsx2`
- shared integration block:
  - `launcher_integration`

Each app block may define:

- `path`: executable path
- `dir`: working directory
- optional per-app geometry: `x`, `y`, `w`, `h`

`launcher_integration` commonly defines:

- default target geometry
- polling cadence
- target/parent/ignore process lists
- `primary_on_exit` geometry

## Geometry Notes

- Negative `x` or `y` values are expected if CRT is positioned left/up of primary monitor in Windows display layout.
- Prefer keeping one known-good baseline geometry in `launcher_integration` and overriding only where needed.

## Process Matching Notes

- `target_processes` should include known executable names that should move to CRT.
- `target_parent_processes` supports platform launchers (Steam/GOG).
- `ignore_processes` should include LaunchBox/BigBox and system processes to prevent accidental moves.

## Scaling Direction

Current pressure: central file grows as game-specific needs increase.

Target direction:

- keep `crt_config.json` global/shared
- move game-specific launch behavior into profile files consumed by generic wrapper

Roadmap: `docs/roadmaps/generic-wrapper-scaling-todo.md`
