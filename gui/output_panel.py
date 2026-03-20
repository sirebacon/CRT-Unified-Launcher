"""
Scrollable live output widget with timestamps and coloured output.

Public API:
    append(line)          — subprocess output line  (bright green)
    append_info(line)     — app status message       (medium green)
    append_exit(rc)       — exit code summary        (green if 0, amber if not)
    copy_to_clipboard()   — copies all text to system clipboard
    clear()               — erases all content

All methods are thread-safe (updates are scheduled via after()).
"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

_MAX_LINES = 300

# Tag name → foreground colour
_TAG_COLORS: dict[str, str] = {
    "ts":       "#1a8a1a",   # dim green  — HH:MM:SS timestamp
    "normal":   "#39ff14",   # phosphor   — subprocess output
    "info":     "#22cc22",   # mid green  — app status messages
    "exit_ok":  "#22cc22",   # mid green  — successful exit
    "exit_err": "#ff6600",   # amber      — non-zero exit
}


class OutputPanel(ctk.CTkFrame):
    """Read-only, auto-scrolling text area for subprocess output."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._textbox = ctk.CTkTextbox(
            self,
            state="disabled",
            wrap="word",
            font=("Consolas", 11),
        )
        self._textbox.pack(fill="both", expand=True, padx=4, pady=4)
        self._init_tags()

    # ------------------------------------------------------------------
    # Public interface (all thread-safe)
    # ------------------------------------------------------------------

    def append(self, line: str) -> None:
        """Append a subprocess output line (bright green)."""
        self.after(0, self._do_append, line, "normal")

    def append_info(self, line: str) -> None:
        """Append an app status message (medium green, no timestamp)."""
        self.after(0, self._do_append_plain, line, "info")

    def append_exit(self, rc: int) -> None:
        """Append an exit-code summary line coloured by success / failure."""
        if rc == 0:
            self.after(0, self._do_append_plain, "[done]", "exit_ok")
        else:
            self.after(0, self._do_append_plain, f"[exit {rc}]", "exit_err")

    def copy_to_clipboard(self) -> None:
        """Copy all output text to the system clipboard."""
        self.after(0, self._do_copy)

    def clear(self) -> None:
        """Erase all content."""
        self.after(0, self._do_clear)

    # ------------------------------------------------------------------
    # Internal (must run on main thread)
    # ------------------------------------------------------------------

    def _init_tags(self) -> None:
        tw = self._textbox._textbox          # underlying tk.Text widget
        for tag, color in _TAG_COLORS.items():
            tw.tag_configure(tag, foreground=color)

    def _do_append(self, line: str, style: str) -> None:
        """Append a timestamped line."""
        ts = datetime.now().strftime("%H:%M:%S")
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.insert("end", f"[{ts}] ", "ts")
        tw.insert("end", line + "\n", style)
        self._trim(tw)
        tw.configure(state="disabled")
        tw.see("end")

    def _do_append_plain(self, line: str, style: str) -> None:
        """Append a line without a timestamp (for app-generated messages)."""
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.insert("end", line + "\n", style)
        self._trim(tw)
        tw.configure(state="disabled")
        tw.see("end")

    def _do_copy(self) -> None:
        text = self._textbox._textbox.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)

    def _do_clear(self) -> None:
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("1.0", "end")
        tw.configure(state="disabled")

    @staticmethod
    def _trim(tw) -> None:
        total = int(tw.index("end-1c").split(".")[0])
        if total > _MAX_LINES:
            tw.delete("1.0", f"{total - _MAX_LINES}.0")
