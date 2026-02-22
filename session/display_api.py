"""Windows display API helpers: enumeration, primary switching, refresh rate."""

import ctypes
import time
from typing import List, Optional, Tuple

try:
    import pywintypes
    import win32api
    import win32con
except Exception:
    pywintypes = None
    win32api = None
    win32con = None


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------

def enumerate_attached_displays() -> List[dict]:
    displays: List[dict] = []
    if win32api is None or win32con is None:
        return displays

    i = 0
    while True:
        try:
            dev = win32api.EnumDisplayDevices(None, i)
        except pywintypes.error:
            break
        i += 1

        if not (dev.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP):
            continue

        try:
            dm = win32api.EnumDisplaySettings(dev.DeviceName, win32con.ENUM_CURRENT_SETTINGS)
            pos = (int(dm.Position_x), int(dm.Position_y))
        except Exception:
            pos = (0, 0)

        monitors: List[str] = []
        j = 0
        while True:
            try:
                mon = win32api.EnumDisplayDevices(dev.DeviceName, j)
            except pywintypes.error:
                break
            j += 1
            if mon.DeviceString:
                monitors.append(mon.DeviceString)

        displays.append(
            {
                "device_name": dev.DeviceName,
                "device_string": dev.DeviceString or "",
                "monitor_strings": monitors,
                "position": pos,
                "state_flags": dev.StateFlags,
            }
        )

    return displays


def find_display_by_token(name_token: str) -> dict:
    token = name_token.lower()
    for d in enumerate_attached_displays():
        haystack = [d["device_name"], d["device_string"], *d["monitor_strings"]]
        if any(token in (item or "").lower() for item in haystack):
            return d
    return {}


def find_display_by_device_name(device_name: str) -> dict:
    for d in enumerate_attached_displays():
        if d["device_name"].lower() == device_name.lower():
            return d
    return {}


def current_primary_display() -> dict:
    for d in enumerate_attached_displays():
        if d["state_flags"] & win32con.DISPLAY_DEVICE_PRIMARY_DEVICE:
            return d
    return {}


def current_primary_device_name() -> str:
    d = current_primary_display()
    return str(d.get("device_name", "")).strip()


# ---------------------------------------------------------------------------
# CRT display rect
# ---------------------------------------------------------------------------

def get_crt_display_rect(crt_tokens: List[str]) -> Optional[Tuple[int, int, int, int]]:
    """Return (x, y, w, h) for the CRT display using live Windows display enumeration."""
    if win32api is None or win32con is None:
        return None
    for token in crt_tokens:
        d = find_display_by_token(token)
        if not d:
            continue
        try:
            dm = win32api.EnumDisplaySettings(d["device_name"], win32con.ENUM_CURRENT_SETTINGS)
            x, y = d["position"]
            w = int(dm.PelsWidth)
            h = int(dm.PelsHeight)
            print(
                f"[re-stack] CRT display detected: {d['device_name']} "
                f"x={x}, y={y}, w={w}, h={h}"
            )
            return (x, y, w, h)
        except Exception as e:
            print(f"[re-stack] Could not read CRT display mode from {d['device_name']}: {e}")
    return None


# ---------------------------------------------------------------------------
# Full display mode (resolution + refresh) — save / restore
# ---------------------------------------------------------------------------

def get_display_mode(display_token: str) -> Optional[dict]:
    """Return the current mode for a display as {device_name, width, height, hz}.

    Returns None if the display cannot be found or queried.
    """
    target = find_display_by_token(display_token)
    if not target or win32api is None or win32con is None:
        return None
    try:
        dm = win32api.EnumDisplaySettings(target["device_name"], win32con.ENUM_CURRENT_SETTINGS)
        return {
            "device_name": target["device_name"],
            "width": int(dm.PelsWidth),
            "height": int(dm.PelsHeight),
            "hz": int(dm.DisplayFrequency),
        }
    except Exception as e:
        print(f"[re-stack] Could not read display mode for {target['device_name']}: {e}")
        return None


