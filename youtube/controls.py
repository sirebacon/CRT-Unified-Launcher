"""Terminal display helpers: Now Playing, Adjust mode, status lines."""

import ctypes
import os
import shutil
import sys
from typing import Optional


def _term_width(default: int = 100) -> int:
    try:
        return max(40, shutil.get_terminal_size((default, 20)).columns)
    except Exception:
        return default


def _fit_line(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _yn(value: Optional[bool]) -> str:
    if value is None:
        return "N/A"
    return "yes" if value else "no"


def build_now_playing_status_text(
    telemetry: Optional[dict],
    zoom_preset_name: Optional[str] = None,
) -> str:
    tele = telemetry or {}
    return (
        f"{tele.get('state_label', 'N/A')} | "
        f"{tele.get('time_label', 'N/A / N/A')} | "
        f"{tele.get('volume_label', 'Vol N/A')} | "
        f"{tele.get('mute_label', 'Mute N/A')} | "
        f"{tele.get('queue_label', 'Item N/A')} | "
        f"{tele.get('zoom_label', ('Zoom ' + (zoom_preset_name or 'OFF')))}"
    )


class _COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _SMALL_RECT(ctypes.Structure):
    _fields_ = [
        ("Left", ctypes.c_short),
        ("Top", ctypes.c_short),
        ("Right", ctypes.c_short),
        ("Bottom", ctypes.c_short),
    ]


class _CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", _COORD),
        ("dwCursorPosition", _COORD),
        ("wAttributes", ctypes.c_ushort),
        ("srWindow", _SMALL_RECT),
        ("dwMaximumWindowSize", _COORD),
    ]


def _get_cursor_row_1based_windows() -> Optional[int]:
    try:
        kernel32 = ctypes.windll.kernel32
        h_stdout = kernel32.GetStdHandle(-11)
        if h_stdout in (0, -1):
            return None
        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        if not kernel32.GetConsoleScreenBufferInfo(h_stdout, ctypes.byref(csbi)):
            return None
        return int(csbi.dwCursorPosition.Y) + 1
    except Exception:
        return None


def _update_status_line_windows(status_text: str, status_row: int, width: int) -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        h_stdout = kernel32.GetStdHandle(-11)
        if h_stdout in (0, -1):
            return False

        csbi = _CONSOLE_SCREEN_BUFFER_INFO()
        if not kernel32.GetConsoleScreenBufferInfo(h_stdout, ctypes.byref(csbi)):
            return False
        old_pos = csbi.dwCursorPosition

        # Writing exactly terminal width can auto-wrap on Windows console and
        # produce visual duplicates on the next row; keep one column headroom.
        safe_width = max(1, width - 1)
        line = _fit_line(f"  Status: {status_text}", safe_width).ljust(safe_width)
        target = _COORD(0, max(0, status_row - 1))
        if not kernel32.SetConsoleCursorPosition(h_stdout, target):
            return False

        written = ctypes.c_ulong(0)
        if not kernel32.WriteConsoleW(
            h_stdout,
            ctypes.c_wchar_p(line),
            len(line),
            ctypes.byref(written),
            None,
        ):
            return False

        kernel32.SetConsoleCursorPosition(h_stdout, old_pos)
        return True
    except Exception:
        return False


def show_now_playing(
    title: str,
    is_playlist: bool = False,
    playlist_pos: Optional[int] = None,
    playlist_count: Optional[int] = None,
    zoom_locked: bool = False,
    zoom_preset_name: Optional[str] = None,
    telemetry: Optional[dict] = None,
    show_advanced_telemetry: bool = False,
) -> None:
    width = _term_width()
    rule = "=" * min(80, max(40, width))
    tele = telemetry or {}
    status = build_now_playing_status_text(telemetry, zoom_preset_name)

    os.system("cls" if os.name == "nt" else "clear")
    row = 1
    print(rule)
    row += 1
    print(_fit_line("        NOW PLAYING (YouTube/CRT)", width))
    row += 1
    print(rule)
    row += 1
    if playlist_pos is not None and playlist_count is not None:
        print(_fit_line(f"  Playlist: {playlist_pos} / {playlist_count}", width))
        row += 1
    if title:
        print(_fit_line(f"  Title: {title}", width))
        row += 1
        print()
        row += 1

    status_row = _get_cursor_row_1based_windows() if os.name == "nt" else None
    if status_row is None:
        status_row = row
    print(_fit_line(f"  Status: {status}", width))
    row += 1
    print()
    row += 1

    if show_advanced_telemetry:
        adv = tele.get("advanced", {}) or {}
        cache_dur = adv.get("demuxer-cache-duration")
        cache_label = "N/A" if cache_dur is None else f"{float(cache_dur):.1f}s"
        cache_buf = _yn(adv.get("cache-buffering-state"))
        vcodec = adv.get("video-codec") or "N/A"
        vw = adv.get("video-params/w")
        vh = adv.get("video-params/h")
        vres = f"{vw}x{vh}" if vw is not None and vh is not None else "N/A"
        vfps = adv.get("estimated-vf-fps") or adv.get("container-fps")
        vfps_label = f"{float(vfps):.3f}" if vfps is not None else "N/A"
        hw = adv.get("hwdec-current") or "N/A"
        acodec = adv.get("audio-codec-name") or "N/A"
        ach = adv.get("audio-params/channel-count")
        asr = adv.get("audio-params/samplerate")
        ach_label = f"{int(ach)}ch" if ach is not None else "N/A"
        asr_label = f"{int(asr)}Hz" if asr is not None else "N/A"
        ipc_mode = tele.get("ipc_mode", "N/A")
        health = tele.get("health", "N/A")

        print("  Telemetry:")
        row += 1
        print(_fit_line(f"  - Cache: {cache_label} buffered | Buffering: {cache_buf}", width))
        row += 1
        print(_fit_line(f"  - Video: {vcodec} | {vres} | {vfps_label} fps | HW: {hw}", width))
        row += 1
        print(_fit_line(f"  - Audio: {acodec} | {ach_label} | {asr_label}", width))
        row += 1
        print(_fit_line(f"  - IPC: {ipc_mode} | Health: {health}", width))
        row += 1
        print()
        row += 1

    print("  Playback")
    print("  [Space]  Pause / Resume")
    print("  [<- ->]  Seek -10s / +10s")
    print("  [^  v]   Volume +5 / -5")
    print("  [M]      Mute")
    if is_playlist:
        print("  [N]      Next video")
        print("  [P]      Previous video")

    print()
    print("  Video / Window")
    print("  [A]      Adjust window position/size")
    print("  [R]      Snap to preset CRT area")
    print("  [U]      Unsnap to saved profile area")
    zoom_label = f"ON  ({zoom_preset_name})" if zoom_locked and zoom_preset_name else "OFF"
    print(f"  [Z]      Cycle zoom preset [{zoom_label}]")

    print()
    print("  Library")
    print("  [+]      Add to favorites")
    print("  [L]      Browse favorites")
    print("  [H]      Recent history")
    print("  [B]      Set bookmark at current time")
    print("  [J]      Jump to bookmark")

    print()
    print(f"  [T]      Telemetry {'ON' if show_advanced_telemetry else 'OFF'}")
    print("  [Q]      Quit")
    print(rule)
    print()
    return {"status_row": status_row, "width": width, "status_text": status}


