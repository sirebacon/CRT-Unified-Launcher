import glob
import os
import shutil
from typing import Dict, List, Tuple


RESTORE_SPECS: Dict[str, Dict] = {
    "Emulators.xml": {
        "target": r"D:\Emulators\LaunchBox\Data\Emulators.xml",
        "patterns": [r"D:\Emulators\LaunchBox\Data\Emulators.*.pre_default_restore.bak"],
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


def restore_defaults_from_backup() -> Tuple[bool, str, List[str]]:
    restored: List[str] = []
    missing: List[str] = []

    for label, spec in RESTORE_SPECS.items():
        source = _latest_match(spec["patterns"])
        if not source:
            missing.append(label)
            continue
        target = spec["target"]
        try:
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

