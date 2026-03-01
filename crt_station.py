import os
import subprocess
import sys
import xml.etree.ElementTree as ET

from default_restore import restore_defaults_from_backup
from launchbox_session_mode import apply_crt_session_mode, restore_session_mode
from session.re_state import apply_restore_system_state

LAUNCHBOX_EXE = r"D:\Emulators\LaunchBox\LaunchBox.exe"
LAUNCHBOX_DIR = r"D:\Emulators\LaunchBox"
GENERIC_LAUNCHER = "launch_generic.py"
SESSION_LAUNCHER = "launch_session.py"
RETROARCH_SESSION_PROFILE = os.path.join("profiles", "retroarch-session.json")
GAMING_MANIFEST = os.path.join("profiles", "gaming-manifest.json")
RE_STACK_LAUNCHER = "launch_resident_evil_stack.py"
CRT_TOOLS_LAUNCHER = "crt_tools.py"
LAUNCHBOX_EMULATORS_XML = r"D:\Emulators\LaunchBox\Data\Emulators.xml"


def stop_plex_lockers() -> None:
    cmd = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'launch_plex\\.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _is_quit(choice: str) -> bool:
    return choice.strip().lower() in {"q", "quit", "x", "exit"}


def _is_back(choice: str) -> bool:
    return choice.strip().lower() in {"b", "back"}


