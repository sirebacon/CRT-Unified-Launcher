import os
import subprocess
import sys

def main():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("========================================")
        print("        CRT WORKSTATION MANAGER")
        print("========================================")
        print(" 1. [GAMING] Launch RetroArch")
        print(" 2. [CINEMA] Launch Plex")
        print(" 3. [EXIT]   Close Menu")
        print("========================================")
        
        try:
            choice = input("\nSelect an option (1-3): ")
            if choice == '1':
                subprocess.run([sys.executable, "launch_ra.py"])
            elif choice == '2':
                subprocess.run([sys.executable, "launch_plex.py"])
            elif choice == '3':
                break
        except KeyboardInterrupt:
            # This catches the Ctrl+C so the Master Script doesn't crash
            print("\nReturning to Menu...")
            continue 

if __name__ == "__main__":
    main()