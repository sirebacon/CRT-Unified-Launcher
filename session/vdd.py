"""VDD lifecycle helpers: plug/unplug the Moonlight virtual display."""

import ctypes
import time
from typing import Optional

try:
    import win32api
    import win32con
except Exception:
    win32api = None
    win32con = None

from session.display_api import find_display_by_token


def _find_vdd_device_name(token: str) -> Optional[str]:
    """Find a display adapter's DeviceName by token substring, including detached adapters.

    enumerate_attached_displays() filters by DISPLAY_DEVICE_ATTACHED_TO_DESKTOP, so it
    misses adapters that were previously disconnected. This scans all adapters.
    """
    if win32api is None:
        return None
    token_lower = token.lower()
    i = 0
    while True:
        try:
            dev = win32api.EnumDisplayDevices(None, i)
        except Exception:
            break
        i += 1
        if token_lower in (dev.DeviceString or "").lower():
            return dev.DeviceName
        if token_lower in (dev.DeviceName or "").lower():
            return dev.DeviceName
    return None


def _log_all_display_adapters() -> None:
    """Log all display adapters (attached or not) for diagnostics."""
    if win32api is None:
        return
    i = 0
    while True:
        try:
            dev = win32api.EnumDisplayDevices(None, i)
        except Exception:
            break
        i += 1
        attached = (
            bool(dev.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)
            if win32con else False
        )
        print(
            f"[re-stack] VDD diag: [{i}] attached={attached} "
            f"name='{dev.DeviceName}' string='{dev.DeviceString}'"
        )


def unplug_vdd(moonlight_token: str) -> bool:
    """Detach the Moonlight virtual display from the Windows desktop topology.

    Equivalent to 'Disconnect this display' in Display Settings — the device
    driver stays active but the display is removed from the virtual desktop.
    """
    d = find_display_by_token(moonlight_token)
    if not d:
        print("[re-stack] VDD: already detached.")
        return True
    if win32api is None or win32con is None:
        print("[re-stack] VDD: pywin32 unavailable; cannot unplug.")
        return False
    dev_name = d["device_name"]
    try:
        rc = win32api.ChangeDisplaySettingsEx(
            dev_name, None, win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET
        )
        if rc != win32con.DISP_CHANGE_SUCCESSFUL:
            print(f"[re-stack] VDD: unplug failed (code {rc}).")
            return False
        commit_rc = win32api.ChangeDisplaySettingsEx(None, None)
        if commit_rc != win32con.DISP_CHANGE_SUCCESSFUL:
            print(f"[re-stack] VDD: unplug commit failed (code {commit_rc}).")
            return False
        print(f"[re-stack] VDD: unplugged ({dev_name}).")
        return True
    except Exception as e:
        print(f"[re-stack] VDD: unplug error: {e}")
        return False


def plug_vdd_and_wait(moonlight_token: str, timeout_seconds: int = 15) -> bool:
    """Wait for the Moonlight virtual display to be present in the Windows desktop topology.

    Normal path: the SudoMaker VDD is kept attached between sessions (unplug_vdd is not
    called on restore), so Apollo has already attached it and this returns immediately.

    Recovery path: if the VDD was previously soft-disconnected (e.g. unplug_vdd was
    called manually), attempts to re-attach it by enumerating the driver's built-in mode
    list. ENUM_REGISTRY_SETTINGS returns zeros after a NULL-devmode disconnect, but mode
    index enumeration queries the driver directly and returns valid modes even when the
    display is not in the active topology.
    """
    if find_display_by_token(moonlight_token):
        print("[re-stack] VDD: already attached.")
        return True

    # Recovery: find the adapter (even if detached) and attempt re-attachment using
    # the first valid mode reported by the driver itself.
    dev_name = _find_vdd_device_name(moonlight_token)
    if dev_name and win32api is not None and win32con is not None:
        dm = None
        mode_idx = 0
        while True:
            try:
                candidate = win32api.EnumDisplaySettings(dev_name, mode_idx)
                if getattr(candidate, "PelsWidth", 0) > 0 and getattr(candidate, "PelsHeight", 0) > 0:
                    dm = candidate
                    break
            except Exception:
                break
            mode_idx += 1

        if dm is not None:
            try:
                rc = win32api.ChangeDisplaySettingsEx(
                    dev_name, dm,
                    win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET,
                )
                commit_rc = win32api.ChangeDisplaySettingsEx(None, None)
                if rc == win32con.DISP_CHANGE_SUCCESSFUL and commit_rc == win32con.DISP_CHANGE_SUCCESSFUL:
                    print(
                        f"[re-stack] VDD: re-attached {dev_name} using "
                        f"{dm.PelsWidth}x{dm.PelsHeight}@{getattr(dm, 'DisplayFrequency', '?')}Hz."
                    )
                else:
                    print(f"[re-stack] VDD: re-attach attempt failed (rc={rc}, commit={commit_rc}).")
            except Exception as e:
                print(f"[re-stack] VDD: re-attach error: {e}")
        else:
            print(
                f"[re-stack] VDD: no supported modes found for '{dev_name}'; "
                "restart Apollo to restore attachment."
            )

    print(f"[re-stack] VDD: waiting for display to attach (up to {timeout_seconds}s)...")
    for _ in range(timeout_seconds * 2):
        time.sleep(0.5)
        if find_display_by_token(moonlight_token):
            print("[re-stack] VDD: display attached.")
            return True

    print("[re-stack] VDD: display did not attach within timeout.")
    print("[re-stack] VDD: restart Apollo to restore the virtual display.")
    _log_all_display_adapters()
    return False
