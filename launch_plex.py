import ctypes
import json
import argparse
import signal
import subprocess
import sys
import time

import win32con
import win32gui

try:
    import keyboard
    _keyboard_available = True
except ImportError:
    _keyboard_available = False

# FORCE Windows to treat every pixel as 1:1, ignoring scaling (125%, 150%, etc.)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

with open('crt_config.json', 'r', encoding='utf-8-sig') as f:
    cfg = json.load(f)['plex']

running = True
_restored = False

# Mutable state shared between the locker loop and the hotkey callback.
_state = {
    'preset_keys': [],   # ordered list of preset keys
    'idx': 0,            # index of the currently active preset
    'presets': {},       # full presets dict
}

# Single-instance guard to avoid two lockers fighting each other.
MUTEX_NAME = "Global\\CRTUnifiedLauncherPlexLocker"
ERROR_ALREADY_EXISTS = 183
_kernel32 = ctypes.windll.kernel32
_mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
if not _mutex:
    print("Failed to create mutex; aborting for safety.")
    sys.exit(1)
if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
    print("Plex locker already running. Exiting duplicate instance.")
    sys.exit(0)


def get_plex_hwnd():
    hwnd = win32gui.FindWindow("Qt642QWindowIcon", None)
    if not hwnd:
        hwnd = win32gui.FindWindow(None, "Plex")
    return hwnd if hwnd != 0 else None


def restore_plex_to_primary():
    global _restored
    if _restored:
        return

    hwnd = get_plex_hwnd()
    if not hwnd:
        _restored = True
        return

    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style | win32con.WS_CAPTION)

        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_NOTOPMOST,
            100,
            100,
            1280,
            720,
            win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED,
        )
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    _restored = True


def _cycle_preset():
    """Hotkey callback — advances to the next preset and prints status."""
    keys = _state['preset_keys']
    if len(keys) < 2:
        return
    _state['idx'] = (_state['idx'] + 1) % len(keys)
    key = keys[_state['idx']]
    rect = _state['presets'][key]
    label = rect.get('label', key)
    print(f"\r  [Plex preset] -> {label}  x={rect['x']} y={rect['y']} w={rect['w']} h={rect['h']}   ")


def _handle_stop(_sig=None, _frame=None):
    global running
    running = False


signal.signal(signal.SIGINT, _handle_stop)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _handle_stop)


def main():
    global running

    hotkey = cfg.get('preset_toggle_hotkey', 'ctrl+alt+p')
    presets = _state['presets']
    keys    = _state['preset_keys']

    if not get_plex_hwnd():
        subprocess.Popen(cfg['path'], cwd=cfg['dir'])
        for _ in range(30):
            time.sleep(0.5)
            if get_plex_hwnd():
                break

    current = presets[keys[_state['idx']]]
    print(f"Locker ACTIVE for Plex [{current.get('label', '')}]  {current['x']},{current['y']}  {current['w']}x{current['h']}")

    if _keyboard_available and len(keys) > 1:
        keyboard.add_hotkey(hotkey, _cycle_preset, suppress=False)
        print(f"  Press {hotkey} to toggle preset ({' / '.join(p.get('label', k) for k, p in presets.items())})")
    elif not _keyboard_available:
        print("  (keyboard library not installed — hotkey unavailable; pip install keyboard)")

    try:
        while running:
            rect = presets[keys[_state['idx']]]
            x, y, w, h = rect['x'], rect['y'], rect['w'], rect['h']

            hwnd = get_plex_hwnd()
            if hwnd:
                try:
                    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                    if style & win32con.WS_CAPTION:
                        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style & ~win32con.WS_CAPTION)

                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_TOP,
                        x, y, w, h,
                        win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED,
                    )
                except Exception:
                    pass
            time.sleep(1)
    except KeyboardInterrupt:
        running = False
    finally:
        print("\nReturning Plex to primary...")
        restore_plex_to_primary()
        if _keyboard_available:
            try:
                keyboard.remove_hotkey(hotkey)
            except Exception:
                pass
        if _mutex:
            _kernel32.ReleaseMutex(_mutex)
            _kernel32.CloseHandle(_mutex)

    sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(description="Plex CRT locker")
    parser.add_argument(
        "--restore-only",
        action="store_true",
        help="Restore Plex to the main display and exit.",
    )
    preset_keys = list(cfg.get("presets", {}).keys())
    parser.add_argument(
        "--preset",
        default=preset_keys[0] if preset_keys else "default",
        choices=preset_keys if preset_keys else None,
        help="Which CRT preset to start with (defined in crt_config.json).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.restore_only:
        restore_plex_to_primary()
        sys.exit(0)

    presets = cfg.get("presets", {})
    keys = list(presets.keys())
    _state['presets'] = presets
    _state['preset_keys'] = keys
    _state['idx'] = keys.index(args.preset) if args.preset in keys else 0

    main()
