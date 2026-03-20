# CRT Station GUI Launcher — Design Document

## Overview

A graphical replacement for `crt_station.py` that presents the same launcher options
in a window-based UI, startable by double-clicking a single `.exe` file. The CLI
backend scripts (`launch_*.py`, `crt_tools.py`, etc.) are **unchanged** — the GUI is
purely a front-end shell that calls the same subprocesses.

---

## Goals

- One-click launch from the desktop (no terminal window required)
- Visual parity with all 10 main-menu actions and the 11 CRT Tools sub-actions
- Live output panel for long-running operations (display restore, RE stack, etc.)
- Single self-contained `.exe` (PyInstaller one-file bundle)
- No changes to any backend Python scripts

## Non-Goals

- Re-implementing any launcher logic inside the GUI
- Replacing the terminal for interactive sub-menus that require input (e.g. RE game selector handled in-GUI instead)
- Cross-platform support (Windows only)

---

## Recommended Stack

| Concern | Choice | Reason |
|---|---|---|
| GUI framework | **CustomTkinter** | Modern dark-themed widgets; pure Python; pip-installable; no C++ build tools needed |
| Packaging | **PyInstaller** | Mature, well-documented, handles hidden imports; `--onefile` gives a single exe |
| Icon | `.ico` file in `assets/` | Embedded via PyInstaller `--icon` flag |

Install deps:
```
pip install customtkinter pyinstaller
```

---

## UI Layout

```
┌──────────────────────────────────────────────────────┐
│  🎮  CRT STATION                          [─] [□] [×] │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ╔════════════ GAMING ════════════╗                  │
│  ║  [  Launch RetroArch         ] ║                  │
│  ║  [  Launch LaunchBox         ] ║                  │
│  ║  [  Launch Resident Evil ▾   ] ║  ← dropdown      │
│  ╚═══════════════════════════════╝                  │
│                                                      │
│  ╔════════════ CINEMA ════════════╗                  │
│  ║  [  Launch Plex               ] ║                  │
│  ║  [  Launch Media (YT/Anime)   ] ║                  │
│  ║  [  Launch Live TV (VLC)      ] ║                  │
│  ╚═══════════════════════════════╝                  │
│                                                      │
│  ╔════════════  TOOLS  ════════════╗                 │
│  ║  [  CRT Tools ▾               ] ║  ← opens panel  │
│  ║  [  Restore Default Settings  ] ║                  │
│  ║  [  Recover RE Stack          ] ║                  │
│  ╚════════════════════════════════╝                  │
│                                                      │
│  ┌──────────── Output ───────────────────────────┐  │
│  │ > Restoring display for gaming session...      │  │
│  │ > Display restore: OK                          │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│                             [  Close Menu  ]         │
└──────────────────────────────────────────────────────┘
```

### Resident Evil dropdown
Clicking "Launch Resident Evil ▾" opens an inline selector (radio buttons or
`CTkOptionMenu`):
```
  ○ RE1 (GOG)
  ○ RE2 (GOG)
  ● RE3 (GOG)      [Launch]  [Cancel]
```

### CRT Tools panel
Clicking "CRT Tools ▾" expands a collapsible section in-place (or a separate
`CTkToplevel` window) with buttons for all 11 sub-actions. Each action streams
output into the shared Output panel.

---

## File Structure

```
CRT-Unified-Launcher/
├── crt_station_gui.py          ← new GUI entry point
├── gui/
│   ├── __init__.py
│   ├── app.py                  ← CTk App class, window setup
│   ├── main_panel.py           ← button layout (3 groups)
│   ├── tools_panel.py          ← CRT Tools sub-panel
│   ├── re_selector.py          ← RE game picker dialog
│   ├── output_panel.py         ← scrollable live output widget
│   └── subprocess_runner.py    ← threaded subprocess wrapper
├── assets/
│   ├── crt_station.ico         ← window icon (create from any 256×256 PNG)
│   └── crt_green_theme.json    ← CustomTkinter color theme (phosphor-green palette)
├── build_exe.bat               ← one-command PyInstaller build
└── crt_station_gui.spec        ← PyInstaller spec (auto-generated, then edited)
```

`crt_station.py` is kept as-is for terminal fallback.

---

## Core Component: `subprocess_runner.py`

All backend calls are **non-blocking** — they run in a `threading.Thread` and pipe
stdout/stderr line-by-line into the Output panel. Buttons are disabled while a job runs.

```python
import subprocess, sys, threading

class SubprocessRunner:
    def __init__(self, output_callback, done_callback=None):
        self._cb = output_callback      # callable(line: str)
        self._done = done_callback      # callable(returncode: int) | None
        self._proc = None

    def run(self, cmd: list[str]):
        """Launch cmd in a background thread, stream output line-by-line."""
        def _worker():
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in self._proc.stdout:
                self._cb(line.rstrip())
            self._proc.wait()
            if self._done:
                self._done(self._proc.returncode)
        threading.Thread(target=_worker, daemon=True).start()

    def terminate(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
```

Callers pass `[sys.executable, "launch_plex.py", ...]` — same commands as the CLI.

---

## Core Component: `output_panel.py`

```python
import customtkinter as ctk

class OutputPanel(ctk.CTkFrame):
    MAX_LINES = 200

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._text = ctk.CTkTextbox(self, state="disabled", wrap="word",
                                    font=("Consolas", 11))
        self._text.pack(fill="both", expand=True, padx=4, pady=4)

    def append(self, line: str):
        self._text.configure(state="normal")
        self._text.insert("end", line + "\n")
        # trim to MAX_LINES
        lines = int(self._text.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            self._text.delete("1.0", f"{lines - self.MAX_LINES}.0")
        self._text.configure(state="disabled")
        self._text.see("end")

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
```

