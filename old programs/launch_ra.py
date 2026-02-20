import win32gui
import win32con
import subprocess
import time
import sys
import os
import json

# --- LOAD SHARED CONFIG ---
try:
    with open('crt_config.json') as f:
        cfg = json.load(f)['retroarch']
except Exception as e:
    print(f"Error loading crt_config.json: {e}")
    sys.exit(1)

# Primary monitor landing spot
PRIMARY = {"x": 100, "y": 100, "w": 1280, "h": 720}

def find_retroarch_hwnd():
    """Finds RetroArch by its internal Class Name - works even if title changes."""
    hwnd = win32gui.FindWindow("RetroArch", None)
    return hwnd if hwnd != 0 else None

def move_window(hwnd, x, y, w, h):
    """Forcefully moves the window and ensures it stays on top during the move."""
    if hwnd:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, win32con.SWP_SHOWWINDOW)

def main():
    # 1. Launch if not open
    hwnd = find_retroarch_hwnd()
    if not hwnd:
        if os.path.exists(cfg['path']):
            print("Launching RetroArch...")
            subprocess.Popen(cfg['path'], cwd=cfg['dir'])
            # Wait for window to initialize
            for _ in range(20):
                time.sleep(0.5)
                hwnd = find_retroarch_hwnd()
                if hwnd: break
        else:
            print(f"Error: {cfg['path']} not found.")
            return

    print(f"RetroArch Locker ACTIVE. Snapping to {cfg['x']}, {cfg['y']}...")
    
    try:
        while True:
            hwnd = find_retroarch_hwnd()
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                curr_x, curr_y = rect[0], rect[1]
                curr_w, curr_h = rect[2] - rect[0], rect[3] - rect[1]

                # Check if window drifted or core resized
                if (curr_x != cfg['x'] or curr_y != cfg['y'] or 
                    curr_w != cfg['w'] or curr_h != cfg['h']):
                    move_window(hwnd, cfg['x'], cfg['y'], cfg['w'], cfg['h'])
            
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[Ctrl+C] Returning RetroArch to Primary Monitor...")
        hwnd = find_retroarch_hwnd()
        if hwnd:
            move_window(hwnd, PRIMARY['x'], PRIMARY['y'], PRIMARY['w'], PRIMARY['h'])
            win32gui.SetForegroundWindow(hwnd)
            print("Done!")
        sys.exit(0)

if __name__ == "__main__":
    main()