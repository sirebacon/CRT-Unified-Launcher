"""
Main launcher panel — three button groups: GAMING, CINEMA, TOOLS.

Accepts an *actions* dict of named callables injected from the app.
This keeps the panel entirely decoupled from app internals; it just
renders buttons and routes clicks to whatever was registered.

Expected action keys:
    gaming   : retroarch, launchbox, resident_evil
    cinema   : plex, media, live_tv
    tools    : crt_tools, restore_defaults, recover_re
"""
from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from gui.theme import FONT_BUTTON, FONT_SECTION, GREEN_MID
from gui.tooltip import Tooltip

# Type alias for clarity
ActionMap = dict[str, Callable[[], None]]

# Hover tooltip text for each button
_TOOLTIPS: dict[str, str] = {
    "retroarch":        "Launch RetroArch via CRT session profile",
    "launchbox":        "Restore display then open LaunchBox gaming session",
    "resident_evil":    "Pick RE1 / RE2 / RE3 and launch via Moonlight",
    "plex":             "Open Plex with display locker",
    "media":            "Play YouTube, HiAnime, or a custom URL in mpv",
    "live_tv":          "Open Live TV via VLC",
    "crt_tools":        "Open CRT diagnostics and utility tools",
    "restore_defaults": "Restore config from backup and reset display/audio",
    "recover_re":       "Force-restore a stuck Resident Evil stack",
}


class MainPanel(ctk.CTkScrollableFrame):
    """Scrollable frame holding all three launcher groups."""

    def __init__(self, master, actions: ActionMap, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._actions = actions
        self._buttons: list[ctk.CTkButton] = []
        self._build_gaming()
        self._build_cinema()
        self._build_tools()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable all launcher buttons (e.g. while a job runs)."""
        state = "normal" if enabled else "disabled"
        for btn in self._buttons:
            btn.configure(state=state)

    # ------------------------------------------------------------------
    # Section / button helpers
    # ------------------------------------------------------------------

    def _section(self, title: str) -> ctk.CTkFrame:
        """Create a labelled group frame and return the inner button container."""
        outer = ctk.CTkFrame(self)
        outer.pack(fill="x", padx=6, pady=(14, 0))

        ctk.CTkLabel(
            outer,
            text=f"  {title}",
            font=FONT_SECTION,
            anchor="w",
            text_color=GREEN_MID,
        ).pack(fill="x", padx=8, pady=(8, 4))

        inner = ctk.CTkFrame(outer)
        inner.pack(fill="x", padx=8, pady=(0, 10))
        return inner

    def _btn(self, parent: ctk.CTkFrame, label: str, key: str) -> ctk.CTkButton:
        """Create a full-width, left-aligned button wired to actions[key]."""
        b = ctk.CTkButton(
            parent,
            text=f"  {label}",
            anchor="w",
            font=FONT_BUTTON,
            height=40,
            command=self._actions[key],
        )
        b.pack(fill="x", padx=6, pady=4)
        self._buttons.append(b)

        tip = _TOOLTIPS.get(key)
        if tip:
            Tooltip(b, tip)

        return b

    # ------------------------------------------------------------------
    # Group builders
    # ------------------------------------------------------------------

    def _build_gaming(self) -> None:
        f = self._section("GAMING")
        self._btn(f, "Launch RetroArch",              "retroarch")
        self._btn(f, "Launch LaunchBox (Session)",    "launchbox")
        self._btn(f, "Launch Resident Evil...",       "resident_evil")

    def _build_cinema(self) -> None:
        f = self._section("CINEMA")
        self._btn(f, "Launch Plex",                      "plex")
        self._btn(f, "Launch Media  (YT / Anime / URL)", "media")
        self._btn(f, "Launch Live TV  (VLC)",            "live_tv")

    def _build_tools(self) -> None:
        f = self._section("TOOLS")
        self._btn(f, "CRT Tools",                    "crt_tools")
        self._btn(f, "Restore Default Settings",     "restore_defaults")
        self._btn(f, "Recover Resident Evil Stack",  "recover_re")
