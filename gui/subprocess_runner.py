"""
Non-blocking subprocess runner.

Runs a command in a background daemon thread, streaming stdout/stderr
line-by-line to a callback.  The GUI stays responsive throughout.

Usage:
    runner = SubprocessRunner()
    runner.run(cmd, on_output=panel.append, on_done=lambda rc: ...)

Only one process is tracked at a time.  Callers should check
`runner.is_running` before starting a new job if they need exclusivity.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Callable, Optional


class SubprocessRunner:
    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True if a subprocess is currently running."""
        return self._proc is not None and self._proc.poll() is None

    def run(
        self,
        cmd: list[str],
        on_output: Callable[[str], None],
        on_done: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Start *cmd* in a background daemon thread.

        *on_output(line)* is called for every stdout/stderr line.
        *on_done(returncode)* is called once the process exits.
        Both callbacks may be invoked from the background thread — use
        ``widget.after(0, ...)`` inside them if you need to touch tkinter.
        """
        threading.Thread(
            target=self._worker,
            args=(cmd, on_output, on_done),
            daemon=True,
        ).start()

    def terminate(self) -> None:
        """Send SIGTERM to the running process, if any."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _worker(
        self,
        cmd: list[str],
        on_output: Callable[[str], None],
        on_done: Optional[Callable[[int], None]],
    ) -> None:
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in self._proc.stdout:
            on_output(line.rstrip())
        self._proc.wait()
        if on_done:
            on_done(self._proc.returncode)
