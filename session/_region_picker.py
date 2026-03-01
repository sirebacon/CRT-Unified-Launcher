"""Region picker subprocess — called by launch_youtube.py.

Usage: python _region_picker.py <ml> <mt> <mr> <mb> [log_path]

Single-step drag-to-select overlay on the monitor described by the given
bounds. The user drags a cyan rectangle around the video content area.

Prints a JSON result to stdout on success, nothing on cancel.
Exit code 0 = success, 1 = cancel/error.
"""

import json
import logging
import sys


def _setup_log(log_path: str) -> logging.Logger:
    log = logging.getLogger("picker")
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        try:
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)-7s [picker] %(message)s",
                datefmt="%H:%M:%S",
            ))
            log.addHandler(fh)
        except Exception:
            pass  # log path unusable — continue without file logging
    return log


def main() -> int:
    if len(sys.argv) < 5:
        print("[picker] usage: _region_picker.py ml mt mr mb [log_path]", file=sys.stderr)
        return 1

    ml, mt, mr, mb = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    log_path = sys.argv[5] if len(sys.argv) > 5 else None
    log = _setup_log(log_path) if log_path else logging.getLogger("picker")

    log.info("start ml=%d mt=%d mr=%d mb=%d", ml, mt, mr, mb)
    mw, mh = mr - ml, mb - mt

    try:
        import tkinter as tk
    except ImportError:
        print("[picker] tkinter not available", file=sys.stderr)
        return 1

    result = {}

    log.info("creating tkinter window %dx%d at (%d,%d)", mw, mh, ml, mt)
    root = tk.Tk()
    try:
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-alpha", 0.3)
        root.attributes("-topmost", True)
        root.configure(bg="black")
        # +{ml}+{mt} with negative ml is valid Tk virtual-desktop syntax.
        root.geometry(f"{mw}x{mh}+{ml}+{mt}")
        log.info("geometry set to %dx%d+%d+%d", mw, mh, ml, mt)

        # Belt-and-suspenders: also reposition via Win32 in case the geometry
        # string doesn't handle negative virtual-desktop coords on this system.
        try:
            import ctypes
            import win32con
            import win32gui
            root.update()  # ensure HWND exists
            frame_hwnd = root.winfo_id()
            log.info("frame hwnd=0x%x", frame_hwnd)
            _GA_ROOT = 2
            top_hwnd = ctypes.windll.user32.GetAncestor(frame_hwnd, _GA_ROOT)
            log.info("top hwnd=0x%x", top_hwnd)
            if top_hwnd:
                rc = win32gui.SetWindowPos(
                    top_hwnd, win32con.HWND_TOPMOST,
                    ml, mt, mw, mh,
                    win32con.SWP_SHOWWINDOW,
                )
                log.info("SetWindowPos rc=%s", rc)
            else:
                log.warning("GetAncestor returned NULL — relying on geometry string")
        except Exception as e:
            log.warning("Win32 reposition failed: %s — relying on geometry string", e)

        root.deiconify()
        root.update()
        root.lift()
        root.focus_force()
        log.info("window shown and focused")

        canvas = tk.Canvas(root, cursor="crosshair", bg="gray10", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        label = canvas.create_text(
            mw // 2, 24,
            text="Drag around the video content (no black bars)  |  Esc to cancel",
            fill="white", font=("Arial", 11),
        )

        sx = sy = 0
        rect_id = [None]

        def on_press(e):
            nonlocal sx, sy
            sx, sy = e.x, e.y
            if rect_id[0]:
                canvas.delete(rect_id[0])
            rect_id[0] = canvas.create_rectangle(sx, sy, sx, sy, outline="cyan", width=2)

        def on_drag(e):
            if rect_id[0]:
                canvas.coords(rect_id[0], sx, sy, e.x, e.y)

        def on_release(e):
            x1, y1 = min(sx, e.x), min(sy, e.y)
            x2, y2 = max(sx, e.x), max(sy, e.y)
            if x2 - x1 <= 10 or y2 - y1 <= 10:
                return  # too small — let user try again
            result["content"] = [ml + x1, mt + y1, x2 - x1, y2 - y1]
            log.info("content selected: %s", result["content"])
            root.quit()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.bind("<Escape>", lambda e: root.quit())
        canvas.focus_set()

        root.mainloop()

    except Exception as e:
        log.exception("unhandled error: %s", e)
        print(f"[picker] error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if result:
        log.info("result: %s", result)
        print(json.dumps(result))
        return 0
    log.info("cancelled (no result)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
