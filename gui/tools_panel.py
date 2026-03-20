"""
CRT Tools panel — inline panel shown inside the main window.

A CTkScrollableFrame containing all ten CRT tool buttons.
Navigation (show/hide) is handled by the app; this panel
only knows about its own buttons and the actions dict.

Like MainPanel, accepts an *actions* dict so it has no
direct dependency on the app class.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from gui.theme import FONT_BUTTON
from gui.tooltip import Tooltip

ActionMap = dict[str, Callable[[], None]]

_BUTTONS: list[tuple[str, str, str]] = [
    # (label,                          key,              tooltip)
    ("Display Dump",                "display_dump",    "Dump current display configuration"),
    ("Config Dump",                 "config_dump",     "Dump the full CRT config to output"),
    ("Config Check",                "config_check",    "Validate CRT config for errors"),
    ("Prereqs Check",               "prereqs",         "Check all prerequisite tools are installed"),
    ("Window List (Moonlight)",     "window_list",     "List windows matching 'moonlight'"),
    ("Audio Status",                "audio_status",    "Show current audio output device"),
    ("Session Log (last 40 lines)", "session_log",     "Tail the last 40 lines of the session log"),
    ("Session Processes",           "session_procs",   "List running session-related processes"),
    ("LaunchBox RetroArch Status",  "lb_status",       "Check if LaunchBox uses the CRT RetroArch wrapper"),
    ("Restore Display & Audio",     "restore_display", "Restore display and audio to default state"),
]


class ToolsPanel(ctk.CTkScrollableFrame):
    """Scrollable frame holding all CRT Tools sub-actions."""

    def __init__(self, master, actions: ActionMap, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._actions = actions
        self._buttons: list[ctk.CTkButton] = []
        self._build()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all buttons (called by app busy state)."""
        state = "normal" if enabled else "disabled"
        for btn in self._buttons:
            btn.configure(state=state)

    def _build(self) -> None:
        for label, key, tip in _BUTTONS:
            b = ctk.CTkButton(
                self,
                text=f"  {label}",
                anchor="w",
                font=FONT_BUTTON,
                height=40,
                command=self._actions[key],
            )
            b.pack(fill="x", padx=6, pady=4)
            self._buttons.append(b)
            Tooltip(b, tip)
