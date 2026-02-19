import datetime as dt
import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET
import re


LAUNCHBOX_EMULATORS = r"D:\Emulators\LaunchBox\Data\Emulators.xml"
RETRO_TITLE = "retroarch"
PPSSPP_TITLE = "ppsspp"
DOLPHIN_TITLE = "dolphin"
PCSX2_TITLE = "pcsx2"
RELATIVE_WRAPPER = r"..\CRT-Unified-Launcher\integrations\launchbox\wrapper\launchbox_retroarch_wrapper.bat"
RELATIVE_PPSSPP_WRAPPER = r"..\CRT-Unified-Launcher\integrations\launchbox\wrapper\launchbox_ppsspp_wrapper.bat"
RELATIVE_DOLPHIN_WRAPPER = r"..\CRT-Unified-Launcher\integrations\launchbox\wrapper\launchbox_dolphin_wrapper.bat"
RELATIVE_PCSX2_WRAPPER = r"..\CRT-Unified-Launcher\integrations\launchbox\wrapper\launchbox_pcsx2_wrapper.bat"
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
WRAPPER_RETRO = os.path.join(PROJECT_ROOT, "integrations", "launchbox", "wrapper", "launchbox_retroarch_wrapper.bat")
WRAPPER_PPSSPP = os.path.join(PROJECT_ROOT, "integrations", "launchbox", "wrapper", "launchbox_ppsspp_wrapper.bat")
WRAPPER_DOLPHIN = os.path.join(PROJECT_ROOT, "integrations", "launchbox", "wrapper", "launchbox_dolphin_wrapper.bat")
WRAPPER_PCSX2 = os.path.join(PROJECT_ROOT, "integrations", "launchbox", "wrapper", "launchbox_pcsx2_wrapper.bat")


def backup_file(path: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(path), f"{os.path.splitext(os.path.basename(path))[0]}.{stamp}.wrapper_install.bak"
    )
    shutil.copy2(path, backup_path)
    return backup_path


def patch_emulators(path: str) -> bool:
    tree = ET.parse(path)
    root = tree.getroot()

    changed = False
    retro_id = None
    ppsspp_id = None
    dolphin_id = None
    pcsx2_id = None
    for emulator in root.findall("Emulator"):
        title = (emulator.findtext("Title") or "").strip().lower()
        if title == RETRO_TITLE:
            retro_id = (emulator.findtext("ID") or "").strip()
            app_path = emulator.find("ApplicationPath")
            if app_path is None:
                app_path = ET.SubElement(emulator, "ApplicationPath")
            if app_path.text != RELATIVE_WRAPPER:
                app_path.text = RELATIVE_WRAPPER
                changed = True
        elif title == PPSSPP_TITLE:
            ppsspp_id = (emulator.findtext("ID") or "").strip()
            app_path = emulator.find("ApplicationPath")
            if app_path is None:
                app_path = ET.SubElement(emulator, "ApplicationPath")
            if app_path.text != RELATIVE_PPSSPP_WRAPPER:
                app_path.text = RELATIVE_PPSSPP_WRAPPER
                changed = True
        elif title == DOLPHIN_TITLE:
            dolphin_id = (emulator.findtext("ID") or "").strip()
            app_path = emulator.find("ApplicationPath")
            if app_path is None:
                app_path = ET.SubElement(emulator, "ApplicationPath")
            if app_path.text != RELATIVE_DOLPHIN_WRAPPER:
                app_path.text = RELATIVE_DOLPHIN_WRAPPER
                changed = True
        elif title == PCSX2_TITLE:
            pcsx2_id = (emulator.findtext("ID") or "").strip()
            app_path = emulator.find("ApplicationPath")
            if app_path is None:
                app_path = ET.SubElement(emulator, "ApplicationPath")
            if app_path.text != RELATIVE_PCSX2_WRAPPER:
                app_path.text = RELATIVE_PCSX2_WRAPPER
                changed = True

    if retro_id:
        for platform in root.findall("EmulatorPlatform"):
            if (platform.findtext("Emulator") or "").strip() != retro_id:
                continue
            cmd = platform.find("CommandLine")
            if cmd is None or cmd.text is None:
                continue
            original = cmd.text
            cmd.text = " ".join(t for t in original.split() if t != "-f")
            if cmd.text != original:
                changed = True

    if ppsspp_id:
        for platform in root.findall("EmulatorPlatform"):
            if (platform.findtext("Emulator") or "").strip() != ppsspp_id:
                continue
            cmd = platform.find("CommandLine")
            if cmd is None or cmd.text is None:
                continue
            original = cmd.text
            cmd.text = " ".join(t for t in original.split() if t.lower() != "--fullscreen")
            if cmd.text != original:
                changed = True

    if dolphin_id:
        for platform in root.findall("EmulatorPlatform"):
            if (platform.findtext("Emulator") or "").strip() != dolphin_id:
                continue
            cmd = platform.find("CommandLine")
            if cmd is None or cmd.text is None:
                continue
            original = cmd.text
            cmd.text = re.sub(
                r"(^|\s)-C\s+Dolphin\.Display\.Fullscreen=True(?=\s|$)",
                r"\1",
                original,
            ).strip()
            if cmd.text != original:
                changed = True

    if pcsx2_id:
        for platform in root.findall("EmulatorPlatform"):
            if (platform.findtext("Emulator") or "").strip() != pcsx2_id:
                continue
            cmd = platform.find("CommandLine")
            if cmd is None or cmd.text is None:
                continue
            original = cmd.text
            cmd.text = re.sub(r"(^|\s)-fullscreen(?=\s|$)", r"\1", original).strip()
            if cmd.text != original:
                changed = True

    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install/verify LaunchBox wrapper integration."
    )
    parser.add_argument(
        "--global",
        dest="global_mode",
        action="store_true",
        help="Patch LaunchBox Emulators.xml globally to always use wrappers.",
    )
    args = parser.parse_args()

    missing = [
        p
        for p in (WRAPPER_RETRO, WRAPPER_PPSSPP, WRAPPER_DOLPHIN, WRAPPER_PCSX2)
        if not os.path.exists(p)
    ]
    if missing:
        print("Missing wrapper file(s):")
        for path in missing:
            print(f" - {path}")
        return 1

    if not args.global_mode:
        print("Session-only-safe mode (default): no global LaunchBox changes made.")
        print("Wrappers detected:")
        print(f" - {WRAPPER_RETRO}")
        print(f" - {WRAPPER_PPSSPP}")
        print(f" - {WRAPPER_DOLPHIN}")
        print(f" - {WRAPPER_PCSX2}")
        print("Use crt_master.py option 2 for temporary session patching.")
        print("Use --global only if you want always-on wrapper patching.")
        return 0

    if not os.path.exists(LAUNCHBOX_EMULATORS):
        print(f"LaunchBox Emulators.xml not found: {LAUNCHBOX_EMULATORS}")
        return 1

    backup = backup_file(LAUNCHBOX_EMULATORS)
    changed = patch_emulators(LAUNCHBOX_EMULATORS)

    print(f"Backup: {backup}")
    if changed:
        print("Patched RetroArch/PPSSPP/Dolphin/PCSX2 emulators to use wrappers.")
    else:
        print("No changes needed; wrapper already configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




