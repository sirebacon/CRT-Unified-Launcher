import os
import subprocess
import sys

from default_restore import restore_defaults_from_backup
from launchbox_session_mode import apply_crt_session_mode, restore_session_mode

LAUNCHBOX_EXE = r"D:\Emulators\LaunchBox\LaunchBox.exe"
LAUNCHBOX_DIR = r"D:\Emulators\LaunchBox"
GENERIC_LAUNCHER = "launch_generic.py"
RETROARCH_SESSION_PROFILE = os.path.join("profiles", "retroarch-session.json")
LAUNCHBOX_SESSION_PROFILE = os.path.join("profiles", "launchbox-session.json")


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


def run_launchbox_session_mode() -> None:
    if not os.path.exists(GENERIC_LAUNCHER):
        print(f"Session launcher not found: {GENERIC_LAUNCHER}")
        input("Press Enter to return to menu...")
        return
    if not os.path.exists(LAUNCHBOX_SESSION_PROFILE):
        print(f"LaunchBox session profile not found: {LAUNCHBOX_SESSION_PROFILE}")
        input("Press Enter to return to menu...")
        return

    try:
        subprocess.run(
            [
                sys.executable,
                GENERIC_LAUNCHER,
                "--profile-file",
                LAUNCHBOX_SESSION_PROFILE,
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
        print(" 5. [TOOLS]  Restore Default Settings")
        print(" 6. [EXIT]   Close Menu")
        print("========================================")

        try:
            choice = input("\nSelect an option (1-6): ")
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
                run_launchbox_session_mode()
            elif choice == '4':
                run_plex_mode()
            elif choice == '5':
                ok, msg, restored = restore_defaults_from_backup()
                print(msg)
                if restored:
                    print("\nRestored files:")
                    for item in restored:
                        print(f" - {item}")
                input("\nPress Enter to return to menu...")
            elif choice == '6':
                break
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to menu...")
            stop_plex_lockers()
            force_restore_plex()


if __name__ == "__main__":
    main()