def update_now_playing_status_line(
    status_text: str,
    status_row: int,
    width: int,
) -> bool:
    """Update only the Status line in-place to avoid full-screen redraw flicker."""
    if os.name == "nt":
        return _update_status_line_windows(status_text, status_row, width)

    try:
        text = _fit_line(f"  Status: {status_text}", width)
        sys.stdout.write(f"\x1b[s\x1b[{status_row};1H{text:<{width}}\x1b[u")
        sys.stdout.flush()
        return True
    except Exception:
        return False


def show_adjust_mode(title: str) -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print("========================================")
    print("        ADJUST WINDOW (YouTube/CRT)")
    print("========================================")
    if title:
        print(f"  {title}")
        print()
    print("  Arrow keys   Move left/right/up/down")
    print("  [ / ]        Narrower / Wider")
    print("  - / =        Shorter / Taller")
    print("  1 - 9        Step size (1/5/10/25/50/100/200/500/1000 px)")
    print("  [S]          Save rect to profile")
    print("  [L]          Load saved profile rect")
    print("  [R]          Snap to preset CRT area (clears zoom/pan)")
    print("  [U]          Unsnap to saved profile rect (clears zoom/pan)")
    print("  [F]          Fill CRT with content via zoom (drag to pick on CRT)")
    print("  [P]          Save current zoom/pan as a named preset")
    print("  [C]          Clear zoom/pan (show unzoomed video)")
    print("  [Z]          Revert last R / F / L (also clears zoom/pan)")
    print("  [A]          Back to player controls")
    print("========================================")


def show_adjust_status(x: int, y: int, w: int, h: int, step: int) -> None:
    print(
        f"\r  x={x:6d}  y={y:6d}  w={w:6d}  h={h:6d}  step={step:4d}px    ",
        end="",
        flush=True,
    )


def show_compact_status(
    title: str,
    pos: Optional[int] = None,
    count: Optional[int] = None,
    telemetry: Optional[dict] = None,
) -> None:
    """One-line compact status shown after auto-hide timeout."""
    idx = f" ({pos}/{count})" if pos is not None and count is not None else ""
    tele = telemetry or {}
    state = tele.get("state_label", "N/A")
    t = tele.get("time_label", "N/A / N/A")
    vol = tele.get("volume_label", "Vol N/A")
    line = f"  \u25b6  {state} | {t} | {vol}{idx}"
    w = _term_width()
    print(f"\r{_fit_line(line, w)}    ", end="", flush=True)


def clear_compact_status_line() -> None:
    """Clear any previously-rendered compact status line."""
    w = _term_width()
    print("\r" + (" " * w) + "\r", end="", flush=True)


def show_zoom_menu(
    presets: list,
    active_name: Optional[str],
    zoom_locked: bool,
) -> None:
    """Full-screen zoom preset picker."""
    os.system("cls" if os.name == "nt" else "clear")
    print("========================================")
    print("        ZOOM PRESETS (YouTube/CRT)")
    print("========================================")
    status = f"ON  ({active_name})" if zoom_locked and active_name else "OFF"
    print(f"  Zoom-lock: {status}")
    print()
    if presets:
        for i, p in enumerate(presets, 1):
            marker = "*" if p["name"] == active_name else " "
            print(
                f"  {i:>2}) {marker} {p['name']:<20}"
                f"  zoom={p['zoom']:+.3f}"
                f"  pan_x={p['pan_x']:+.3f}"
                f"  pan_y={p['pan_y']:+.3f}"
            )
    else:
        print("  (no presets yet — use [F] then [P] in Adjust mode to save one)")
    print()
    print("  Pick number to enable, [O] Off, Enter to cancel:")
    print("========================================")
