"""
Modal dialog for Resident Evil game selection.

Usage:
    RESelector(parent, on_select=lambda game_key: ...)

*on_select* is called with one of "re1", "re2", "re3" after the user
clicks Launch.  If the user cancels, *on_select* is never called.
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from gui.theme import FONT_BUTTON, FONT_SECTION

_GAMES: dict[str, str] = {
    "re1": "RE1  —  Resident Evil (GOG)",
    "re2": "RE2  —  Resident Evil 2 (GOG)",
    "re3": "RE3  —  Resident Evil 3 (GOG)",
}


class RESelector(ctk.CTkToplevel):
    """Small modal popup for picking which RE title to launch."""

    def __init__(self, master, on_select: Callable[[str], None]) -> None:
        super().__init__(master)
        self.title("Select Game")
        self.geometry("340x210")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()          # modal — blocks interaction with parent

        self._on_select = on_select
        self._choice = ctk.StringVar(value="re1")

        self._build_ui()
        self.after(50, self._center_on_parent)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self,
            text="Select Resident Evil game:",
            font=FONT_SECTION,
        ).pack(pady=(18, 10))

        for key, label in _GAMES.items():
            ctk.CTkRadioButton(
                self,
                text=label,
                variable=self._choice,
                value=key,
                font=FONT_BUTTON,
            ).pack(anchor="w", padx=28, pady=3)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(14, 0))

        ctk.CTkButton(
            btn_row, text="Launch", width=110, command=self._launch
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Cancel", width=110, command=self.destroy
        ).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _launch(self) -> None:
        game = self._choice.get()
        self.destroy()
        self._on_select(game)

    def _center_on_parent(self) -> None:
        """Position the dialog over its parent window."""
        parent = self.master
        px = parent.winfo_x() + parent.winfo_width() // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w, h = 340, 210
        self.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")