def restore_display_mode(saved: dict) -> bool:
    """Apply a previously saved display mode dict (from get_display_mode).

    Sets width, height, and refresh rate together so the mode is valid.
    Returns True on success.
    """
    if not saved or win32api is None or win32con is None:
        return False
    dev = saved.get("device_name", "")
    w, h, hz = saved.get("width"), saved.get("height"), saved.get("hz")
    if not dev or not w or not h or not hz:
        return False
    try:
        dm = win32api.EnumDisplaySettings(dev, win32con.ENUM_CURRENT_SETTINGS)
        dm.PelsWidth = int(w)
        dm.PelsHeight = int(h)
        dm.DisplayFrequency = int(hz)
        dm.Fields |= win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_DISPLAYFREQUENCY
        # Try dynamic-only apply first (flag=0); CDS_UPDATEREGISTRY is rejected by some
        # NVIDIA hybrid-GPU drivers (returns DISP_CHANGE_FAILED=-1) even for valid modes.
        for flags in (0, win32con.CDS_UPDATEREGISTRY):
            rc = win32api.ChangeDisplaySettingsEx(dev, dm, flags)
            if rc == win32con.DISP_CHANGE_SUCCESSFUL:
                print(f"[re-stack] CRT mode restored: {w}x{h}@{hz}Hz on {dev}.")
                return True
        print(f"[re-stack] CRT mode restore failed on {dev} (code {rc}).")
        return False
    except Exception as e:
        print(f"[re-stack] CRT mode restore error on {dev}: {e}")
        return False


# ---------------------------------------------------------------------------
# Refresh rate
# ---------------------------------------------------------------------------

def set_display_refresh_best_effort(display_token: str, refresh_hz: int) -> bool:
    target = find_display_by_token(display_token)
    if not target:
        print(f"[re-stack] Could not find display for refresh token: {display_token}")
        return False
    if win32api is None or win32con is None:
        print("[re-stack] pywin32 display APIs unavailable; cannot set refresh.")
        return False

    dev_name = target["device_name"]
    try:
        dm = win32api.EnumDisplaySettings(dev_name, win32con.ENUM_CURRENT_SETTINGS)
        current = int(getattr(dm, "DisplayFrequency", 0) or 0)
        if current == int(refresh_hz):
            return True
        dm.DisplayFrequency = int(refresh_hz)
        dm.Fields |= win32con.DM_DISPLAYFREQUENCY
        # Try dynamic-only apply first; CDS_UPDATEREGISTRY is rejected by some NVIDIA drivers.
        for flags in (0, win32con.CDS_UPDATEREGISTRY):
            rc = win32api.ChangeDisplaySettingsEx(dev_name, dm, flags)
            if rc == win32con.DISP_CHANGE_SUCCESSFUL:
                print(f"[re-stack] Refresh corrected: {current} Hz -> {refresh_hz} Hz on {dev_name}.")
                return True
        print(
            f"[re-stack] Failed to correct refresh from {current} Hz to {refresh_hz} Hz "
            f"on {dev_name} (code {rc})."
        )
        return False
    except Exception as e:
        print(f"[re-stack] Refresh switch error on {dev_name}: {e}")
        return False


# ---------------------------------------------------------------------------
# Primary display switching
# ---------------------------------------------------------------------------

