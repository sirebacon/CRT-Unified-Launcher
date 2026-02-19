import win32gui
import win32con
import subprocess
import time
import sys
import os
import json
import configparser
import ctypes

# FORCE Windows to treat every pixel as 1:1, ignoring scaling (125%, 150%, etc.)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

with open('crt_config.json') as f:
    cfg = json.load(f)['plex']

def get_plex_hwnd():
    hwnd = win32gui.FindWindow("Qt642QWindowIcon", None)
    if not hwnd:
        hwnd = win32gui.FindWindow(None, "Plex")
    return hwnd if hwnd != 0 else None

def main():
    # Start Plex if not running
    if not get_plex_hwnd():
        subprocess.Popen(cfg['path'], cwd=cfg['dir'])
        for _ in range(30):
            time.sleep(0.5)
            if get_plex_hwnd(): break

    print(f"Locker ACTIVE for Plex. Target: {cfg['x']}, {cfg['y']}")
    
    try:
        while True:
            hwnd = get_plex_hwnd()
            if hwnd:
                # 1. Strip Borders
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                if style & win32con.WS_CAPTION:
                    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style & ~win32con.WS_CAPTION)
                
                # 2. Force Move (The 'Focus' trick)
                # We use HWND_TOPMOST briefly to ensure it breaks out of any "snapping"
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, cfg['x'], cfg['y'], cfg['w'], cfg['h'], 
                                     win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED)
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nReturning Plex to primary...")
        hwnd = get_plex_hwnd()
        if hwnd:
            # Restore style
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style | win32con.WS_CAPTION)
            # Standard primary location
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 100, 100, 1280, 720, win32con.SWP_SHOWWINDOW)
        sys.exit(0)

if __name__ == "__main__":
    main()