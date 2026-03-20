"""
Inline Resident Evil game selector panel.

Pushed onto the navigation stack when the user clicks
"Launch Resident Evil..." in the main menu.
Three full-width buttons launch each title directly.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from gui.theme import FONT_BUTTON, FONT_SECTION, GREEN_MID
from gui.tooltip import Tooltip

ActionMap = dict[str, Callable[[], None]]

_GAMES: list[tuple[str, str, str]] = [
    # (action key,  button label,                        tooltip)
    ("re1", "RE1  —  Resident Evil (GOG)",   "Launch Resident Evil 1 via Moonlight"),
    ("re2", "RE2  —  Resident Evil 2 (GOG)", "Launch Resident Evil 2 via Moonlight"),
    ("re3", "RE3  —  Resident Evil 3 (GOG)", "Launch Resident Evil 3 via Moonlight"),
]


class REPanel(ctk.CTkScrollableFrame):
    """Inline panel for selecting which RE title to launch."""

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
        section = ctk.CTkFrame(self)
        section.pack(fill="x", padx=6, pady=(14, 0))

        ctk.CTkLabel(
            section,
            text="  Select a game to launch",
            font=FONT_SECTION,
            anchor="w",
            text_color=GREEN_MID,
        ).pack(fill="x", padx=8, pady=(8, 4))

        inner = ctk.CTkFrame(section)
        inner.pack(fill="x", padx=8, pady=(0, 10))

        for key, label, tip in _GAMES:
            b = ctk.CTkButton(
                inner,
                text=f"  {label}",
                anchor="w",
                font=FONT_BUTTON,
                height=52,
                command=self._actions[key],
            )
            b.pack(fill="x", padx=6, pady=6)
            self._buttons.append(b)
            Tooltip(b, tip)
