"""LaunchBox XML patch handlers.

Two entry points:

    apply_emulator(path, emulators)
        Patches Emulators.xml: sets ApplicationPath and optional XML fields on
        each named emulator, then strips fullscreen arguments from the matching
        EmulatorPlatform CommandLine entries.

    apply_settings(bigbox_path, settings_path, monitor_index, disable_splash_screens)
        Patches BigBoxSettings.xml and Settings.xml.

Both functions write the file back using the same encoding and declaration that
ElementTree uses (UTF-8 with XML declaration), which matches what option 2
currently produces.
"""
import re
import xml.etree.ElementTree as ET
from typing import Dict, List


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_text(parent: ET.Element, tag: str, value: str) -> None:
    """Set or create a child element's text."""
    node = parent.find(tag)
    if node is None:
        node = ET.SubElement(parent, tag)
    node.text = value


def _save_tree(tree: ET.ElementTree, path: str) -> None:
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _strip_arg_pattern(arg: str) -> str:
    """Build a word-boundary regex pattern that matches `arg` in a command string.

    Splits arg on whitespace so that multi-word args like
    '-C Dolphin.Display.Fullscreen=True' produce a pattern that tolerates
    any amount of whitespace between tokens.
    """
    tokens = arg.split()
    escaped = r"\s+".join(re.escape(t) for t in tokens)
    return rf"(^|\s){escaped}(?=\s|$)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_emulator(path: str, emulators: List[Dict]) -> None:
    """Patch Emulators.xml for the listed emulators.

    Each entry in `emulators` is a dict with:
        title       - emulator name matched case-insensitively against <Title>
        wrapper_bat - new <ApplicationPath> value
        strip_args  - list of command-line arg strings to remove from every
                      matching EmulatorPlatform <CommandLine>
        xml_fields  - dict of additional XML elements to set on the Emulator
                      node (e.g. UseStartupScreen, StartupLoadDelay)
    """
    tree = ET.parse(path)
    root = tree.getroot()

    # First pass: patch Emulator nodes and record their IDs.
    # title_lower -> (em_cfg dict, id_str or None)
    title_map: Dict[str, tuple] = {
        em["title"].lower(): (em, None) for em in emulators
    }

    for emulator in root.findall("Emulator"):
        title = (emulator.findtext("Title") or "").strip().lower()
        if title not in title_map:
            continue
        em_cfg, _ = title_map[title]
        em_id = (emulator.findtext("ID") or "").strip()
        title_map[title] = (em_cfg, em_id)

        _set_text(emulator, "ApplicationPath", em_cfg["wrapper_bat"])
        for field, value in em_cfg.get("xml_fields", {}).items():
            _set_text(emulator, field, value)

    # Second pass: strip fullscreen args from EmulatorPlatform CommandLine.
    id_to_cfg: Dict[str, Dict] = {
        em_id: em_cfg
        for em_cfg, em_id in title_map.values()
        if em_id is not None
    }

    for platform in root.findall("EmulatorPlatform"):
        em_id = (platform.findtext("Emulator") or "").strip()
        em_cfg = id_to_cfg.get(em_id)
        if em_cfg is None:
            continue
        cmd_node = platform.find("CommandLine")
        if cmd_node is None or cmd_node.text is None:
            continue
        cmd = cmd_node.text
        for arg in em_cfg.get("strip_args", []):
            cmd = re.sub(_strip_arg_pattern(arg), r"\1", cmd).strip()
        cmd_node.text = cmd

    _save_tree(tree, path)


def apply_settings(
    bigbox_path: str,
    settings_path: str,
    monitor_index: int,
    disable_splash_screens: bool,
) -> None:
    """Patch BigBoxSettings.xml and Settings.xml.

    Args:
        bigbox_path:            Path to BigBoxSettings.xml.
        settings_path:          Path to Settings.xml.
        monitor_index:          Zero-based index of the CRT monitor to use.
        disable_splash_screens: When True, disables all startup splash screens
                                in both files.
    """
    # --- BigBoxSettings.xml ---
    tree = ET.parse(bigbox_path)
    root = tree.getroot()
    settings = root.find("BigBoxSettings")
    if settings is None:
        raise RuntimeError(f"BigBoxSettings node not found in {bigbox_path}")
    _set_text(settings, "PrimaryMonitorIndex", str(monitor_index))
    if disable_splash_screens:
        _set_text(settings, "ShowStartupSplashScreen", "false")
        _set_text(settings, "ShowLoadingGameMessage", "false")
        _set_text(settings, "UseStartupScreen", "false")
        _set_text(settings, "HideMouseCursorOnStartupScreens", "false")
    _save_tree(tree, bigbox_path)

    # --- Settings.xml ---
    tree = ET.parse(settings_path)
    root = tree.getroot()
    settings = root.find("Settings")
    if settings is None:
        raise RuntimeError(f"Settings node not found in {settings_path}")
    if disable_splash_screens:
        _set_text(settings, "ShowLaunchBoxSplashScreen", "false")
        _set_text(settings, "UseStartupScreen", "false")
        _set_text(settings, "HideMouseCursorOnStartupScreens", "false")
    _save_tree(tree, settings_path)