---

## Main App (`app.py` sketch)

```python
import customtkinter as ctk, sys, os
from gui.main_panel import MainPanel
from gui.output_panel import OutputPanel

WORKING_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

class CRTStationApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("assets/crt_green_theme.json")

        self.title("CRT Station")
        self.geometry("520x640")
        self.resizable(False, True)

        # Change to launcher directory so all relative paths resolve
        os.chdir(WORKING_DIR)

        self.output = OutputPanel(self, height=160)
        self.output.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.panel = MainPanel(self, output=self.output)
        self.panel.pack(side="top", fill="both", expand=True, padx=10, pady=10)
```

---

## Button Action Map

| Button | Subprocess command |
|---|---|
| Launch RetroArch | `[python, "launch_generic.py", "--profile-file", "profiles/retroarch-session.json"]` |
| Launch LaunchBox | `[python, "crt_tools.py", "display", "restore", "--force"]` then `[python, "launch_session.py", "--manifest", "profiles/gaming-manifest.json", "--debug"]` |
| Launch Plex | `[python, "launch_plex.py", "--preset", "default"]` |
| Launch Media | `[python, "launch_youtube.py"]` |
| Launch Live TV | `[python, "launch_live_tv.py"]` |
| Launch RE (game) | `[python, "launch_resident_evil_stack.py", "manual", "--game", "<re1|re2|re3>"]` |
| Display Dump | `[python, "crt_tools.py", "display", "dump"]` |
| Config Dump | `[python, "crt_tools.py", "config", "dump"]` |
| Config Check | `[python, "crt_tools.py", "config", "check"]` |
| Prereqs Check | `[python, "crt_tools.py", "prereqs"]` |
| Window List | `[python, "crt_tools.py", "window", "list", "--filter", "moonlight"]` |
| Audio Status | `[python, "crt_tools.py", "audio", "status"]` |
| Session Log | `[python, "crt_tools.py", "session", "log", "--lines", "40"]` |
| Session Processes | `[python, "crt_tools.py", "session", "processes"]` |
| LB RetroArch Status | inline XML check (replicate `show_launchbox_retroarch_status`) |
| Restore Display/Audio | `[python, "crt_tools.py", "display", "restore", "--force"]` then audio |
| Restore Defaults | `[python, "crt_station.py", "--restore-defaults"]` *(see note)* |
| Recover RE Stack | `[python, "launch_resident_evil_stack.py", "restore"]` |

> **Restore Defaults note:** `restore_defaults_from_backup()` is currently inline in
> `crt_station.py`. Extract it to a standalone CLI entry point
> (`crt_tools.py restore-defaults`) so the GUI can call it as a subprocess.

---

## Executable Build (`build_exe.bat`)

```bat
@echo off
cd /d %~dp0
pyinstaller ^
  --onefile ^
  --windowed ^
  --icon assets\crt_station.ico ^
  --name "CRT Station" ^
  --add-data "assets;assets" ^
  crt_station_gui.py
echo.
echo Build complete: dist\CRT Station.exe
pause
```

**`--windowed`** suppresses the console window entirely (the Output panel in the GUI
replaces it). Remove this flag temporarily if you need to debug startup crashes.

### Hidden imports to add if PyInstaller misses them

Add to `build_exe.bat` or `.spec`:
```
--hidden-import customtkinter
--hidden-import PIL._tkinter_finder
```

### What is NOT bundled

The `.exe` bundles only the GUI code and CustomTkinter. All backend `.py` scripts,
JSON configs, and runtime assets stay as loose files in the launcher directory.
PyInstaller's `--onefile` is for the GUI entry point only — the working directory
must still contain the full project tree.

The resulting workflow:
```
D:\Emulators\CRT-Unified-Launcher\
  "CRT Station.exe"     ← double-click this (can pin to taskbar / Start)
  crt_station_gui.py
  gui\...
  launch_*.py
  crt_tools.py
  ...
```

---

## Migration Path (step-by-step)

1. `pip install customtkinter pyinstaller`
2. Create `gui/` package with stubs, wire up `app.py`
3. Implement `output_panel.py` and `subprocess_runner.py` first — test with one button
4. Implement `main_panel.py` (3 group frames, all buttons)
5. Implement `tools_panel.py` (collapsible or separate window)
6. Implement `re_selector.py` (small `CTkToplevel` dialog)
7. Add `assets/crt_station.ico`
8. Run `build_exe.bat`, test `dist/CRT Station.exe`
9. Create desktop shortcut pointing to `dist/CRT Station.exe`

---

## Design Decisions

| # | Decision |
|---|---|
| 1 | **CRT Tools → separate `CTkToplevel` popup.** Simpler to implement; keeps the main window uncluttered. |
| 2 & 3 | **GUI always stays open.** Every action streams output to the OutputPanel, exactly like the CLI does. No hide/minimize behaviour. |
| 4 | **No system tray icon.** Adds `pystray` dependency for marginal benefit; the taskbar button is sufficient. |
| 5 | **Phosphor-green CRT aesthetic.** Custom `CTkTheme` JSON with green accents on near-black background. Fits the project name and CRT hardware context. |

All actions stay open and stream output to the OutputPanel — same behaviour as the CLI.
