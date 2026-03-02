"""Named pipe IPC client for mpv: send commands, cache set properties."""

import json
import time

_HAS_WIN32 = False
try:
    import pywintypes
    import win32file
    _HAS_WIN32 = True
except ImportError:
    pass

PIPE_NAME = r'\\.\pipe\crt-mpv-ipc'


class MpvIpc:
    """IPC client for mpv's named pipe server.

    Uses a single write-only connection for reliability — Windows synchronous
    pipe handles only allow one I/O operation at a time, so mixing a background
    ReadFile thread with WriteFile on the same handle causes a deadlock.

    get_property() returns values from a local cache that is populated whenever
    set_property() is called successfully.  Properties that mpv manages itself
    (time-pos, playlist-pos, etc.) are not in the cache and return None.
    """

    def __init__(self):
        self._handle = None
        self._prop_cache: dict = {}

    def connect(self, retries: int = 10, delay: float = 0.5) -> bool:
        """Open the mpv IPC pipe write-only.  Returns True on success."""
        if not _HAS_WIN32:
            return False
        for attempt in range(retries):
            try:
                self._handle = win32file.CreateFile(
                    PIPE_NAME,
                    win32file.GENERIC_WRITE,
                    0, None,
                    win32file.OPEN_EXISTING,
                    0, None,
                )
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
        """Send a command list to mpv."""
        if self._handle is None or not _HAS_WIN32:
            return False
        try:
            payload = json.dumps({"command": list(cmd_args)}) + "\n"
            win32file.WriteFile(self._handle, payload.encode("utf-8"))
            return True
        except Exception:
            return False

    def get_property(self, name: str, timeout: float = 1.0):
        """Return the cached value for name, or None if not in cache.

        Only properties set via set_property() are available.  Properties
        managed by mpv itself (time-pos, playlist-pos, etc.) return None.
        """
        return self._prop_cache.get(name)

    # ---- Public command methods ----

    def toggle_pause(self) -> bool:
        return self._send("cycle", "pause")

    def seek(self, seconds: int) -> bool:
        return self._send("seek", seconds, "relative")

    def seek_absolute(self, seconds: float) -> bool:
        return self._send("seek", seconds, "absolute")

    def add_volume(self, delta: int) -> bool:
        return self._send("add", "volume", delta)

    def toggle_mute(self) -> bool:
        return self._send("cycle", "mute")

    def quit(self) -> bool:
        return self._send("quit")

    def set_property(self, name: str, value) -> bool:
        result = self._send("set_property", name, value)
        if result:
            self._prop_cache[name] = value
        return result

    def reset_zoom_pan(self) -> None:
        self.set_property("video-zoom", 0)
        self.set_property("video-pan-x", 0)
        self.set_property("video-pan-y", 0)

    def playlist_next(self) -> bool:
        return self._send("playlist-next")

    def playlist_prev(self) -> bool:
        return self._send("playlist-prev")
