import os
import subprocess
import sys

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


def tools_menu() -> None:
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("========================================")
        print("              TOOLS MENU")
        print("========================================")
        print(" 1. Restore Default Settings")
        print(" 2. Recover Resident Evil Stack")
        print(" 3. Restore Display & Audio")
        print(" 4. Back")
        print("========================================")
        try:
            choice = input("\nSelect an option (1-4): ").strip()
            if choice == '1':
                ok, msg, restored = restore_defaults_from_backup()
                print(msg)
                if restored:
                    print("\nRestored files:")
                    for item in restored:
                        print(f" - {item}")
                input("\nPress Enter to return to Tools menu...")
            elif choice == '2':
                restore_resident_evil_stack()
            elif choice == '3':
                restore_display_state()
            elif choice == '4':
                return
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to main menu...")
            return


def main():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("========================================")
        print("        CRT WORKSTATION MANAGER")
        print("========================================")
        print(" 1. [GAMING] Launch RetroArch")
        print(" 2. [GAMING] Launch LaunchBox CRT Watcher")
        print(" 3. [GAMING] Launch LaunchBox (Session)")
        print(" 4. [CINEMA] Launch Plex")
        print(" 5. [GAMING] Launch Resident Evil (Manual Mode)")
        print(" 6. [TOOLS]  Open Tools Menu")
        print(" 7. [EXIT]   Close Menu")
        print("========================================")

        try:
            choice = input("\nSelect an option (1-7): ")
            if choice == '1':
                run_retroarch_mode()
            elif choice == '2':
                ok, msg, backup_dir = apply_crt_session_mode()
                if not ok:
                    print(msg)
                    input("Press Enter to return to menu...")
                    continue

                if os.path.exists(LAUNCHBOX_EXE):
                    subprocess.Popen([LAUNCHBOX_EXE], cwd=LAUNCHBOX_DIR)
                else:
                    print(f"LaunchBox not found at: {LAUNCHBOX_EXE}")
                    if backup_dir:
                        restore_session_mode(backup_dir)
                    input("Press Enter to return to menu...")
                    continue
                try:
                    result = subprocess.run([sys.executable, "launchbox_crt_watcher.py"])
                    if result.returncode != 0:
                        print(f"LaunchBox watcher exited with code {result.returncode}.")
                        input("Press Enter to return to menu...")
                finally:
                    ok_restore, restore_msg = restore_session_mode(backup_dir)
                    if not ok_restore:
                        print(restore_msg)
                        input("Press Enter to continue...")
            elif choice == '3':
                run_gaming_session()
                input("\nPress Enter to return to menu...")
            elif choice == '4':
                run_plex_mode()
            elif choice == '5':
                run_resident_evil_stack_manual()
            elif choice == '6':
                tools_menu()
            elif choice == '7':
                break
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to menu...")
            stop_plex_lockers()
            force_restore_plex()


if __name__ == "__main__":
    main()