def set_primary_via_setdisplayconfig(target_device_name: str) -> bool:
    """Set primary display using SetDisplayConfig.

    Repositions all source modes so target lands at (0, 0), which is how Windows
    determines the primary monitor. Works with virtual display drivers that reject
    ChangeDisplaySettingsEx CDS_SET_PRIMARY.
    """
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return False

    QDC_ONLY_ACTIVE_PATHS = 0x00000002
    SDC_APPLY = 0x00000080
    SDC_USE_SUPPLIED_DISPLAY_CONFIG = 0x00000020
    SDC_SAVE_TO_DATABASE = 0x00000200
    SDC_ALLOW_CHANGES = 0x00000400
    DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1
    DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE = 1
    ERROR_SUCCESS = 0

    class _LUID(ctypes.Structure):
        _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]

    class _Rational(ctypes.Structure):
        _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]

    class _2DRegion(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_uint32), ("cy", ctypes.c_uint32)]

    class _VideoSignalInfo(ctypes.Structure):
        _fields_ = [
            ("pixelRate", ctypes.c_uint64),
            ("hSyncFreq", _Rational),
            ("vSyncFreq", _Rational),
            ("activeSize", _2DRegion),
            ("totalSize", _2DRegion),
            ("videoStandard", ctypes.c_uint32),
            ("scanLineOrdering", ctypes.c_int),
        ]

    class _TargetMode(ctypes.Structure):
        _fields_ = [("targetVideoSignalInfo", _VideoSignalInfo)]

    class _POINTL(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class _SourceMode(ctypes.Structure):
        _fields_ = [
            ("width", ctypes.c_uint32),
            ("height", ctypes.c_uint32),
            ("pixelFormat", ctypes.c_int),
            ("position", _POINTL),
        ]

    class _ModeInfoUnion(ctypes.Union):
        _fields_ = [("targetMode", _TargetMode), ("sourceMode", _SourceMode)]

    class _ModeInfo(ctypes.Structure):
        _fields_ = [
            ("infoType", ctypes.c_int),
            ("id", ctypes.c_uint32),
            ("adapterId", _LUID),
            ("info", _ModeInfoUnion),
        ]

    class _PathSourceInfo(ctypes.Structure):
        _fields_ = [
            ("adapterId", _LUID),
            ("id", ctypes.c_uint32),
            ("modeInfoIdx", ctypes.c_uint32),
            ("statusFlags", ctypes.c_uint32),
        ]

    class _PathTargetInfo(ctypes.Structure):
        _fields_ = [
            ("adapterId", _LUID),
            ("id", ctypes.c_uint32),
            ("modeInfoIdx", ctypes.c_uint32),
            ("outputTechnology", ctypes.c_int),
            ("rotation", ctypes.c_int),
            ("scaling", ctypes.c_int),
            ("refreshRate", _Rational),
            ("scanLineOrdering", ctypes.c_int),
            ("targetAvailable", ctypes.c_int),
            ("statusFlags", ctypes.c_uint32),
        ]

    class _PathInfo(ctypes.Structure):
        _fields_ = [
            ("sourceInfo", _PathSourceInfo),
            ("targetInfo", _PathTargetInfo),
            ("flags", ctypes.c_uint32),
        ]

    class _DeviceInfoHeader(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_int),
            ("size", ctypes.c_uint32),
            ("adapterId", _LUID),
            ("id", ctypes.c_uint32),
        ]

    class _SourceDeviceName(ctypes.Structure):
        _fields_ = [
            ("header", _DeviceInfoHeader),
            ("viewGdiDeviceName", ctypes.c_wchar * 32),
        ]

    try:
        num_paths = ctypes.c_uint32()
        num_modes = ctypes.c_uint32()
        ret = user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS, ctypes.byref(num_paths), ctypes.byref(num_modes)
        )
        if ret != ERROR_SUCCESS:
            print(f"[re-stack] SetDisplayConfig: GetDisplayConfigBufferSizes failed ({ret}).")
            return False

        paths = (_PathInfo * num_paths.value)()
        modes = (_ModeInfo * num_modes.value)()
        ret = user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths), paths,
            ctypes.byref(num_modes), modes,
            None,
        )
        if ret != ERROR_SUCCESS:
            print(f"[re-stack] SetDisplayConfig: QueryDisplayConfig failed ({ret}).")
            return False

        want = target_device_name.lower().rstrip("\x00")
        target_src_id = None
        target_adapter = None
        for i in range(num_paths.value):
            info = _SourceDeviceName()
            info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
            info.header.size = ctypes.sizeof(_SourceDeviceName)
            info.header.adapterId = paths[i].sourceInfo.adapterId
            info.header.id = paths[i].sourceInfo.id
            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)) == ERROR_SUCCESS:
                gdi = info.viewGdiDeviceName.lower().rstrip("\x00")
                if gdi == want:
                    target_src_id = paths[i].sourceInfo.id
                    target_adapter = paths[i].sourceInfo.adapterId
                    break

        if target_src_id is None:
            print(f"[re-stack] SetDisplayConfig: no source matched '{target_device_name}'.")
            return False

        tx, ty = None, None
        for i in range(num_modes.value):
            m = modes[i]
            if (
                m.infoType == DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE
                and m.id == target_src_id
                and m.adapterId.LowPart == target_adapter.LowPart
                and m.adapterId.HighPart == target_adapter.HighPart
            ):
                tx = m.info.sourceMode.position.x
                ty = m.info.sourceMode.position.y
                break

        if tx is None:
            print("[re-stack] SetDisplayConfig: target source mode not found in mode list.")
            return False

        if tx == 0 and ty == 0:
            print("[re-stack] SetDisplayConfig: target already at (0,0) — already primary.")
            return True

        for i in range(num_modes.value):
            if modes[i].infoType == DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE:
                modes[i].info.sourceMode.position.x -= tx
                modes[i].info.sourceMode.position.y -= ty

        flags = (
            SDC_APPLY
            | SDC_USE_SUPPLIED_DISPLAY_CONFIG
            | SDC_SAVE_TO_DATABASE
            | SDC_ALLOW_CHANGES
        )
        ret = user32.SetDisplayConfig(
            num_paths.value, paths,
            num_modes.value, modes,
            flags,
        )
        if ret == ERROR_SUCCESS:
            print(f"[re-stack] SetDisplayConfig: primary set to '{target_device_name}'.")
            return True
        print(f"[re-stack] SetDisplayConfig failed (code {ret}).")
        return False

    except Exception as e:
        print(f"[re-stack] SetDisplayConfig exception: {e}")
        return False


