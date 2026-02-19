import datetime as dt
import os
import shutil
import sys
import xml.etree.ElementTree as ET


LAUNCHBOX_EMULATORS = r"D:\LaunchBox\Data\Emulators.xml"
RETRO_TITLE = "retroarch"
RELATIVE_WRAPPER = r"..\CRT Unified Launcher\integrations\launchbox\wrapper\launchbox_retroarch_wrapper.bat"


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
    for emulator in root.findall("Emulator"):
        title = (emulator.findtext("Title") or "").strip().lower()
        if title != RETRO_TITLE:
            continue
        retro_id = (emulator.findtext("ID") or "").strip()

        app_path = emulator.find("ApplicationPath")
        if app_path is None:
            app_path = ET.SubElement(emulator, "ApplicationPath")
        if app_path.text != RELATIVE_WRAPPER:
            app_path.text = RELATIVE_WRAPPER
            changed = True
        break

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

    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


def main() -> int:
    if not os.path.exists(LAUNCHBOX_EMULATORS):
        print(f"LaunchBox Emulators.xml not found: {LAUNCHBOX_EMULATORS}")
        return 1

    backup = backup_file(LAUNCHBOX_EMULATORS)
    changed = patch_emulators(LAUNCHBOX_EMULATORS)

    print(f"Backup: {backup}")
    if changed:
        print("Patched RetroArch emulator to use wrapper.")
    else:
        print("No changes needed; wrapper already configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