def force_restore_plex() -> None:
    subprocess.run(
        [sys.executable, "launch_plex.py", "--restore-only"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_retroarch_mode() -> None:
    if not os.path.exists(GENERIC_LAUNCHER):
        print(f"Session launcher not found: {GENERIC_LAUNCHER}")
        input("Press Enter to return to menu...")
        return
    if not os.path.exists(RETROARCH_SESSION_PROFILE):
        print(f"RetroArch session profile not found: {RETROARCH_SESSION_PROFILE}")
        input("Press Enter to return to menu...")
        return

    try:
        subprocess.run(
            [
                sys.executable,
                GENERIC_LAUNCHER,
                "--profile-file",
                RETROARCH_SESSION_PROFILE,
            ]
        )
    except KeyboardInterrupt:
        pass


def run_gaming_session() -> None:
    if not os.path.exists(SESSION_LAUNCHER):
        print(f"Session launcher not found: {SESSION_LAUNCHER}")
        input("Press Enter to return to menu...")
        return
    if not os.path.exists(GAMING_MANIFEST):
        print(f"Gaming manifest not found: {GAMING_MANIFEST}")
        input("Press Enter to return to menu...")
        return

    # Ensure Intel UHD is primary and CRT refresh is correct before the session starts.
    # SudoMaker (Moonlight VDD) is irrelevant for LaunchBox sessions -- only the internal
    # display and CRT are used. Without this, RetroArch may open on SudoMaker instead.
    print("Restoring display for gaming session...")
    subprocess.run(
        [sys.executable, CRT_TOOLS_LAUNCHER, "display", "restore", "--force"],
        check=False,
    )

    try:
        subprocess.run(
            [
                sys.executable,
                SESSION_LAUNCHER,
                "--manifest",
                GAMING_MANIFEST,
                "--debug",
            ]
        )
    except KeyboardInterrupt:
        pass


def run_plex_mode() -> None:
    stop_plex_lockers()

    plex_proc = subprocess.Popen([sys.executable, "launch_plex.py"])
    try:
        plex_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping Plex locker and restoring to main screen...")
    finally:
        if plex_proc.poll() is None:
            plex_proc.terminate()
            try:
                plex_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                plex_proc.kill()
        stop_plex_lockers()
        force_restore_plex()


def run_youtube_mode() -> None:
    try:
        subprocess.run([sys.executable, "launch_youtube.py"])
    except KeyboardInterrupt:
        pass


def run_resident_evil_stack_manual() -> None:
    if not os.path.exists(RE_STACK_LAUNCHER):
        print(f"Resident Evil stack launcher not found: {RE_STACK_LAUNCHER}")
        input("Press Enter to return to menu...")
        return

    print("\nSelect Resident Evil game:")
    print(" 1. RE1 (GOG)")
    print(" 2. RE2 (GOG)")
    print(" 3. RE3 (GOG)")
    sel = input("Choice (1-3): ").strip()
    mapping = {"1": "re1", "2": "re2", "3": "re3"}
    game = mapping.get(sel)
    if not game:
        print("Invalid selection.")
        input("Press Enter to return to menu...")
        return

    cmd = [sys.executable, RE_STACK_LAUNCHER, "manual", "--game", game]

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


def restore_display_state() -> None:
    if os.path.exists(CRT_TOOLS_LAUNCHER):
        print("\nRestoring display state using crt_tools...")
        subprocess.run([sys.executable, CRT_TOOLS_LAUNCHER, "display", "restore", "--force"])
        print("\nRestoring audio output using crt_tools...")
        subprocess.run([sys.executable, CRT_TOOLS_LAUNCHER, "audio", "restore", "--force"])
        print("\nDisplay/audio restore commands completed. Verify Windows display settings if needed.")
    else:
        print("\nRestoring primary display to Intel UHD and CRT refresh to 60 Hz...")
        ok = apply_restore_system_state()
        if ok:
            print("Display and audio restored.")
        else:
            print("WARNING: Primary display restore may not have completed; check display settings.")
    input("\nPress Enter to return to menu...")


def restore_resident_evil_stack() -> None:
    if not os.path.exists(RE_STACK_LAUNCHER):
        print(f"Resident Evil stack launcher not found: {RE_STACK_LAUNCHER}")
        input("Press Enter to return to menu...")
        return

    subprocess.run([sys.executable, RE_STACK_LAUNCHER, "restore"])
    input("\nPress Enter to return to menu...")


def show_launchbox_retroarch_status() -> None:
    print("\nChecking LaunchBox RetroArch emulator path...")
    if not os.path.exists(LAUNCHBOX_EMULATORS_XML):
        print(f"LaunchBox Emulators.xml not found: {LAUNCHBOX_EMULATORS_XML}")
        input("\nPress Enter to return...")
        return

    try:
        tree = ET.parse(LAUNCHBOX_EMULATORS_XML)
        root = tree.getroot()
    except Exception as e:
        print(f"Failed to read LaunchBox Emulators.xml: {e}")
        input("\nPress Enter to return...")
        return

    retro = None
    for emulator in root.findall("Emulator"):
        title = (emulator.findtext("Title") or "").strip().lower()
        if title == "retroarch":
            retro = emulator
            break

    if retro is None:
        print("RetroArch emulator entry not found in LaunchBox Emulators.xml.")
        input("\nPress Enter to return...")
        return

    app_path = (retro.findtext("ApplicationPath") or "").strip()
    command_line = (retro.findtext("CommandLine") or "").strip()
    is_wrapper = "launchbox_retroarch_wrapper" in app_path.lower()

    print(f"ApplicationPath: {app_path or '(empty)'}")
    print(f"CommandLine: {command_line or '(empty)'}")
    if is_wrapper:
        print("\nStatus: WRAPPER ACTIVE (LaunchBox RetroArch launches through CRT wrapper).")
        print("This will move/lock RetroArch to the CRT even if CRT Station is not running.")
    else:
        print("\nStatus: NORMAL (LaunchBox RetroArch is not using the CRT wrapper path).")

    input("\nPress Enter to return...")


def _run_crt_tools(*tool_args: str, pause: bool = True) -> None:
    if not os.path.exists(CRT_TOOLS_LAUNCHER):
        print(f"CRT tools launcher not found: {CRT_TOOLS_LAUNCHER}")
        if pause:
            input("\nPress Enter to return...")
        return

    cmd = [sys.executable, CRT_TOOLS_LAUNCHER, *tool_args]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    if pause:
        input("\nPress Enter to return...")


def crt_tools_menu() -> None:
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("========================================")
        print("              CRT TOOLS")
        print("========================================")
        print(" 1. Display Dump")
        print(" 2. Config Dump")
        print(" 3. Config Check")
        print(" 4. Prereqs Check")
        print(" 5. Window List (Moonlight)")
        print(" 6. Audio Status")
        print(" 7. Session Log (last 40 lines)")
        print(" 8. Session Processes")
        print(" 9. LaunchBox RetroArch Wrapper Status")
        print("10. Restore Display & Audio")
        print("11. Back")
        print("    Quick keys: [b] Back, [q] Quit")
        print("========================================")
        try:
            choice = input("\nSelect an option (1-11): ").strip()
            if _is_quit(choice):
                raise SystemExit(0)
            if _is_back(choice) or choice == '11':
                return
            if choice == '1':
                _run_crt_tools("display", "dump")
            elif choice == '2':
                _run_crt_tools("config", "dump")
            elif choice == '3':
                _run_crt_tools("config", "check")
            elif choice == '4':
                _run_crt_tools("prereqs")
            elif choice == '5':
                _run_crt_tools("window", "list", "--filter", "moonlight")
            elif choice == '6':
                _run_crt_tools("audio", "status")
            elif choice == '7':
                _run_crt_tools("session", "log", "--lines", "40")
            elif choice == '8':
                _run_crt_tools("session", "processes")
            elif choice == '9':
                show_launchbox_retroarch_status()
            elif choice == '10':
                restore_display_state()
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to main menu...")
            return


def main():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("========================================")
        print("           CRT STATION")
        print("========================================")
        print(" 1. [GAMING] Launch RetroArch")
        print(" 2. [GAMING] Launch LaunchBox (Session)")
        print(" 3. [CINEMA] Launch Plex")
        print(" 4. [CINEMA] Launch YouTube")
        print(" 5. [GAMING] Launch Resident Evil (Manual Mode)")
        print(" 6. [TOOLS]  CRT Tools")
        print(" 7. [TOOLS]  Restore Default Settings")
        print(" 8. [TOOLS]  Recover Resident Evil Stack")
        print(" 9. [EXIT]   Close Menu")
        print("    Quick keys: [q] Quit")
        print("========================================")

        try:
            choice = input("\nSelect an option (1-9): ").strip()
            if _is_quit(choice) or choice == '9':
                break
            if choice == '1':
                run_retroarch_mode()
            elif choice == '2':
                run_gaming_session()
                input("\nPress Enter to return to menu...")
            elif choice == '3':
                run_plex_mode()
            elif choice == '4':
                run_youtube_mode()
            elif choice == '5':
                run_resident_evil_stack_manual()
            elif choice == '6':
                crt_tools_menu()
            elif choice == '7':
                ok, msg, restored = restore_defaults_from_backup()
                print(msg)
                if restored:
                    print("\nRestored files:")
                    for item in restored:
                        print(f" - {item}")
                if ok:
                    print("\nRestoring display and audio to default state...")
                    subprocess.run(
                        [sys.executable, CRT_TOOLS_LAUNCHER, "display", "restore", "--force"],
                        check=False,
                    )
                    subprocess.run(
                        [sys.executable, CRT_TOOLS_LAUNCHER, "audio", "restore", "--force"],
                        check=False,
                    )
                input("\nPress Enter to return to menu...")
            elif choice == '8':
                restore_resident_evil_stack()
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to menu...")
            stop_plex_lockers()
            force_restore_plex()


if __name__ == "__main__":
    main()
