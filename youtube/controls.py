"""Terminal display helpers: Now Playing, Adjust mode, status lines."""

import os
from typing import Optional


def show_now_playing(
    title: str,
    is_playlist: bool = False,
    playlist_pos: Optional[int] = None,
    playlist_count: Optional[int] = None,
    zoom_locked: bool = False,
    zoom_preset_name: Optional[str] = None,
) -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print("========================================")
    print("        NOW PLAYING (YouTube/CRT)")
    print("========================================")
    if playlist_pos is not None and playlist_count is not None:
        print(f"  Playlist: {playlist_pos} / {playlist_count}")
    if title:
        print(f"  Title: {title}")
        print()

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
    print("  [Q]      Quit")
    print("========================================")
    print()


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
) -> None:
    """One-line compact status shown after auto-hide timeout."""
    idx = f" ({pos}/{count})" if pos is not None and count is not None else ""
    print(f"\r  \u25b6  YouTube Playing{idx}    ", end="", flush=True)


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
