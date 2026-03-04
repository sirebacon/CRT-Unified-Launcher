import argparse
import ctypes
import json
import os
import subprocess
import sys
import time

import keyboard  # pip install keyboard
import win32con
import win32gui

# --- DPI AWARENESS ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'crt_config.json')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_preset(preset_key, x, y, w, h):
    config = load_config()
    config['plex']['presets'][preset_key].update({'x': x, 'y': y, 'w': w, 'h': h})
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    print(f"\n  Saved to preset '{preset_key}' in crt_config.json")


def pick_preset(presets: dict) -> str:
    keys = list(presets.keys())
    if len(keys) == 1:
        return keys[0]
    print("\nWhich preset to calibrate?")
    for i, key in enumerate(keys, 1):
        label = presets[key].get('label', key)
        print(f"  {i}. {label}  ({key})")
    sel = input(f"Choice (1-{len(keys)}): ").strip()
    try:
        idx = int(sel) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    except ValueError:
        pass
    print("Invalid, using first preset.")
    return keys[0]


def get_plex_hwnd():
    hwnd = win32gui.FindWindow("Qt642QWindowIcon", None)
    if not hwnd:
        hwnd = win32gui.FindWindow(None, "Plex")
    return hwnd if hwnd != 0 else None


def strip_borders(hwnd):
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~win32con.WS_CAPTION
    style &= ~win32con.WS_THICKFRAME
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                         win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                         win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED)


def main():
    parser = argparse.ArgumentParser(description="Plex CRT live calibration")
    parser.add_argument('--preset', default=None, help="Preset key to calibrate (e.g. 'alt')")
    args = parser.parse_args()

    config = load_config()
    plex_cfg = config['plex']
    presets = plex_cfg.get('presets', {})

    if not presets:
        print("No presets found in crt_config.json under plex.presets")
        sys.exit(1)

    preset_key = args.preset if args.preset in presets else pick_preset(presets)
    rect = presets[preset_key]
    label = rect.get('label', preset_key)

    x, y, w, h = rect['x'], rect['y'], rect['w'], rect['h']

    # Launch Plex if not running
    hwnd = get_plex_hwnd()
    if not hwnd:
        plex_path = plex_cfg['path']
        plex_dir  = plex_cfg['dir']
        if os.path.exists(plex_path):
            print("Launching Plex...")
            subprocess.Popen(plex_path, cwd=plex_dir)
            for _ in range(20):
                time.sleep(0.5)
                if get_plex_hwnd():
                    break

    print(f"\n--- CALIBRATING preset: {label} ({preset_key}) ---")
    print("Arrows: move    W/S: height    A/D: width")
    print("Shift+key: 1px precision    regular: 5px")
    print("P: save to config    Ctrl+C: exit")
    print("---------------------------------------------")

    try:
        while True:
            hwnd = get_plex_hwnd()
            if hwnd:
                strip_borders(hwnd)

                step = 1 if keyboard.is_pressed('shift') else 5

                if keyboard.is_pressed('up'):    y -= step
                if keyboard.is_pressed('down'):  y += step
                if keyboard.is_pressed('left'):  x -= step
                if keyboard.is_pressed('right'): x += step
                if keyboard.is_pressed('w'):     h -= step
                if keyboard.is_pressed('s'):     h += step
                if keyboard.is_pressed('a'):     w -= step
                if keyboard.is_pressed('d'):     w += step

                win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h,
                                      win32con.SWP_SHOWWINDOW)

                print(f"\r  x={x}  y={y}  w={w}  h={h}   ", end="", flush=True)

                if keyboard.is_pressed('p'):
                    save_preset(preset_key, x, y, w, h)
                    time.sleep(0.5)  # debounce

            time.sleep(0.01)

    except KeyboardInterrupt:
        print(f"\n\n--- DONE ---")
        print(f"  x={x}  y={y}  w={w}  h={h}")
        print(f"  (Press P next time to save, or add these manually to crt_config.json)")
        sys.exit(0)


if __name__ == "__main__":
    main()
