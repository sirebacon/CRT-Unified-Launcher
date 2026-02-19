import json
import os
import re
import shutil
import tempfile
from typing import Dict, Optional, Tuple
import xml.etree.ElementTree as ET


FILES = {
    "emulators": r"D:\LaunchBox\Data\Emulators.xml",
    "bigbox": r"D:\LaunchBox\Data\BigBoxSettings.xml",
    "settings": r"D:\LaunchBox\Data\Settings.xml",
}


def _load_json_config() -> Dict:
    with open("crt_config.json", "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _backup_files() -> str:
    backup_dir = tempfile.mkdtemp(prefix="crt_session_")
    for path in FILES.values():
        shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    return backup_dir


def _save_tree(tree: ET.ElementTree, path: str) -> None:
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _set_text(parent: ET.Element, tag: str, value: str) -> None:
    node = parent.find(tag)
    if node is None:
        node = ET.SubElement(parent, tag)
    node.text = value


def _patch_bigbox(bigbox_path: str, monitor_index: int) -> None:
    tree = ET.parse(bigbox_path)
    root = tree.getroot()
    settings = root.find("BigBoxSettings")
    if settings is None:
        raise RuntimeError("BigBoxSettings node not found")

    _set_text(settings, "PrimaryMonitorIndex", str(monitor_index))
    _set_text(settings, "ShowStartupSplashScreen", "false")
    _set_text(settings, "ShowLoadingGameMessage", "false")
    _set_text(settings, "UseStartupScreen", "false")
    _set_text(settings, "HideMouseCursorOnStartupScreens", "false")
    _save_tree(tree, bigbox_path)


def _patch_launchbox_settings(settings_path: str) -> None:
    tree = ET.parse(settings_path)
    root = tree.getroot()
    settings = root.find("Settings")
    if settings is None:
        raise RuntimeError("Settings node not found")

    _set_text(settings, "ShowLaunchBoxSplashScreen", "false")
    _set_text(settings, "UseStartupScreen", "false")
    _set_text(settings, "HideMouseCursorOnStartupScreens", "false")
    _save_tree(tree, settings_path)


def _patch_emulators(emulators_path: str) -> None:
    tree = ET.parse(emulators_path)
    root = tree.getroot()

    retro_id: Optional[str] = None
    for emulator in root.findall("Emulator"):
        title = (emulator.findtext("Title") or "").strip().lower()
        if title == "retroarch":
            retro_id = (emulator.findtext("ID") or "").strip()
            _set_text(emulator, "UseStartupScreen", "false")
            _set_text(emulator, "StartupLoadDelay", "0")
            _set_text(emulator, "HideMouseCursorInGame", "false")
            break

    if retro_id:
        for platform in root.findall("EmulatorPlatform"):
            if (platform.findtext("Emulator") or "").strip() != retro_id:
                continue
            cmd_node = platform.find("CommandLine")
            if cmd_node is None or cmd_node.text is None:
                continue
            cmd = cmd_node.text
            cmd = re.sub(r"(^|\s)-f(?=\s|$)", r"\1", cmd).strip()
            cmd_node.text = cmd

    _save_tree(tree, emulators_path)


def apply_crt_session_mode() -> Tuple[bool, str, Optional[str]]:
    try:
        cfg = _load_json_config()
        monitor_index = int(cfg.get("launcher_integration", {}).get("main_monitor_index", 1))
        backup_dir = _backup_files()

        _patch_bigbox(FILES["bigbox"], monitor_index)
        _patch_launchbox_settings(FILES["settings"])
        _patch_emulators(FILES["emulators"])
        return True, "CRT session mode applied.", backup_dir
    except Exception as e:
        return False, f"Failed to apply CRT session mode: {e}", None


def restore_session_mode(backup_dir: str) -> Tuple[bool, str]:
    try:
        for key, path in FILES.items():
            src = os.path.join(backup_dir, os.path.basename(path))
            shutil.copy2(src, path)
        shutil.rmtree(backup_dir, ignore_errors=True)
        return True, "Restored default settings from session backup."
    except Exception as e:
        return False, f"Failed to restore session mode backup: {e}"
