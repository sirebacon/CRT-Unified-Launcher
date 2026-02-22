"""VDD lifecycle helpers: plug/unplug the Moonlight virtual display."""

import ctypes
import time

try:
    import win32api
    import win32con
except Exception:
    win32api = None
    win32con = None

from session.display_api import find_display_by_token


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
    """Re-attach the Moonlight virtual display to the Windows desktop topology.

    Uses SetDisplayConfig extend topology so Windows re-adds all available
    displays. Polls until the display appears or timeout is reached.
    """
    if find_display_by_token(moonlight_token):
        print("[re-stack] VDD: already attached.")
        return True
    try:
        SDC_TOPOLOGY_EXTEND = 0x00000004
        SDC_APPLY = 0x00000080
        SDC_ALLOW_CHANGES = 0x00000400
        ret = ctypes.windll.user32.SetDisplayConfig(
            0, None, 0, None,
            SDC_TOPOLOGY_EXTEND | SDC_APPLY | SDC_ALLOW_CHANGES,
        )
        if ret != 0:
            print(f"[re-stack] VDD: plug in failed (SetDisplayConfig code {ret}).")
            return False
    except Exception as e:
        print(f"[re-stack] VDD: plug in error: {e}")
        return False
    print(f"[re-stack] VDD: waiting for display to attach (up to {timeout_seconds}s)...")
    for _ in range(timeout_seconds * 2):
        if find_display_by_token(moonlight_token):
            print("[re-stack] VDD: display attached.")
            return True
        time.sleep(0.5)
    print("[re-stack] VDD: display did not attach within timeout.")
    return False
