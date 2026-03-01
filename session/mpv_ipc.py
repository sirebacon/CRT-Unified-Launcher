"""Thin write-only named pipe client for mpv IPC control."""

import json

_HAS_WIN32 = False
try:
    import pywintypes
    import win32file
    _HAS_WIN32 = True
except ImportError:
    pass

PIPE_NAME = r'\\.\pipe\crt-mpv-ipc'


class MpvIpc:
    """Write-only IPC client for mpv's named pipe server."""

    def __init__(self):
        self._handle = None

    def connect(self, retries: int = 10, delay: float = 0.5) -> bool:
        """Try to open the mpv IPC pipe. Returns True on success."""
        if not _HAS_WIN32:
            return False
        import time
        for attempt in range(retries):
            try:
                handle = win32file.CreateFile(
                    PIPE_NAME,
                    win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                self._handle = handle
                return True
            except pywintypes.error:
                if attempt < retries - 1:
                    time.sleep(delay)
        return False

    def close(self) -> None:
        if self._handle is not None:
            try:
                win32file.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _send(self, *cmd_args) -> bool:
        """Send a command list to mpv via the pipe. Returns True on success."""
        if self._handle is None or not _HAS_WIN32:
            return False
        try:
            payload = json.dumps({"command": list(cmd_args)}) + "\n"
            win32file.WriteFile(self._handle, payload.encode("utf-8"))
            return True
        except Exception:
            return False

    # ---- Public command methods ----

    def toggle_pause(self) -> bool:
        return self._send("cycle", "pause")

    def seek(self, seconds: int) -> bool:
        return self._send("seek", seconds, "relative")

    def add_volume(self, delta: int) -> bool:
        return self._send("add", "volume", delta)

    def toggle_mute(self) -> bool:
        return self._send("cycle", "mute")

    def quit(self) -> bool:
        return self._send("quit")

    def set_property(self, name: str, value) -> bool:
        return self._send("set_property", name, value)

    def reset_zoom_pan(self) -> None:
        self.set_property("video-zoom", 0)
        self.set_property("video-pan-x", 0)
        self.set_property("video-pan-y", 0)
