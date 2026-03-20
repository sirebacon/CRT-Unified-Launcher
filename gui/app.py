"""
CRTStationApp — the top-level tkinter application.

Navigation model:
  A navigation stack drives all panel switching.  Every panel is a
  CTkScrollableFrame that lives inside a shared *content area* frame.
  Only one panel is pack()ed at a time.

      _navigate_to(panel, title)  — push current panel, show new one
      _navigate_back()            — pop stack, return to previous panel

  A nav bar (Back button + current title) is shown whenever the stack
  is non-empty (i.e. any time the main menu is not the active panel).

  Adding a new submenu:
    1. Create a new *Panel class (CTkScrollableFrame + set_enabled())
    2. Instantiate it in _build_ui(), add to self._all_panels
    3. Define its _<name>_actions() method
    4. Call self._navigate_to(panel, "TITLE") from the relevant action

Run model:
  run()            — run one command, stream output, show busy state
  run_sequence()   — run a list of commands serially
  _run_next_step() — internal recursive driver for run_sequence()
  _set_busy()      — lock/unlock ALL panels, toggle Stop / Back buttons
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

import customtkinter as ctk

from gui.constants import LAUNCHER_DIR, LAUNCHBOX_EMULATORS_XML, PYTHON_EXE, PROFILES, SCRIPTS
from gui.main_panel import MainPanel, ActionMap
from gui.tools_panel import ToolsPanel
from gui.re_panel import REPanel
from gui.output_panel import OutputPanel
from gui.subprocess_runner import SubprocessRunner
from gui.theme import THEME_PATH, FONT_SECTION, GREEN_MID

_GEOMETRY_FILE = os.path.join(LAUNCHER_DIR, "runtime", "gui_geometry.json")


class CRTStationApp(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        theme = THEME_PATH if os.path.exists(THEME_PATH) else "dark-blue"
        ctk.set_default_color_theme(theme)

        super().__init__()

        os.chdir(LAUNCHER_DIR)

        self.title("CRT Station")
        self.geometry("620x820")
        self.minsize(480, 560)
        self.resizable(True, True)

        self.runner = SubprocessRunner()

        # Navigation state — populated in _build_ui
        self._nav_history: list[tuple[ctk.CTkWidget, str]] = []
        self._active_panel: ctk.CTkWidget | None = None
        self._all_panels:   list = []   # every panel that has set_enabled()

        self._build_ui()
        self._load_geometry()

        self.bind_all("<Control-c>", self._on_ctrl_c)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ---- Shared content area ----------------------------------------
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        # Nav bar — hidden while main menu is active
        self._nav_bar = ctk.CTkFrame(self._content, fg_color="transparent")
        self._back_btn = ctk.CTkButton(
            self._nav_bar, text="← Back", width=90, height=32,
            command=self._navigate_back,
        )
        self._back_btn.pack(side="left", padx=(0, 10))
        self._nav_title_label = ctk.CTkLabel(
            self._nav_bar, text="", font=FONT_SECTION, text_color=GREEN_MID
        )
        self._nav_title_label.pack(side="left")

        # ---- Panels (only main is packed on startup) --------------------
        self._panel = MainPanel(
            self._content, actions=self._main_actions(), fg_color="transparent"
        )
        self._panel.pack(fill="both", expand=True)
        self._active_panel = self._panel

        self._tools_panel = ToolsPanel(
            self._content, actions=self._tool_actions(), fg_color="transparent"
        )

        self._re_panel = REPanel(
            self._content, actions=self._re_actions(), fg_color="transparent"
        )

        # Register all panels so _set_busy() can reach them
        self._all_panels = [self._panel, self._tools_panel, self._re_panel]

        # ---- Output toolbar --------------------------------------------
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=12, pady=(6, 2))

        ctk.CTkLabel(
            toolbar, text="Output", font=("Consolas", 11), text_color=GREEN_MID
        ).pack(side="left", padx=2)

        self._stop_btn = ctk.CTkButton(
            toolbar,
            text="■  Stop",
            width=90, height=28,
            fg_color=("#3a1a0a", "#3a1a0a"),
            hover_color=("#5a2a0a", "#5a2a0a"),
            text_color=("#ff6600", "#ff6600"),
            border_color=("#ff6600", "#ff6600"),
            border_width=1,
            state="disabled",
            command=self._stop_process,
        )
        self._stop_btn.pack(side="right", padx=2)

        ctk.CTkButton(
            toolbar, text="Copy", width=64, height=28,
            command=lambda: self._output.copy_to_clipboard(),
        ).pack(side="right", padx=2)

        ctk.CTkButton(
            toolbar, text="Clear", width=64, height=28,
            command=lambda: self._output.clear(),
        ).pack(side="right", padx=2)

        # ---- Output panel ---------------------------------------------
        self._output = OutputPanel(self)
        self._output.configure(height=200)
        self._output.pack(fill="both", expand=False, padx=12, pady=(0, 6))

        # ---- Close button ---------------------------------------------
        ctk.CTkButton(
            self, text="Close Menu", height=36, command=self._on_close
        ).pack(pady=(0, 14))

    # ------------------------------------------------------------------
    # Action maps — keep action definitions close to the panel they serve
    # ------------------------------------------------------------------

    def _main_actions(self) -> ActionMap:
        return {
            "retroarch":        self.action_retroarch,
            "launchbox":        self.action_launchbox,
            "resident_evil":    lambda: self._navigate_to(self._re_panel, "RESIDENT EVIL"),
            "plex":             self.action_plex,
            "media":            self.action_media,
            "live_tv":          self.action_live_tv,
            "crt_tools":        lambda: self._navigate_to(self._tools_panel, "CRT TOOLS"),
            "restore_defaults": self.action_restore_defaults,
            "recover_re":       self.action_recover_re,
        }

    def _tool_actions(self) -> ActionMap:
        crt = self._script("crt_tools")
        return {
            "display_dump":    lambda: self.run([PYTHON_EXE, crt, "display", "dump"]),
            "config_dump":     lambda: self.run([PYTHON_EXE, crt, "config", "dump"]),
            "config_check":    lambda: self.run([PYTHON_EXE, crt, "config", "check"]),
            "prereqs":         lambda: self.run([PYTHON_EXE, crt, "prereqs"]),
            "window_list":     lambda: self.run([PYTHON_EXE, crt, "window", "list", "--filter", "moonlight"]),
            "audio_status":    lambda: self.run([PYTHON_EXE, crt, "audio", "status"]),
            "session_log":     lambda: self.run([PYTHON_EXE, crt, "session", "log", "--lines", "40"]),
            "session_procs":   lambda: self.run([PYTHON_EXE, crt, "session", "processes"]),
            "lb_status":       self._lb_retroarch_status,
            "restore_display": self._restore_display_audio,
        }

    def _re_actions(self) -> ActionMap:
        return {
            "re1": lambda: self._launch_re("re1"),
            "re2": lambda: self._launch_re("re2"),
            "re3": lambda: self._launch_re("re3"),
        }

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_to(self, panel: ctk.CTkWidget, title: str) -> None:
        """Push the current panel onto the history stack and show *panel*."""
        # Save where we are now (and what title the nav bar currently shows)
        current_title = (
            self._nav_title_label.cget("text") if self._nav_history else ""
        )
        self._nav_history.append((self._active_panel, current_title))

        self._active_panel.pack_forget()
        self._active_panel = panel
        self._nav_title_label.configure(text=title)

        # Show nav bar on first navigation away from root
        if len(self._nav_history) == 1:
            self._nav_bar.pack(fill="x", pady=(0, 6))

        panel.pack(fill="both", expand=True)

    def _navigate_back(self) -> None:
        """Pop the history stack and return to the previous panel."""
        if not self._nav_history:
            return

        self._active_panel.pack_forget()
        prev_panel, prev_title = self._nav_history.pop()
        self._active_panel = prev_panel

        if self._nav_history:
            # Still inside a submenu — update the nav bar title
            self._nav_title_label.configure(text=prev_title)
        else:
            # Returned all the way to root — hide the nav bar
            self._nav_bar.pack_forget()

        prev_panel.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Busy state
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool, name: str = "") -> None:
        """Lock/unlock every registered panel and the nav/stop buttons."""
        for panel in self._all_panels:
            panel.set_enabled(not busy)
        self._back_btn.configure(state="disabled" if busy else "normal")
        self._stop_btn.configure(state="normal" if busy else "disabled")
        if busy and name:
            self.title(f"CRT Station  —  {name}")
        else:
            self.title("CRT Station")

    def _update_running_title(self, name: str) -> None:
        self.title(f"CRT Station  —  {name}")

    def _stop_process(self) -> None:
        self.runner.terminate()
        self._output.append_info("> Terminated by user (Ctrl+C)")

    def _on_ctrl_c(self, event=None) -> str | None:
        if self.runner.is_running:
            self._stop_process()
            return "break"
        return None

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def _load_geometry(self) -> None:
        try:
            with open(_GEOMETRY_FILE) as f:
                geo = json.load(f).get("geometry", "")
            if geo:
                self.geometry(geo)
        except Exception:
            pass

    def _save_geometry(self) -> None:
        try:
            os.makedirs(os.path.dirname(_GEOMETRY_FILE), exist_ok=True)
            with open(_GEOMETRY_FILE, "w") as f:
                json.dump({"geometry": self.geometry()}, f)
        except Exception:
            pass

    def _on_close(self) -> None:
        self._save_geometry()
        self.destroy()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _script(self, key: str) -> str:
        return os.path.join(LAUNCHER_DIR, SCRIPTS[key])

    def _profile(self, key: str) -> str:
        return os.path.join(LAUNCHER_DIR, PROFILES[key])

    # ------------------------------------------------------------------
    # Run primitives
    # ------------------------------------------------------------------

    def run(self, cmd: list[str], prefix: str | None = None) -> None:
        """Run *cmd*, stay open, stream output. Shows busy state throughout."""
        if self.runner.is_running:
            self._output.append_info("> A process is already running.")
            return

        name = os.path.basename(cmd[1]) if len(cmd) > 1 else cmd[0]
        self._set_busy(True, name)

        if prefix:
            self._output.append_info(prefix)

        def _done(rc: int) -> None:
            self._output.append_exit(rc)
            self.after(0, lambda: self._set_busy(False))

        self.runner.run(cmd, on_output=self._output.append, on_done=_done)

    def run_sequence(self, steps: list[dict]) -> None:
        """Run a list of commands serially, streaming each to the OutputPanel.

        Each step: {cmd: list[str], prefix: str (optional)}
        """
        if not steps:
            return
        if self.runner.is_running:
            self._output.append_info("> A process is already running.")
            return

        name = os.path.basename(steps[0]["cmd"][1])
        self._set_busy(True, name)
        self._run_next_step(steps)

    def _run_next_step(self, steps: list[dict]) -> None:
        """Internal serial runner — always called on the main thread."""
        if not steps:
            self._set_busy(False)
            return

        step, remaining = steps[0], steps[1:]
        self._update_running_title(os.path.basename(step["cmd"][1]))

        def _done(rc: int) -> None:
            self._output.append_exit(rc)
            self.after(0, lambda: self._run_next_step(remaining))

        if step.get("prefix"):
            self._output.append_info(step["prefix"])

        self.runner.run(step["cmd"], on_output=self._output.append, on_done=_done)

    # ------------------------------------------------------------------
    # Tool actions
    # ------------------------------------------------------------------

    def _restore_display_audio(self) -> None:
        crt = self._script("crt_tools")
        self.run_sequence([
            {"cmd": [PYTHON_EXE, crt, "display", "restore", "--force"], "prefix": "> Restoring display..."},
            {"cmd": [PYTHON_EXE, crt, "audio",   "restore", "--force"], "prefix": "> Restoring audio..."},
        ])

    def _lb_retroarch_status(self) -> None:
        self._output.clear()
        self._output.append_info("> Checking LaunchBox RetroArch path...")

        if not os.path.exists(LAUNCHBOX_EMULATORS_XML):
            self._output.append_info(f"ERROR: Emulators.xml not found:\n  {LAUNCHBOX_EMULATORS_XML}")
            return

        try:
            tree = ET.parse(LAUNCHBOX_EMULATORS_XML)
        except Exception as exc:
            self._output.append_info(f"ERROR: Failed to parse Emulators.xml: {exc}")
            return

        retro = None
        for em in tree.getroot().findall("Emulator"):
            if (em.findtext("Title") or "").strip().lower() == "retroarch":
                retro = em
                break

        if retro is None:
            self._output.append_info("RetroArch entry not found in Emulators.xml.")
            return

        app_path   = (retro.findtext("ApplicationPath") or "").strip()
        cmd_line   = (retro.findtext("CommandLine") or "").strip()
        is_wrapper = "launchbox_retroarch_wrapper" in app_path.lower()

        self._output.append_info(f"  ApplicationPath : {app_path or '(empty)'}")
        self._output.append_info(f"  CommandLine     : {cmd_line or '(empty)'}")
        if is_wrapper:
            self._output.append_info("  Status          : WRAPPER ACTIVE")
            self._output.append_info("  RetroArch launches through CRT wrapper.")
        else:
            self._output.append_info("  Status          : NORMAL (no CRT wrapper)")

    # ------------------------------------------------------------------
    # Actions — GAMING
    # ------------------------------------------------------------------

    def action_retroarch(self) -> None:
        self.run([
            PYTHON_EXE, self._script("generic_launcher"),
            "--profile-file", self._profile("retroarch_session"),
        ])

    def action_launchbox(self) -> None:
        self.run_sequence([
            {
                "cmd":    [PYTHON_EXE, self._script("crt_tools"), "display", "restore", "--force"],
                "prefix": "> Restoring display for gaming session...",
            },
            {
                "cmd": [
                    PYTHON_EXE, self._script("session_launcher"),
                    "--manifest", self._profile("gaming_manifest"),
                    "--debug",
                ],
            },
        ])

    def _launch_re(self, game: str) -> None:
        self.run([
            PYTHON_EXE, self._script("re_launcher"),
            "manual", "--game", game,
        ])

    # ------------------------------------------------------------------
    # Actions — CINEMA
    # ------------------------------------------------------------------

    def action_plex(self) -> None:
        self.run([PYTHON_EXE, self._script("plex_launcher"), "--preset", "default"])

    def action_media(self) -> None:
        self.run([PYTHON_EXE, self._script("youtube_launcher")])

    def action_live_tv(self) -> None:
        self.run([PYTHON_EXE, self._script("live_tv_launcher")])

    # ------------------------------------------------------------------
    # Actions — TOOLS (main menu)
    # ------------------------------------------------------------------

    def action_restore_defaults(self) -> None:
        if self.runner.is_running:
            self._output.append_info("> A process is already running.")
            return

        helper = os.path.join(LAUNCHER_DIR, "gui", "helpers", "restore_defaults_runner.py")
        self._output.clear()
        self._set_busy(True, "restore_defaults_runner.py")

        def _after_restore(rc: int) -> None:
            self._output.append_exit(rc)
            if rc == 0:
                crt = self._script("crt_tools")
                self.after(0, lambda: self._run_next_step([
                    {"cmd": [PYTHON_EXE, crt, "display", "restore", "--force"], "prefix": "> Applying display restore..."},
                    {"cmd": [PYTHON_EXE, crt, "audio",   "restore", "--force"], "prefix": "> Applying audio restore..."},
                ]))
            else:
                self.after(0, lambda: self._set_busy(False))

        self.runner.run(
            [PYTHON_EXE, helper, LAUNCHER_DIR],
            on_output=self._output.append,
            on_done=_after_restore,
        )

    def action_recover_re(self) -> None:
        self._output.clear()
        self.run(
            [PYTHON_EXE, self._script("re_launcher"), "restore"],
            prefix="> Recovering RE stack...",
        )
