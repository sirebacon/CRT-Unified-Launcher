import os
import subprocess
import sys

from launchbox_session_mode import apply_crt_session_mode, restore_session_mode

LAUNCHBOX_EXE = r"D:\LaunchBox\LaunchBox.exe"
LAUNCHBOX_DIR = r"D:\LaunchBox"

def main():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("========================================")
        print("        CRT WORKSTATION MANAGER")
        print("========================================")
        print(" 1. [GAMING] Launch RetroArch")
        print(" 2. [GAMING] Launch LaunchBox CRT Watcher")
        print(" 3. [CINEMA] Launch Plex")
        print(" 4. [EXIT]   Close Menu")
        print("========================================")
        
        try:
            choice = input("\nSelect an option (1-4): ")
            if choice == '1':
                subprocess.run([sys.executable, "launch_ra.py"])
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
                subprocess.run([sys.executable, "launch_plex.py"])
            elif choice == '4':
                break
        except KeyboardInterrupt:
            print("\nExiting...")
            break

if __name__ == "__main__":
    main()
