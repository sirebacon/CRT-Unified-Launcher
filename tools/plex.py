import win32gui
import win32con
import subprocess
import time
import sys
import os
import ctypes
import configparser

# --- DPI AWARENESS ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# --- YOUR CALIBRATED COORDINATES ---
TARGET_X, TARGET_Y = -1883, 139
TARGET_W, TARGET_H = 1720, 1168

# --- PRIMARY MONITOR SETTINGS (Where it goes on Ctrl+C) ---
PRIMARY_X, PRIMARY_Y = 100, 100
PRIMARY_W, PRIMARY_H = 1280, 720

# --- PLEX PATHS ---
PLEX_PATH = r"C:\Program Files\Plex\Plex\Plex.exe" 
PLEX_DIR = r"C:\Program Files\Plex\Plex"
INI_PATH = os.path.expandvars(r'%LOCALAPPDATA%\Plex\Plex.ini')

def force_plex_config():
    """Syncs the Plex.ini with your perfect coordinates before launch."""
    if os.path.exists(INI_PATH):
        config = configparser.ConfigParser()
        try:
            config.read(INI_PATH)
            if not config.has_section('General'): config.add_section('General')
            config.set('General', 'WindowX', str(TARGET_X))
            config.set('General', 'WindowY', str(TARGET_Y))
            config.set('General', 'WindowWidth', str(TARGET_W))
            config.set('General', 'WindowHeight', str(TARGET_H))
            config.set('General', 'Fullscreen', 'false')
            with open(INI_PATH, 'w') as f: config.write(f)
        except Exception as e: print(f"INI Sync Failed: {e}")

def get_plex_hwnd():
    hwnd = win32gui.FindWindow("Qt642QWindowIcon", None)
    return hwnd if hwnd != 0 else win32gui.FindWindow(None, "Plex")

def apply_position(hwnd, x, y, w, h, borderless=True):
    """Handles both the border stripping and the physical move."""
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    
    if borderless:
        # Remove Title Bar and Resizing Frame
        style &= ~win32con.WS_CAPTION
        style &= ~win32con.WS_THICKFRAME
    else:
        # Restore Title Bar and Resizing Frame
        style |= win32con.WS_CAPTION | win32con.WS_THICKFRAME
        
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, 
                         win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED)

def main():
    force_plex_config()
    
    if not get_plex_hwnd():
        if os.path.exists(PLEX_PATH):
            subprocess.Popen(PLEX_PATH, cwd=PLEX_DIR)
            for _ in range(20):
                time.sleep(0.5)
                if get_plex_hwnd(): break

    print(f"Locker ACTIVE: Holding Plex at CRT {TARGET_X}, {TARGET_Y}")
    print(">>> Press CTRL+C to move Plex back to Primary Monitor and exit.")

    try:
        while True:
            hwnd = get_plex_hwnd()
            if hwnd:
                # Get current rect to see if it moved
                rect = win32gui.GetWindowRect(hwnd)
                curr_x, curr_y = rect[0], rect[1]
                
                # Check for drift (ignoring size for better stability)
                if curr_x != TARGET_X or curr_y != TARGET_Y:
                    apply_position(hwnd, TARGET_X, TARGET_Y, TARGET_W, TARGET_H, borderless=True)
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[Ctrl+C Detected] Returning Plex to Primary screen...")
        hwnd = get_plex_hwnd()
        if hwnd:
            # Re-apply borders so it's a normal window again on your main screen
            apply_position(hwnd, PRIMARY_X, PRIMARY_Y, PRIMARY_W, PRIMARY_H, borderless=False)
            # Bring it to focus
            win32gui.SetForegroundWindow(hwnd)
            print("Done! Plex is back home.")
        else:
            print("Could not find Plex window to move it back.")
        sys.exit(0)

if __name__ == "__main__":
    main()