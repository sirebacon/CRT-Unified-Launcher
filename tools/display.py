"""Display diagnostics and recovery commands for crt_tools."""

import time
from typing import Any, Dict, List, Optional

try:
    import win32api
    import win32con
except Exception:
    win32api = None
    win32con = None

from session.display_api import (
    current_primary_display,
    enumerate_attached_displays,
    find_display_by_token,
    get_display_mode,
    get_rational_refresh_map,
    set_display_refresh_best_effort,
    set_primary_display_verified,
)
from session.re_config import (
    CRT_DISPLAY_TOKEN,
    CRT_TARGET_REFRESH_HZ,
    RE_PRIMARY_DISPLAY_TOKEN,
    RESTORE_PRIMARY_DISPLAY_TOKEN,
)


# ---------------------------------------------------------------------------
# display dump
# ---------------------------------------------------------------------------

def display_dump() -> Dict[str, Any]:
    displays = enumerate_attached_displays()
    primary = current_primary_display()
    primary_name = str(primary.get("device_name", "")).lower()
    rational_map = get_rational_refresh_map()

    rows: List[Dict[str, Any]] = []
    for d in displays:
        device_name = d.get("device_name", "")
        mode = get_display_mode(device_name) if device_name else None
        if mode and device_name:
            rational = rational_map.get(device_name.lower())
            if rational:
                mode["rational_hz"] = rational  # (numerator, denominator)
        rows.append(
            {
                "device_name": device_name,
                "device_string": d.get("device_string", ""),
                "monitor_strings": d.get("monitor_strings", []),
                "position": d.get("position", (0, 0)),
                "state_flags": d.get("state_flags", 0),
                "is_primary": str(device_name).lower() == primary_name,
                "mode": mode,
            }
        )

    token_map = {
        "re_primary_token": RE_PRIMARY_DISPLAY_TOKEN,
        "crt_token": CRT_DISPLAY_TOKEN,
        "restore_primary_token": RESTORE_PRIMARY_DISPLAY_TOKEN,
    }
    token_resolution: Dict[str, Any] = {}
    for key, token in token_map.items():
        match = find_display_by_token(token)
        token_resolution[key] = {
            "token": token,
            "matched": bool(match),
            "device_name": match.get("device_name", "") if match else "",
            "device_string": match.get("device_string", "") if match else "",
        }

    return {
        "displays": rows,
        "token_resolution": token_resolution,
        "primary": primary,
    }


def print_display_dump(data: Dict[str, Any]) -> int:
    displays = data.get("displays", [])
    if not displays:
        print("[tools] FAIL: display dump -- no attached displays found or display API unavailable")
        return 1

    print("Display dump (attached displays)")
    print()
    for d in displays:
        x, y = d.get("position", (0, 0))
        mode = d.get("mode") or {}
        hz = mode.get("hz", "?")
        w = mode.get("width", "?")
        h = mode.get("height", "?")
        rational = mode.get("rational_hz")
        if rational:
            n, denom = rational
            exact_hz = f"{n}/{denom}"
            hz_str = f"{hz}Hz  ({exact_hz} = {n / denom:.4f} Hz)"
        else:
            hz_str = f"{hz}Hz"
        prefix = "[PRIMARY] " if d.get("is_primary") else "          "
        mons = ", ".join(d.get("monitor_strings") or []) or "(none)"
        print(
            f"{prefix}{d.get('device_name')} | {d.get('device_string')} | "
            f"pos=({x},{y}) | {w}x{h}@{hz_str}"
        )
        print(f"          monitors={mons}")

    print()
    print("Token resolution:")
    for key, info in (data.get("token_resolution") or {}).items():
        if info["matched"]:
            device = f"{info['device_name']} ({info['device_string']})"
            status = "OK  "
        else:
            device = "(no attached display matches)"
            status = "MISS"
        print(f"  [{status}] {key}: {info['token']!r}")
        print(f"          -> {device}")

    fail = sum(1 for v in (data.get("token_resolution") or {}).values() if not v["matched"])
    if fail:
        print(f"\n[tools] WARN: display dump -- {fail} token(s) did not resolve to an attached display")
    return 0


