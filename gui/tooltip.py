"""
Simple hover tooltip for any tkinter / CustomTkinter widget.

Usage:
    from gui.tooltip import Tooltip
    Tooltip(some_button, "Short description shown on hover")
"""
from __future__ import annotations

import tkinter as tk


class Tooltip:
    """Displays a small popup label when the mouse hovers over *widget*."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text   = text
        self._tip: tk.Toplevel | None = None

        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _show(self, event: tk.Event | None = None) -> None:
        if self._tip:
            return
        w = self._widget
        x = w.winfo_rootx() + 12
        y = w.winfo_rooty() + w.winfo_height() + 6

        self._tip = tk.Toplevel(w)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_attributes("-topmost", True)
        self._tip.wm_geometry(f"+{x}+{y}")

        tk.Label(
            self._tip,
            text=self._text,
            background="#0d2a0d",
            foreground="#22cc22",
            font=("Consolas", 10),
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
        ).pack()

    def _hide(self, event: tk.Event | None = None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None
