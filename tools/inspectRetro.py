import pygetwindow as gw
import time
import os

def get_ra_stats():
    # Clear terminal for a clean live view
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("=== RetroArch Window Inspector ===")
    print("Press Ctrl+C to stop monitoring.\n")

    try:
        while True:
            windows = gw.getWindowsWithTitle('plex')
            
            if windows:
                ra = windows[0]
                
                # Pulling the raw data
                x, y = ra.topleft
                w, h = ra.width, ra.height
                
                # Displaying the data in a format you can copy-paste back into your scripts
                print(f"Current Status: {'Visible' if ra.visible else 'Hidden/Minimized'}")
                print(f"Position (X, Y): {x}, {y}")
                print(f"Size (W x H):   {w} x {h}")
                print(f"Aspect Ratio:   {round(w/h, 3) if h != 0 else 0}:1")
                print("-" * 30)
                print(f"Config Snippet for your other script:")
                print(f"TARGET_X, TARGET_Y = {x}, {y}")
                print(f"TARGET_W, TARGET_H = {w}, {h}")
                
            else:
                print("Searching for RetroArch window... (Make sure it's open)", end="\r")
            
            time.sleep(1) # Refresh every second
            print("\033[H", end="") # Move cursor to top to overwrite instead of scrolling

    except KeyboardInterrupt:
        print("\nInspector closed.")

if __name__ == "__main__":
    get_ra_stats()