# ---------------------------------------------------------------------------
# display modes
# ---------------------------------------------------------------------------

def display_modes(display_token: Optional[str] = None) -> Dict[str, Any]:
    """Enumerate driver-reported modes for one or all attached displays."""
    if win32api is None or win32con is None:
        return {"error": "pywin32 unavailable", "displays": []}

    if display_token:
        d = find_display_by_token(display_token)
        if not d:
            return {"error": f"no display matches token: {display_token!r}", "displays": []}
        targets = [d]
    else:
        targets = enumerate_attached_displays()

    result: List[Dict[str, Any]] = []
    for d in targets:
        dev_name = d.get("device_name", "")
        modes: List[Dict[str, int]] = []
        seen: set = set()
        idx = 0
        while True:
            try:
                dm = win32api.EnumDisplaySettings(dev_name, idx)
                w = int(getattr(dm, "PelsWidth", 0))
                h = int(getattr(dm, "PelsHeight", 0))
                hz = int(getattr(dm, "DisplayFrequency", 0))
                key = (w, h, hz)
                if w > 0 and h > 0 and key not in seen:
                    seen.add(key)
                    modes.append({"w": w, "h": h, "hz": hz})
            except Exception:
                break
            idx += 1
        modes.sort(key=lambda m: (-m["w"], -m["h"], -m["hz"]))
        result.append(
            {
                "device_name": dev_name,
                "device_string": d.get("device_string", ""),
                "monitor_strings": d.get("monitor_strings", []),
                "modes": modes,
            }
        )
    return {"displays": result}


def print_display_modes(data: Dict[str, Any]) -> int:
    if data.get("error"):
        print(f"[tools] FAIL: display modes -- {data['error']}")
        return 1
    for d in data.get("displays", []):
        mons = ", ".join(d.get("monitor_strings") or []) or "(none)"
        print(f"{d['device_name']} | {d['device_string']} | monitors={mons}")
        modes = d.get("modes", [])
        if not modes:
            print("  (no modes returned by driver)")
        for m in modes:
            print(f"  {m['w']}x{m['h']}@{m['hz']}Hz")
        print()
    return 0


# ---------------------------------------------------------------------------
# display vdd
# ---------------------------------------------------------------------------

def display_vdd() -> Dict[str, Any]:
    """Check SudoMaker VDD presence and attachment status."""
    token = RE_PRIMARY_DISPLAY_TOKEN
    token_lower = token.lower()

    dev_name: Optional[str] = None
    dev_string: Optional[str] = None

    # Scan all adapters including detached -- enumerate_attached_displays() would miss them
    if win32api is not None:
        i = 0
        while True:
            try:
                dev = win32api.EnumDisplayDevices(None, i)
            except Exception:
                break
            i += 1
            if (token_lower in (dev.DeviceString or "").lower()
                    or token_lower in (dev.DeviceName or "").lower()):
                dev_name = dev.DeviceName
                dev_string = dev.DeviceString
                break

    attached_display = find_display_by_token(token)
    attached = bool(attached_display)

    # Enumerate driver-reported modes (works even when detached)
    modes: List[Dict[str, int]] = []
    if dev_name and win32api is not None and win32con is not None:
        idx = 0
        while True:
            try:
                dm = win32api.EnumDisplaySettings(dev_name, idx)
                w = int(getattr(dm, "PelsWidth", 0))
                h = int(getattr(dm, "PelsHeight", 0))
                hz = int(getattr(dm, "DisplayFrequency", 0))
                if w > 0 and h > 0:
                    modes.append({"w": w, "h": h, "hz": hz})
            except Exception:
                break
            idx += 1

    return {
        "token": token,
        "dev_name": dev_name,
        "dev_string": dev_string,
        "found": dev_name is not None,
        "attached": attached,
        "mode_count": len(modes),
        "first_mode": modes[0] if modes else None,
    }