def set_primary_display_entry(target: dict) -> bool:
    if win32api is None or win32con is None:
        print("[re-stack] pywin32 display APIs unavailable; cannot set primary display.")
        return False
    if not target:
        return False

    displays = enumerate_attached_displays()
    current_primary = current_primary_display()
    if current_primary and current_primary.get("device_name") == target.get("device_name"):
        print(f"[re-stack] Target already primary: {target['device_name']}")
        return True

    tx, ty = target["position"]

    methods = [
        ("keep_pos", None, None, win32con.DM_POSITION),
        ("zero_pos", 0, 0, win32con.DM_POSITION),
        ("no_pos_change", None, None, 0),
    ]
    target_set = False
    for label, px, py, field_mask in methods:
        try:
            target_dm = win32api.EnumDisplaySettings(
                target["device_name"], win32con.ENUM_CURRENT_SETTINGS
            )
            if field_mask & win32con.DM_POSITION:
                if px is None or py is None:
                    pass
                else:
                    target_dm.Position_x = px
                    target_dm.Position_y = py
                target_dm.Fields |= win32con.DM_POSITION

            target_flags = (
                win32con.CDS_UPDATEREGISTRY
                | win32con.CDS_NORESET
                | win32con.CDS_SET_PRIMARY
            )
            target_rc = win32api.ChangeDisplaySettingsEx(
                target["device_name"], target_dm, target_flags
            )
            if target_rc == win32con.DISP_CHANGE_SUCCESSFUL:
                print(
                    f"[re-stack] Target primary set using method '{label}' "
                    f"for {target['device_name']}."
                )
                target_set = True
                break
            print(
                f"[re-stack] Target primary method '{label}' failed "
                f"for {target['device_name']} (code {target_rc})."
            )
        except Exception as e:
            print(
                f"[re-stack] Display switch exception with method '{label}' "
                f"on target {target['device_name']}: {e}"
            )

    if not target_set:
        print("[re-stack] ChangeDisplaySettingsEx methods exhausted; trying SetDisplayConfig.")
        return set_primary_via_setdisplayconfig(target["device_name"])

    # Reposition non-primary displays relative to the new origin.
    # (SetDisplayConfig handles this atomically when used as fallback.)
    for d in displays:
        if d["device_name"] == target["device_name"]:
            continue
        try:
            dm = win32api.EnumDisplaySettings(d["device_name"], win32con.ENUM_CURRENT_SETTINGS)
            dm.Position_x = int(dm.Position_x - tx)
            dm.Position_y = int(dm.Position_y - ty)
            dm.Fields |= win32con.DM_POSITION
            rc = win32api.ChangeDisplaySettingsEx(
                d["device_name"],
                dm,
                win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET,
            )
            if rc != win32con.DISP_CHANGE_SUCCESSFUL:
                print(
                    f"[re-stack] Warning: failed repositioning '{d['device_name']}' "
                    f"(code {rc})."
                )
        except Exception as e:
            print(f"[re-stack] Warning: display reposition error on {d['device_name']}: {e}")

    final_rc = win32api.ChangeDisplaySettingsEx(None, None)
    if final_rc != win32con.DISP_CHANGE_SUCCESSFUL:
        print(f"[re-stack] Failed to commit display changes (code {final_rc}).")
        return False
    return True


def set_primary_display(name_token: str) -> bool:
    target = find_display_by_token(name_token)
    if not target:
        print(f"[re-stack] Could not find display matching token: {name_token}")
        return False
    ok = set_primary_display_entry(target)
    if ok:
        print(f"[re-stack] Primary display set using token: {name_token}")
    return ok


def set_primary_display_verified(name_token: str, retries: int = 3) -> bool:
    target = find_display_by_token(name_token)
    if not target:
        print(f"[re-stack] Could not find display matching token: {name_token}")
        return False
    wanted = str(target.get("device_name", "")).strip().lower()

    for attempt in range(1, retries + 1):
        if not set_primary_display(name_token):
            continue
        active = current_primary_device_name().lower()
        if active == wanted:
            print(f"[re-stack] Verified primary display: {target['device_name']}")
            return True
        print(
            f"[re-stack] Primary verify failed (attempt {attempt}/{retries}). "
            f"Expected {target['device_name']}, got {active or 'UNKNOWN'}."
        )
        time.sleep(0.5)
    return False
