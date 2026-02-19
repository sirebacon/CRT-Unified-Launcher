import win32gui
import win32con
import subprocess
import time
import sys
import os
import ctypes
import keyboard  # Requires: pip install keyboard

# --- DPI AWARENESS ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# --- STARTING COORDINATES (Your current best guess) ---
TARGET_X, TARGET_Y = -1333, 64
TARGET_W, TARGET_H = 1310, 813

# --- PLEX CONFIGURATION ---
PLEX_PATH = r"C:\Program Files\Plex\Plex\Plex.exe" 
PLEX_DIR = r"C:\Program Files\Plex\Plex"

def get_plex_hwnd():
    hwnd = win32gui.FindWindow("Qt642QWindowIcon", None)
    if not hwnd:
        hwnd = win32gui.FindWindow(None, "Plex")
    return hwnd if hwnd != 0 else None

def strip_window_borders(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~win32con.WS_CAPTION
    style &= ~win32con.WS_THICKFRAME
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 
                         win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                         win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)

def main():
    global TARGET_X, TARGET_Y, TARGET_W, TARGET_H
    
    # 1. Launch Plex
    if not get_plex_hwnd():
        if os.path.exists(PLEX_PATH):
            print("Launching Plex...")
            subprocess.Popen(PLEX_PATH, cwd=PLEX_DIR)
            for _ in range(20):
                time.sleep(0.5)
                if get_plex_hwnd(): break
    
    print("--- LIVE CALIBRATION MODE ACTIVE ---")
    print("ARROWS: Move Window  |  WASD: Resize Window")
    print("SHIFT + Key: 1px precision (slow) | Regular: 5px")
    print("CTRL+C: Stop and show FINAL COORDINATES")
    print("-------------------------------------")

    try:
        while True:
            hwnd = get_plex_hwnd()
            if hwnd:
                strip_window_borders(hwnd)
                
                # Determine movement speed
                step = 1 if keyboard.is_pressed('shift') else 5
                
                # Nudge Position (Arrows)
                if keyboard.is_pressed('up'):    TARGET_Y -= step
                if keyboard.is_pressed('down'):  TARGET_Y += step
                if keyboard.is_pressed('left'):  TARGET_X -= step
                if keyboard.is_pressed('right'): TARGET_X += step
                
                # Nudge Size (WASD)
                if keyboard.is_pressed('w'):     TARGET_H -= step
                if keyboard.is_pressed('s'):     TARGET_H += step
                if keyboard.is_pressed('a'):     TARGET_W -= step
                if keyboard.is_pressed('d'):     TARGET_W += step

                # Apply live update
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, TARGET_X, TARGET_Y, TARGET_W, TARGET_H, win32con.SWP_SHOWWINDOW)
                
                # Print status to terminal (overwriting the same line)
                status = f"X: {TARGET_X} | Y: {TARGET_Y} | W: {TARGET_W} | H: {TARGET_H}      "
                print(f"\r{status}", end="", flush=True)

            time.sleep(0.01) # High refresh for smooth movement

    except KeyboardInterrupt:
        print("\n\n--- CALIBRATION COMPLETE ---")
        print(f"Final X, Y: {TARGET_X}, {TARGET_Y}")
        print(f"Final W, H: {TARGET_W}, {TARGET_H}")
        print("Save these numbers for your master script.")
        sys.exit(0)

if __name__ == "__main__":
    main()