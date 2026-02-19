import ctypes
import json
import argparse
import signal
import subprocess
import sys
import time

import win32con
import win32gui

# FORCE Windows to treat every pixel as 1:1, ignoring scaling (125%, 150%, etc.)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

with open('crt_config.json', 'r', encoding='utf-8-sig') as f:
    cfg = json.load(f)['plex']

running = True
_restored = False

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


def _handle_stop(_sig=None, _frame=None):
    global running
    running = False


signal.signal(signal.SIGINT, _handle_stop)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _handle_stop)


def main():
    global running

    if not get_plex_hwnd():
        subprocess.Popen(cfg['path'], cwd=cfg['dir'])
        for _ in range(30):
            time.sleep(0.5)
            if get_plex_hwnd():
                break

    print(f"Locker ACTIVE for Plex. Target: {cfg['x']}, {cfg['y']}")

    try:
        while running:
            hwnd = get_plex_hwnd()
            if hwnd:
                try:
                    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                    if style & win32con.WS_CAPTION:
                        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style & ~win32con.WS_CAPTION)

                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_TOP,
                        cfg['x'],
                        cfg['y'],
                        cfg['w'],
                        cfg['h'],
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.restore_only:
        restore_plex_to_primary()
        sys.exit(0)
    main()
