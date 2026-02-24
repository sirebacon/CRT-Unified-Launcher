import glob
import os
import shutil
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple


RESTORE_SPECS: Dict[str, Dict] = {
    "Emulators.xml": {
        "target": r"D:\Emulators\LaunchBox\Data\Emulators.xml",
        "patterns": [r"D:\Emulators\LaunchBox\Data\Emulators.*.pre_default_restore.bak"],
        # Fallback scan to recover from a bad pre_default_restore snapshot that already
        # contains wrapper paths.
        "fallback_patterns": [r"D:\Emulators\LaunchBox\Data\Emulators*.bak"],
    },
    "BigBoxSettings.xml": {
        "target": r"D:\Emulators\LaunchBox\Data\BigBoxSettings.xml",
        "patterns": [r"D:\Emulators\LaunchBox\Data\BigBoxSettings.*.pre_default_restore.bak"],
    },
    "Settings.xml": {
        "target": r"D:\Emulators\LaunchBox\Data\Settings.xml",
        "patterns": [r"D:\Emulators\LaunchBox\Data\Settings.*.pre_default_restore.bak"],
    },
    "retroarch.cfg": {
        "target": r"D:\Emulators\RetroArch-Win64\retroarch.cfg",
        "patterns": [r"D:\Emulators\RetroArch-Win64\retroarch.*.pre_default_restore.bak"],
    },
}


def _latest_match(patterns: List[str]) -> str:
    candidates: List[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    if not candidates:
        return ""
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _all_matches(patterns: List[str]) -> List[str]:
    candidates: List[str] = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    return sorted(set(candidates), key=lambda p: os.path.getmtime(p), reverse=True)


def _emulators_backup_is_sane(path: str) -> bool:
    """Reject LaunchBox emulator backups that still point at CRT wrapper bat files."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return False

    wrapper_markers = (
        "launchbox_retroarch_wrapper",
        "launchbox_ppsspp_wrapper",
        "launchbox_dolphin_wrapper",
        "launchbox_pcsx2_wrapper",
    )
    tracked_emulators = {"retroarch", "ppsspp", "dolphin", "pcsx2"}

    for emulator in root.findall("Emulator"):
        title = (emulator.findtext("Title") or "").strip().lower()
        if title not in tracked_emulators:
            continue
        app_path = (emulator.findtext("ApplicationPath") or "").strip().lower()
        if any(marker in app_path for marker in wrapper_markers):
            return False
    return True


def _choose_restore_source(label: str, spec: Dict) -> str:
    source = _latest_match(spec["patterns"])
    if label != "Emulators.xml":
        return source

    if source and _emulators_backup_is_sane(source):
        return source

    for candidate in _all_matches(spec.get("fallback_patterns", [])):
        if _emulators_backup_is_sane(candidate):
            return candidate

    return source


def _read_retroarch_cfg_values(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if " = " not in line:
                    continue
                key, value = line.split(" = ", 1)
                values[key.strip()] = value.strip()
    except Exception:
        return {}
    return values


def _restore_retroarch_cfg_preserving_window_placement(source: str, target: str) -> None:
    """Restore retroarch.cfg but preserve the user's current monitor index.

    force_keys are always written to a fixed value regardless of backup or current config.
    video_windowed_fullscreen is forced to false so RetroArch uses position coordinates
    instead of filling the primary monitor (which may be SudoMaker after an RE session).
    """
    preserve_keys = {
        "video_monitor_index",
    }
    force_keys = {
        "video_windowed_fullscreen": '"false"',
    }
    current_values = _read_retroarch_cfg_values(target)

    with open(source, "r", encoding="utf-8-sig") as f:
        lines = f.read().splitlines()

    replaced = set()
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if " = " not in stripped:
            out.append(line)
            continue
        key = stripped.split(" = ", 1)[0].strip()
        if key in force_keys:
            out.append(f"{key} = {force_keys[key]}")
            replaced.add(key)
        elif key in preserve_keys and key in current_values:
            out.append(f"{key} = {current_values[key]}")
            replaced.add(key)
        else:
            out.append(line)

    for key in preserve_keys:
        if key in current_values and key not in replaced:
            out.append(f"{key} = {current_values[key]}")
    for key, val in force_keys.items():
        if key not in replaced:
            out.append(f"{key} = {val}")

    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def restore_defaults_from_backup() -> Tuple[bool, str, List[str]]:
    restored: List[str] = []
    missing: List[str] = []

    for label, spec in RESTORE_SPECS.items():
        source = _choose_restore_source(label, spec)
        if not source:
            missing.append(label)
            continue
        target = spec["target"]
        try:
            if label == "retroarch.cfg" and os.path.exists(target):
                _restore_retroarch_cfg_preserving_window_placement(source, target)
            else:
                shutil.copy2(source, target)
            restored.append(f"{label} <- {source}")
        except Exception as e:
            return False, f"Failed restoring {label}: {e}", restored

    if missing:
        return (
            False,
            "Missing backup(s) for: " + ", ".join(missing),
            restored,
        )

    return True, "Default settings restored from backup files.", restored
