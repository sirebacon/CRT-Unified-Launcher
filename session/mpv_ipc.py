"""Named pipe IPC client for mpv with optional duplex request/response mode."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

_HAS_WIN32 = False
try:
    import pywintypes
    import win32file
    import win32pipe
    _HAS_WIN32 = True
except ImportError:
    pass

PIPE_NAME = r"\\.\pipe\crt-mpv-ipc"


class MpvIpc:
    """IPC client for mpv named-pipe JSON protocol.

    Modes:
    - write-only: stable command sends, cache-only get_property behavior
    - duplex: one GENERIC_READ|GENERIC_WRITE handle with serialized request/response

    Deadlock prevention:
    - no background reader thread
    - all pipe I/O serialized under one lock
    """

    _MAX_PENDING = 128

    def __init__(self, use_duplex: bool = False):
        self._handle = None
        self._prop_cache: Dict[str, Any] = {}
        self._pending_by_id: Dict[int, dict] = {}
        self._read_buffer = b""
        self._next_request_id = 1
        self._io_lock = threading.Lock()
        self._requested_duplex = bool(use_duplex)
        self._duplex_active = False

    @property
    def mode(self) -> str:
        return "duplex" if self._duplex_active else "write-only"

    def connect(self, retries: int = 10, delay: float = 0.5) -> bool:
        """Open mpv IPC pipe.

        If duplex is requested, we try R/W first and gracefully fall back to
        write-only if unavailable so controls remain usable.
        """
        if not _HAS_WIN32:
            return False
        for attempt in range(retries):
            try:
                if self._requested_duplex:
                    try:
                        self._handle = win32file.CreateFile(
                            PIPE_NAME,
                            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                            0,
                            None,
                            win32file.OPEN_EXISTING,
                            0,
                            None,
                        )
                        self._duplex_active = True
                        return True
                    except Exception:
                        # Fallback keeps controls working even if duplex isn't supported.
                        self._handle = win32file.CreateFile(
                            PIPE_NAME,
                            win32file.GENERIC_WRITE,
                            0,
                            None,
                            win32file.OPEN_EXISTING,
                            0,
                            None,
                        )
                        self._duplex_active = False
                        return True

                self._handle = win32file.CreateFile(
                    PIPE_NAME,
                    win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                self._duplex_active = False
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
        self._pending_by_id.clear()
        self._read_buffer = b""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _invalidate(self) -> None:
        try:
            if self._handle is not None:
                win32file.CloseHandle(self._handle)
        except Exception:
            pass
        self._handle = None

    def _next_id(self) -> int:
        rid = self._next_request_id
        self._next_request_id += 1
        if self._next_request_id > 2_000_000_000:
            self._next_request_id = 1
        return rid

    def _store_pending(self, rid: int, obj: dict) -> None:
        self._pending_by_id[rid] = obj
        if len(self._pending_by_id) > self._MAX_PENDING:
            # Drop oldest inserted key by dict order.
            oldest = next(iter(self._pending_by_id))
            self._pending_by_id.pop(oldest, None)

    def _drain_events(self, obj: dict) -> None:
        # Track property-change events as optional cache hints.
        try:
            if obj.get("event") == "property-change":
                name = obj.get("name")
                if name:
                    self._prop_cache[name] = obj.get("data")
        except Exception:
            pass

    def _read_line(self, timeout: float) -> Optional[str]:
        if self._handle is None or not _HAS_WIN32:
            return None
        deadline = time.monotonic() + max(0.0, timeout)

        while time.monotonic() < deadline:
            if b"\n" in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split(b"\n", 1)
                return line.decode("utf-8", errors="ignore")

            try:
                avail = win32pipe.PeekNamedPipe(self._handle, 0)[1]
            except Exception:
                self._invalidate()
                return None

            if avail <= 0:
                time.sleep(0.01)
                continue

            try:
                _, chunk = win32file.ReadFile(self._handle, min(4096, max(1, avail)))
                if not chunk:
                    self._invalidate()
                    return None
                self._read_buffer += chunk
            except Exception:
                self._invalidate()
                return None
        return None

    def _send_write_only(self, cmd_args: list) -> bool:
        if self._handle is None or not _HAS_WIN32:
            return False
        try:
            payload = json.dumps({"command": cmd_args}) + "\n"
            win32file.WriteFile(self._handle, payload.encode("utf-8"))
            return True
        except Exception:
            self._invalidate()
            return False

    def _send_request(self, cmd_args: list, timeout: float) -> Optional[dict]:
        """Send request and wait for matching request_id response (duplex only)."""
        if not self._duplex_active or self._handle is None or not _HAS_WIN32:
            return None

        rid = self._next_id()
        payload = {"command": cmd_args, "request_id": rid}

        with self._io_lock:
            # A matching response may have been buffered earlier.
            cached = self._pending_by_id.pop(rid, None)
            if cached is not None:
                return cached

            try:
                wire = json.dumps(payload) + "\n"
                win32file.WriteFile(self._handle, wire.encode("utf-8"))
            except Exception:
                self._invalidate()
                return None

            deadline = time.monotonic() + max(0.0, timeout)
            while time.monotonic() < deadline:
                line = self._read_line(deadline - time.monotonic())
                if line is None:
                    return None
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                msg_rid = obj.get("request_id")
                if isinstance(msg_rid, int):
                    if msg_rid == rid:
                        return obj
                    self._store_pending(msg_rid, obj)
                    continue

                # Async event/no request_id.
                self._drain_events(obj)
            return None

    def _command(self, *cmd_args, timeout: float = 0.20) -> bool:
        cmd = list(cmd_args)
        if self._duplex_active:
            resp = self._send_request(cmd, timeout)
            if not resp:
                return False
            return resp.get("error") == "success"
        return self._send_write_only(cmd)

    def get_property(self, name: str, timeout: float = 0.20):
        if self._duplex_active:
            resp = self._send_request(["get_property", name], timeout)
            if resp and resp.get("error") == "success":
                value = resp.get("data")
                self._prop_cache[name] = value
                return value
            return None
        # Legacy write-only behavior: cache only.
        return self._prop_cache.get(name)

    # ---- Public command methods ----

    def toggle_pause(self) -> bool:
        return self._command("cycle", "pause")

    def seek(self, seconds: int) -> bool:
        return self._command("seek", seconds, "relative")

    def seek_absolute(self, seconds: float) -> bool:
        return self._command("seek", seconds, "absolute")

    def add_volume(self, delta: int) -> bool:
        return self._command("add", "volume", delta)

    def toggle_mute(self) -> bool:
        return self._command("cycle", "mute")

    def quit(self) -> bool:
        return self._command("quit")

    def set_property(self, name: str, value) -> bool:
        result = self._command("set_property", name, value)
        if result:
            self._prop_cache[name] = value
        return result

    def reset_zoom_pan(self) -> None:
        self.set_property("video-zoom", 0)
        self.set_property("video-pan-x", 0)
        self.set_property("video-pan-y", 0)

    def playlist_next(self) -> bool:
        return self._command("playlist-next")

    def playlist_prev(self) -> bool:
        return self._command("playlist-prev")
