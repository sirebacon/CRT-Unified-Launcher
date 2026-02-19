import win32gui
import win32con
import subprocess
import time
import sys
import os

# --- PATH & TARGET CONFIGURATION ---
RA_PATH = r"D:\RetroArch-Win64\retroarch.exe"
RA_DIR = r"D:\RetroArch-Win64"

# --- CRT SETTINGS ---
CRT_X, CRT_Y = -1211, 43
CRT_W, CRT_H = 1057, 833

# --- PRIMARY MONITOR SETTINGS ---
PRIMARY_X, PRIMARY_Y = 100, 100
PRIMARY_W, PRIMARY_H = 1280, 720

def find_retroarch_hwnd():
    """Finds RetroArch by its internal Windows Class Name (RetroArch)."""
    hwnd = win32gui.FindWindow("RetroArch", None)
    return hwnd if hwnd != 0 else None

def move_window(hwnd, x, y, w, h):
    """Forcefully moves a window even if it's being stubborn."""
    if hwnd:
        # SWP_SHOWWINDOW ensures it's visible while moving
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)

def main():
    # 1. Launch if not open
    hwnd = find_retroarch_hwnd()
    if not hwnd:
        if os.path.exists(RA_PATH):
            print("Launching RetroArch...")
            subprocess.Popen(RA_PATH, cwd=RA_DIR)
            # Wait for it to actually create a window
            for _ in range(20):
                time.sleep(0.5)
                hwnd = find_retroarch_hwnd()
                if hwnd: break
        else:
            print(f"Error: {RA_PATH} not found.")
            return

    if not hwnd:
        print("Could not find RetroArch window.")
        return

    print(f"Locker ACTIVE. Snapping to CRT...")
    
    try:
        while True:
            # Re-check the handle in case the window was recreated (rare but happens)
            hwnd = find_retroarch_hwnd()
            if hwnd:
                # Get current rect
                rect = win32gui.GetWindowRect(hwnd)
                curr_x, curr_y = rect[0], rect[1]
                curr_w, curr_h = rect[2] - rect[0], rect[3] - rect[1]

                # If size/pos is off, force it back
                if (curr_x != CRT_X or curr_y != CRT_Y or 
                    curr_w != CRT_W or curr_h != CRT_H):
                    move_window(hwnd, CRT_X, CRT_Y, CRT_W, CRT_H)
            
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[Ctrl+C] Returning to Primary Monitor...")
        hwnd = find_retroarch_hwnd()
        if hwnd:
            # Force the move back to primary
            move_window(hwnd, PRIMARY_X, PRIMARY_Y, PRIMARY_W, PRIMARY_H)
            # Bring it to front so you can see it
            win32gui.SetForegroundWindow(hwnd)
            print("Done!")
        sys.exit(0)

if __name__ == "__main__":
    main()