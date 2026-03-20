"""Keyboard command mapping for the Live TV session loop."""

from __future__ import annotations

from typing import Optional


def decode_key(ch: bytes) -> Optional[str]:
    if not ch:
        return None
    if ch in (b"q", b"Q", b"\x1b"):
        return "quit"
    if ch in (b"r", b"R"):
        return "move_crt"
    if ch in (b"m", b"M"):
        return "move_main"
    return None