def print_display_vdd(data: Dict[str, Any]) -> int:
    print("VDD status")
    print(f"  Token    : {data['token']!r}")
    if not data["found"]:
        print("  Adapter  : NOT FOUND")
        print("  (SudoMaker adapter not present at any DISPLAY slot -- is Apollo installed?)")
        return 1
    print(f"  Adapter  : {data['dev_name']} ({data['dev_string']})")
    print(f"  Attached : {'yes  (DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)' if data['attached'] else 'NO  (not in active topology)'}")
    print(f"  Modes    : {data['mode_count']} driver-reported mode(s)", end="")
    if data["first_mode"]:
        m = data["first_mode"]
        print(f"  first valid: {m['w']}x{m['h']}@{m['hz']}Hz")
    else:
        print()
        print("  (no modes -- driver may need Apollo to be running)")
    if not data["attached"]:
        print()
        print("  VDD is not attached. If Apollo is running, start a session to let it re-attach.")
        print("  If recovery is needed, run: python launch_resident_evil_stack.py restore")
    return 0 if data["attached"] else 1


# ---------------------------------------------------------------------------
# display token
# ---------------------------------------------------------------------------

def display_token_resolve(token: str) -> Dict[str, Any]:
    """Resolve a token string to the display it matches."""
    match = find_display_by_token(token)
    if not match:
        return {"token": token, "matched": False}
    mode = get_display_mode(match.get("device_name", ""))
    return {
        "token": token,
        "matched": True,
        "device_name": match.get("device_name", ""),
        "device_string": match.get("device_string", ""),
        "monitor_strings": match.get("monitor_strings", []),
        "position": match.get("position", (0, 0)),
        "mode": mode,
    }


def print_display_token(data: Dict[str, Any]) -> int:
    token = data.get("token", "")
    if not data.get("matched"):
        print(f"[tools] MISS: display token -- {token!r} -> no attached display matches")
        return 1
    x, y = data.get("position", (0, 0))
    mode = data.get("mode") or {}
    hz = mode.get("hz", "?")
    w = mode.get("width", "?")
    h = mode.get("height", "?")
    mons = ", ".join(data.get("monitor_strings") or []) or "(none)"
    print(f"Token: {token!r}")
    print(f"  Match found   : yes")
    print(f"  Device name   : {data['device_name']}")
    print(f"  Device string : {data['device_string']}")
    print(f"  Monitor(s)    : {mons}")
    print(f"  Position      : ({x}, {y})")
    print(f"  Resolution    : {w}x{h} @ {hz} Hz")
    return 0


# ---------------------------------------------------------------------------
# display restore  (mutating)
# ---------------------------------------------------------------------------

def display_restore(primary_only: bool = False, force: bool = False) -> int:
    """Restore primary display and (optionally) CRT refresh rate."""
    print("Display restore:")
    print(f"  Primary    -> {RESTORE_PRIMARY_DISPLAY_TOKEN!r}")
    if not primary_only:
        print(f"  CRT refresh-> {CRT_TARGET_REFRESH_HZ} Hz  (token: {CRT_DISPLAY_TOKEN!r})")

    if not force:
        ans = input("Apply? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("[tools] PASS: display restore -- cancelled")
            return 0

    ok_primary = set_primary_display_verified(RESTORE_PRIMARY_DISPLAY_TOKEN)
    if ok_primary:
        print("[tools] PASS: display restore -- primary restored")
    else:
        print("[tools] WARN: display restore -- primary restore failed or could not be verified")

    if primary_only:
        return 0 if ok_primary else 1

    # After a primary switch the NVIDIA hybrid-GPU driver enters a transitional
    # state. Wait briefly before applying the CRT mode change.
    print("[tools] Waiting for driver to settle after primary switch...")
    time.sleep(2.0)

    ok_crt = set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    if ok_crt:
        print(f"[tools] PASS: display restore -- CRT refresh set to {CRT_TARGET_REFRESH_HZ} Hz")
    else:
        print("[tools] WARN: display restore -- CRT refresh restore failed")

    return 0 if (ok_primary and ok_crt) else 1
