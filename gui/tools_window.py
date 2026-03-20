"""
CRT Tools popup window.

Opened by the main panel's "CRT Tools" button.  Owns its own OutputPanel
and SubprocessRunner so it is fully independent of the main window's runner.

Accepts a *runner* (SubprocessRunner) injected from the app — the tools
window does not own long-lived processes, so sharing the app runner is fine,
but receiving it as a parameter keeps the coupling explicit.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import customtkinter as ctk

from gui.constants import LAUNCHER_DIR, LAUNCHBOX_EMULATORS_XML, PYTHON_EXE, SCRIPTS
from gui.output_panel import OutputPanel
from gui.subprocess_runner import SubprocessRunner
from gui.theme import FONT_BUTTON, FONT_SECTION, GREEN_MID


class ToolsWindow(ctk.CTkToplevel):
    """Non-modal popup containing all eleven CRT Tools sub-actions."""

    def __init__(self, master, runner: SubprocessRunner) -> None:
        super().__init__(master)
        self.title("CRT Tools")
        self.geometry("560x580")
        self.resizable(False, True)
        self.transient(master)

        self._runner = runner
        self._build_ui()
        self.after(50, self._center_on_parent)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self, text="CRT TOOLS", font=FONT_SECTION, text_color=GREEN_MID
        ).pack(pady=(10, 4))

        scroll = ctk.CTkScrollableFrame(self, height=280)
        scroll.pack(fill="x", padx=10, pady=(0, 4))

        for label, handler in self._actions():
            ctk.CTkButton(
                scroll,
                text=f"  {label}",
                anchor="w",
                font=FONT_BUTTON,
                command=handler,
            ).pack(fill="x", padx=4, pady=3)

        self._output = OutputPanel(self, height=200)
        self._output.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    def _actions(self) -> list[tuple[str, object]]:
        """Return (label, handler) pairs for each tool button."""
        return [
            ("Display Dump",                lambda: self._run_tool("display", "dump")),
            ("Config Dump",                 lambda: self._run_tool("config", "dump")),
            ("Config Check",                lambda: self._run_tool("config", "check")),
            ("Prereqs Check",               lambda: self._run_tool("prereqs")),
            ("Window List (Moonlight)",     lambda: self._run_tool("window", "list", "--filter", "moonlight")),
            ("Audio Status",                lambda: self._run_tool("audio", "status")),
            ("Session Log (last 40 lines)", lambda: self._run_tool("session", "log", "--lines", "40")),
            ("Session Processes",           lambda: self._run_tool("session", "processes")),
            ("LaunchBox RetroArch Status",  self._lb_retroarch_status),
            ("Restore Display & Audio",     self._restore_display_audio),
        ]

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _run_tool(self, *args: str) -> None:
        """Run a crt_tools.py subcommand, stream output to this window's panel."""
        crt = os.path.join(LAUNCHER_DIR, SCRIPTS["crt_tools"])
        self._output.clear()
        self._runner.run(
            [PYTHON_EXE, crt, *args],
            on_output=self._output.append,
        )

    def _restore_display_audio(self) -> None:
        """Run display restore then audio restore in sequence."""
        crt = os.path.join(LAUNCHER_DIR, SCRIPTS["crt_tools"])
        self._output.clear()
        self._output.append("> Restoring display...")

        def _after_display(rc: int) -> None:
            self._output.append(f"> Display: {'OK' if rc == 0 else f'exit {rc}'}")
            self._output.append("> Restoring audio...")
            self._runner.run(
                [PYTHON_EXE, crt, "audio", "restore", "--force"],
                on_output=self._output.append,
                on_done=lambda rc2: self._output.append(
                    f"> Audio: {'OK' if rc2 == 0 else f'exit {rc2}'}"
                ),
            )

        self._runner.run(
            [PYTHON_EXE, crt, "display", "restore", "--force"],
            on_output=self._output.append,
            on_done=_after_display,
        )

    def _lb_retroarch_status(self) -> None:
        """Parse LaunchBox Emulators.xml and report RetroArch wrapper status."""
        self._output.clear()
        self._output.append("> Checking LaunchBox RetroArch path...")

        if not os.path.exists(LAUNCHBOX_EMULATORS_XML):
            self._output.append(f"ERROR: Emulators.xml not found:\n  {LAUNCHBOX_EMULATORS_XML}")
            return

        try:
            tree = ET.parse(LAUNCHBOX_EMULATORS_XML)
        except Exception as exc:
            self._output.append(f"ERROR: Failed to parse Emulators.xml: {exc}")
            return

        retro = None
        for emulator in tree.getroot().findall("Emulator"):
            if (emulator.findtext("Title") or "").strip().lower() == "retroarch":
                retro = emulator
                break

        if retro is None:
            self._output.append("RetroArch entry not found in Emulators.xml.")
            return

        app_path = (retro.findtext("ApplicationPath") or "").strip()
        cmd_line = (retro.findtext("CommandLine") or "").strip()
        is_wrapper = "launchbox_retroarch_wrapper" in app_path.lower()

        self._output.append(f"  ApplicationPath : {app_path or '(empty)'}")
        self._output.append(f"  CommandLine     : {cmd_line or '(empty)'}")
        if is_wrapper:
            self._output.append("  Status          : WRAPPER ACTIVE")
            self._output.append("  RetroArch launches through CRT wrapper.")
        else:
            self._output.append("  Status          : NORMAL (no CRT wrapper)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _center_on_parent(self) -> None:
        parent = self.master
        px = parent.winfo_x() + parent.winfo_width() // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w, h = 560, 580
        self.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")
