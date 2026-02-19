import win32gui
import win32con
import subprocess
import time
import sys
import os
import ctypes
import configparser

# --- DPI AWARENESS ---
try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception: pass

# --- SHARED SETTINGS ---
PRIMARY_MONITOR = {"x": 100, "y": 100, "w": 1280, "h": 720}

# --- APP PROFILES ---
APPS = {
    "1": {
        "name": "RetroArch",
        "path": r"D:\RetroArch-Win64\retroarch.exe",
        "dir": r"D:\RetroArch-Win64",
        "class": "RetroArch",
        "title": "RetroArch",
        # Updated to your latest confirmed calibration
        "crt": {"x": -1333, "y": 64, "w": 1310, "h": 813},
        "use_ini": False
    },
    "2": {
        "name": "Plex",
        "path": r"C:\Program Files\Plex\Plex\Plex.exe",
        "dir": r"C:\Program Files\Plex\Plex",
        "class": "Qt642QWindowIcon",
        "title": "Plex",
        # Updated to your latest confirmed calibration
        "crt": {"x": -1883, "y": 139, "w": 1720, "h": 1168},
        "use_ini": True,
        "ini_path": os.path.expandvars(r'%LOCALAPPDATA%\Plex\Plex.ini')
    }
}

def sync_plex_ini(config):
    if os.path.exists(config["ini_path"]):
        cfg = configparser.ConfigParser()
        try:
            cfg.read(config["ini_path"])
            if not cfg.has_section('General'): cfg.add_section('General')
            cfg.set('General', 'WindowX', str(config["crt"]["x"]))
            cfg.set('General', 'WindowY', str(config["crt"]["y"]))
            cfg.set('General', 'WindowWidth', str(config["crt"]["w"]))
            cfg.set('General', 'WindowHeight', str(config["crt"]["h"]))
            cfg.set('General', 'Fullscreen', 'false')
            with open(config["ini_path"], 'w') as f: cfg.write(f)
        except Exception as e: print(f"INI Sync Error: {e}")

def get_hwnd(config):
    hwnd = win32gui.FindWindow(config["class"], None)
    if not hwnd:
        hwnd = win32gui.FindWindow(None, config["title"])
    return hwnd if hwnd != 0 else None

def apply_pos(hwnd, x, y, w, h, borderless=True):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    if borderless:
        # Strip borders to allow negative positioning and prevent drift
        style &= ~win32con.WS_CAPTION
        style &= ~win32con.WS_THICKFRAME
    else:
        # Restore borders for the primary monitor
        style |= win32con.WS_CAPTION | win32con.WS_THICKFRAME
    
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h, 
                         win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED)

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("===============================")
    print("   CRT MASTER UNIFIED MENU")
    print("===============================")
    print("1. Launch RetroArch (Gaming)")
    print("2. Launch Plex (Cinema)")
    print("Q. Quit")
    
    choice = input("\nSelect Mode: ").lower()
    if choice == 'q': return
    if choice not in APPS: return

    app = APPS[choice]
    if app["use_ini"]: sync_plex_ini(app)

    # Launch if not running
    if not get_hwnd(app):
        print(f"Starting {app['name']}...")
        subprocess.Popen(app["path"], cwd=app["dir"])
        for _ in range(20):
            time.sleep(0.5)
            if get_hwnd(app): break

    print(f"\nLOCKER ACTIVE for {app['name']}")
    print(">>> Press CTRL+C to move back to Primary and exit.")

    try:
        while True:
            hwnd = get_hwnd(app)
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                curr_x, curr_y = rect[0], rect[1]
                curr_w, curr_h = rect[2] - rect[0], rect[3] - rect[1]

                # If it drifts or the core changes resolution, snap it back
                if (curr_x != app["crt"]["x"] or curr_y != app["crt"]["y"] or
                    curr_w != app["crt"]["w"] or curr_h != app["crt"]["h"]):
                    apply_pos(hwnd, app["crt"]["x"], app["crt"]["y"], 
                              app["crt"]["w"], app["crt"]["h"], borderless=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\nReturning {app['name']} to Primary...")
        hwnd = get_hwnd(app)
        if hwnd:
            apply_pos(hwnd, PRIMARY_MONITOR["x"], PRIMARY_MONITOR["y"], 
                      PRIMARY_MONITOR["w"], PRIMARY_MONITOR["h"], borderless=False)
            win32gui.SetForegroundWindow(hwnd)
        sys.exit(0)

if __name__ == "__main__":
    main()