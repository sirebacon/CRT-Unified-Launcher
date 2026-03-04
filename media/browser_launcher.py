"""Browser launcher adapter for Tier 3 providers.

Mode A (system browser): isolated Chrome via --user-data-dir, placed on CRT,
  key loop for re-anchor and live window adjustment.

Mode B (Playwright): same isolation, plus CSS/JS injection for fullscreen
  containment — video fills the Chrome window instead of going OS fullscreen,
  fixing 4:3 cropping on CRT displays.

Key loop controls (terminal, while browser is open):
  Normal mode:  A=adjust  R=re-anchor  1-9=presets  Q/Esc=close
  Adjust mode:  arrows=move  [/]=width  -/+=height  1-6=step  S=save  Z=undo  A/Esc=done
"""

from __future__ import annotations

import json
import logging
import msvcrt
import os
import shutil
import subprocess
import threading
import time
from typing import Callable, List, Optional, Set

import win32gui
import win32process

from session.window_utils import enum_windows, find_window, get_rect, move_window, pids_for_root

log = logging.getLogger("media.browser_launcher")

_CHROME_CLASS = "Chrome_WidgetWin_1"
_STEPS = [1, 5, 10, 25, 50, 100]

# Default CSS injected in Mode B: makes video/iframe elements use contain
# instead of cover when the browser enters OS fullscreen, preventing cropping.
_DEFAULT_FULLSCREEN_CSS = """
:-webkit-full-screen video,
:fullscreen video {
    object-fit: contain !important;
    background: #000 !important;
}
:-webkit-full-screen iframe,
:fullscreen iframe {
    width: 100% !important;
    height: 100% !important;
}
"""

# JS injected when playwright_fullscreen_js=true: overrides requestFullscreen()
# so the element fills the viewport via CSS instead of triggering OS fullscreen.
# The Chrome window stays under our control and the key loop can still adjust it.
_STEALTH_INIT_SCRIPT = """
(function() {
    // navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

    // window.chrome — must look like a real Chrome instance
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function(){}, sendMessage: function(){}
        };
    }

    // navigator.plugins — Playwright leaves this empty; fill with a dummy entry
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [{
                name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer',
                description: 'Portable Document Format', length: 1
            }];
            Object.defineProperty(arr, 'length', {value: 1});
            return arr;
        }
    });

    // navigator.languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

    // Remove CDP / Playwright global artifacts
    try {
        const drop = Object.getOwnPropertyNames(window).filter(
            k => k.startsWith('cdc_') || k.startsWith('__playwright') || k === '__pwInitScripts'
        );
        drop.forEach(k => { try { delete window[k]; } catch(_) {} });
    } catch(_) {}
})();
"""

_FULLSCREEN_JS_OVERRIDE = """
(function() {
    Element.prototype.requestFullscreen = function() {
        this.style.setProperty('position', 'fixed', 'important');
        this.style.setProperty('inset', '0', 'important');
        this.style.setProperty('width', '100vw', 'important');
        this.style.setProperty('height', '100vh', 'important');
        this.style.setProperty('z-index', '2147483647', 'important');
        this.style.setProperty('object-fit', 'contain', 'important');
        this.style.setProperty('background', '#000', 'important');
        document.dispatchEvent(new Event('fullscreenchange'));
        return Promise.resolve();
    };
    document.exitFullscreen = function() { return Promise.resolve(); };
})();
"""


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------

def _snapshot_chrome_windows() -> Set[int]:
    """Return handles of all currently visible Chrome top-level windows.
    Used to build the protected set — we never touch any window in this set.
    """
    protected: Set[int] = set()
    for hwnd in enum_windows():
        try:
            if not win32gui.IsWindowVisible(hwnd):
                continue
            if win32gui.GetClassName(hwnd) != _CHROME_CLASS:
                continue
            protected.add(hwnd)
        except Exception:
            continue
    return protected


def _poll_for_window(our_pid: int, timeout_sec: float, proc: subprocess.Popen) -> Optional[int]:
    """Poll for a Chrome window owned by our PID (Mode A)."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log.warning("browser process exited before window was found")
            return None
        hwnd = find_window(pid=our_pid, class_contains=[_CHROME_CLASS], title_contains=[])
        if hwnd is not None:
            return hwnd
        time.sleep(0.3)
    return None


def _poll_for_new_window(protected: Set[int], timeout: float) -> Optional[int]:
    """Poll for a Chrome window that wasn't in the protected snapshot (Mode B)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for hwnd in enum_windows():
            try:
                if hwnd in protected:
                    continue
                if not win32gui.IsWindowVisible(hwnd):
                    continue
                if win32gui.GetClassName(hwnd) != _CHROME_CLASS:
                    continue
                if not win32gui.GetWindowText(hwnd):
                    continue
                return hwnd
            except Exception:
                continue
        time.sleep(0.3)
    return None


def _safe_move_window(
    hwnd: int,
    rect: dict,
    protected: Set[int],
    our_pid: Optional[int],
    dry_run: bool,
) -> bool:
    """Safety-checked window move.

    Safeguard 1 — protected set: hwnd must not be a pre-existing window.
    Safeguard 2 — PID verify: skipped when our_pid is None (Mode B, window
      verified via snapshot diff instead).
    """
    if hwnd in protected:
        log.error("Safety abort: hwnd %d is in protected set — skipping", hwnd)
        return False

    actual_pid: Optional[int] = None
    if our_pid is not None:
        allowed_pids = pids_for_root(our_pid)
        _, actual_pid = win32process.GetWindowThreadProcessId(hwnd)
        if actual_pid not in allowed_pids:
            log.error("Safety abort: hwnd %d PID %d not in process tree %d — skipping",
                      hwnd, actual_pid, our_pid)
            return False

    x, y, w, h = rect["x"], rect["y"], rect["w"], rect["h"]

    if dry_run:
        log.info("[dry-run] would move hwnd=%d to x=%d y=%d w=%d h=%d", hwnd, x, y, w, h)
        print(f"[browser] [dry-run] would move hwnd={hwnd} to x={x} y={y} w={w} h={h}")
        return True

    try:
        move_window(hwnd, x, y, w, h)
        log.info("placed hwnd=%d at x=%d y=%d w=%d h=%d", hwnd, x, y, w, h)
        return True
    except Exception as exc:
        log.warning("move_window failed for hwnd=%d: %s", hwnd, exc)
        return False


# ---------------------------------------------------------------------------
# Extension helpers
# ---------------------------------------------------------------------------

def _find_extensions_in_profile(profile_dir: str, ext_ids: list, browser_path: str) -> list:
    """Return local paths for extensions found in the Chrome profile.

    CWS extensions live at <profile_dir>/Default/Extensions/<id>/<version>/.
    If an extension is missing, prints install instructions and skips it.
    """
    found = []
    for ext_id in ext_ids:
        ext_base = os.path.join(profile_dir, "Default", "Extensions", ext_id)
        if not os.path.isdir(ext_base):
            log.warning("Mode B: extension %s not found in profile — install it first", ext_id)
            print(f"[browser] WARNING: extension {ext_id!r} not installed in profile.")
            print(f"[browser]   Run this once to install it:")
            bp = browser_path or "chrome.exe"
            print(f"[browser]   \"{bp}\" --user-data-dir=\"{profile_dir}\" "
                  f"https://chromewebstore.google.com/detail/{ext_id}")
            continue
        try:
            versions = sorted(
                [d for d in os.listdir(ext_base)
                 if os.path.isdir(os.path.join(ext_base, d))],
                reverse=True,
            )
            if versions:
                path = os.path.join(ext_base, versions[0])
                found.append(path)
                log.info("Mode B: extension %s v%s loaded from profile", ext_id, versions[0])
            else:
                log.warning("Mode B: extension %s dir exists but no version subdirs", ext_id)
        except Exception as exc:
            log.warning("Mode B: error resolving extension %s: %s", ext_id, exc)
    return found


# ---------------------------------------------------------------------------
# CRT rect resolution
# ---------------------------------------------------------------------------

def _resolve_browser_rect(cfg: dict, project_root: str) -> dict:
    """Return the browser rect. Priority: config value → auto-detect → default."""
    _default = {"x": 0, "y": 0, "w": 1920, "h": 1080}
    configured = cfg.get("browser_playback", {}).get("browser_rect")
    if configured is not None:
        log.info("browser_rect from config: x=%d y=%d w=%d h=%d",
                 configured["x"], configured["y"], configured["w"], configured["h"])
        return configured
    log.info("browser_rect is null — attempting auto-detect from CRT display token")
    try:
        re_cfg_path = os.path.join(project_root, "re_stack_config.json")
        with open(re_cfg_path, encoding="utf-8") as f:
            re_cfg = json.load(f)
        display_cfg = re_cfg.get("display", {})
        tokens: list = list(display_cfg.get("required_groups", {}).get("crt_display", []))
        crt_token = display_cfg.get("crt_token", "")
        if crt_token and crt_token not in tokens:
            tokens.append(crt_token)
        if tokens:
            from session.display_api import get_crt_display_rect
            result = get_crt_display_rect(tokens)
            if result:
                x, y, w, h = result
                log.info("auto-detected CRT browser_rect: x=%d y=%d w=%d h=%d", x, y, w, h)
                return {"x": x, "y": y, "w": w, "h": h}
            log.warning("get_crt_display_rect returned None for tokens %s", tokens)
        else:
            log.warning("no CRT tokens found in re_stack_config.json display section")
    except Exception as exc:
        log.warning("browser_rect auto-detect failed: %s", exc)
    log.warning("browser_rect not configured and auto-detect failed — using default 0,0,1920,1080")
    print("[browser] WARNING: could not detect CRT display rect; placement may be wrong.")
    print("[browser]   Set browser_playback.browser_rect in crt_config.json to fix this.")
    return _default


# ---------------------------------------------------------------------------
# Preset save
# ---------------------------------------------------------------------------

def _save_browser_preset(profile_id: str, project_root: str, label: str, rect: dict) -> bool:
    """Append or update a named preset in crt_config.json."""
    cfg_path = os.path.join(project_root, "crt_config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        profile = (cfg
                   .setdefault("browser_playback", {})
                   .setdefault("profiles", {})
                   .setdefault(profile_id, {}))
        presets: list = profile.setdefault("window_presets", [])
        for p in presets:
            if p.get("label") == label:
                p.update(rect)
                break
        else:
            presets.append({"label": label, **rect})
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        log.info("saved browser preset %r: %s", label, rect)
        return True
    except Exception as exc:
        log.error("failed to save browser preset: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Session key loop (shared by Mode A and Mode B)
# ---------------------------------------------------------------------------

def _build_preset_list(default_rect: dict, profile_cfg: dict) -> List[dict]:
    presets = [{"label": "CRT (auto)", **default_rect}]
    for p in profile_cfg.get("window_presets", []):
        presets.append({
            "label": p.get("label", f"Preset {len(presets) + 1}"),
            "x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"],
        })
    return presets


def _print_key_help(presets: List[dict], mode_label: str = "") -> None:
    tag = f" [{mode_label}]" if mode_label else ""
    print()
    print(f"[browser]{tag} ── Session controls ──────────────────────────────────")
    print(f"[browser]   A        Enter adjust mode (move/resize window)")
    print(f"[browser]   R        Re-anchor to active preset")
    print(f"[browser]   Q / Esc  Close browser and end session")
    for i, p in enumerate(presets):
        print(f"[browser]   {i + 1}        {p['label']}  "
              f"(x={p['x']} y={p['y']} w={p['w']} h={p['h']})")
    print(f"[browser] ────────────────────────────────────────────────────")
    print()


def _print_adjust_help() -> None:
    print()
    print("[browser] ── Adjust mode ────────────────────────────────────────")
    print("[browser]   Arrows   Move window (x / y)")
    print("[browser]   [ / ]    Decrease / increase width")
    print("[browser]   - / +    Decrease / increase height")
    print("[browser]   1-6      Step size: 1  5  10  25  50  100")
    print("[browser]   S        Save current rect as a named preset")
    print("[browser]   Z        Undo last change")
    print("[browser]   A / Esc  Exit adjust mode")
    print("[browser] ────────────────────────────────────────────────────")
    print()


def _print_adjust_status(x: int, y: int, w: int, h: int, step: int) -> None:
    print(f"\r[browser] ADJUST  x={x:+d}  y={y:+d}  w={w}  h={h}  step={step}    ",
          end="", flush=True)


def _run_key_loop(
    hwnd: Optional[int],
    presets: List[dict],
    protected: Set[int],
    our_pid: Optional[int],
    stop_event: threading.Event,
    close_fn: Callable,
    profile_id: str,
    project_root: str,
    mode_label: str = "",
) -> None:
    """Key loop on main thread while the browser runs.

    our_pid: PID of the launched process (Mode A). None for Mode B (PID check skipped).
    close_fn: callable that closes the browser (proc.terminate for A, ctx.close for B).
    """
    active_preset = presets[0]
    adjust_mode = False
    step_idx = 2        # default step = 10
    prev_rect: Optional[dict] = None

    _print_key_help(presets, mode_label)

    while not stop_event.wait(timeout=0.05):
        if not msvcrt.kbhit():
            continue
        ch = msvcrt.getch()

        # ── Adjust mode ────────────────────────────────────────────────────
        if adjust_mode:
            if ch == b"\xe0":
                ch2 = msvcrt.getch()
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    step = _STEPS[step_idx]
                    prev_rect = {"x": x, "y": y, "w": w, "h": h}
                    if   ch2 == b"H": y -= step
                    elif ch2 == b"P": y += step
                    elif ch2 == b"K": x -= step
                    elif ch2 == b"M": x += step
                    else: continue
                    _safe_move_window(hwnd, {"x": x, "y": y, "w": w, "h": h},
                                      protected, our_pid, dry_run=False)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch == b"[":
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    prev_rect = {"x": x, "y": y, "w": w, "h": h}
                    w = max(1, w - _STEPS[step_idx])
                    _safe_move_window(hwnd, {"x": x, "y": y, "w": w, "h": h},
                                      protected, our_pid, dry_run=False)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch == b"]":
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    prev_rect = {"x": x, "y": y, "w": w, "h": h}
                    w += _STEPS[step_idx]
                    _safe_move_window(hwnd, {"x": x, "y": y, "w": w, "h": h},
                                      protected, our_pid, dry_run=False)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch == b"-":
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    prev_rect = {"x": x, "y": y, "w": w, "h": h}
                    h = max(1, h - _STEPS[step_idx])
                    _safe_move_window(hwnd, {"x": x, "y": y, "w": w, "h": h},
                                      protected, our_pid, dry_run=False)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch in (b"=", b"+"):
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    prev_rect = {"x": x, "y": y, "w": w, "h": h}
                    h += _STEPS[step_idx]
                    _safe_move_window(hwnd, {"x": x, "y": y, "w": w, "h": h},
                                      protected, our_pid, dry_run=False)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch in (b"1", b"2", b"3", b"4", b"5", b"6"):
                step_idx = int(ch) - 1
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch in (b"z", b"Z"):
                if prev_rect and hwnd and win32gui.IsWindow(hwnd):
                    _safe_move_window(hwnd, prev_rect, protected, our_pid, dry_run=False)
                    x, y, w, h = prev_rect["x"], prev_rect["y"], prev_rect["w"], prev_rect["h"]
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])
                    log.info("adjust undo: reverted to x=%d y=%d w=%d h=%d", x, y, w, h)

            elif ch in (b"s", b"S"):
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    print(f"\n[browser] Preset label (Enter = 'Adjusted'): ", end="", flush=True)
                    try:
                        label = input().strip() or "Adjusted"
                    except (EOFError, KeyboardInterrupt):
                        label = "Adjusted"
                    rect = {"x": x, "y": y, "w": w, "h": h}
                    if _save_browser_preset(profile_id, project_root, label, rect):
                        print(f"[browser] Saved '{label}': x={x} y={y} w={w} h={h}")
                        active_preset = {"label": label, **rect}
                    else:
                        print("[browser] ERROR: could not save preset.")
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch in (b"a", b"A", b"\x1b"):
                adjust_mode = False
                print()
                log.info("exiting adjust mode")
                _print_key_help(presets, mode_label)

        # ── Normal mode ────────────────────────────────────────────────────
        else:
            if ch in (b"a", b"A"):
                adjust_mode = True
                log.info("entering adjust mode")
                _print_adjust_help()
                if hwnd and win32gui.IsWindow(hwnd):
                    x, y, w, h = get_rect(hwnd)
                    _print_adjust_status(x, y, w, h, _STEPS[step_idx])

            elif ch in (b"r", b"R"):
                if hwnd and win32gui.IsWindow(hwnd):
                    _safe_move_window(hwnd, active_preset, protected, our_pid, dry_run=False)
                    log.info("re-anchored to %r", active_preset["label"])
                    print(f"[browser] Re-anchored: {active_preset['label']}  "
                          f"x={active_preset['x']} y={active_preset['y']} "
                          f"w={active_preset['w']} h={active_preset['h']}")
                else:
                    print("[browser] Window no longer available.")

            elif ch in (b"q", b"Q", b"\x1b"):
                print("[browser] Closing browser session...")
                log.info("user requested browser close")
                close_fn()
                break

            elif ch in (b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"):
                idx = int(ch.decode()) - 1
                if idx < len(presets):
                    active_preset = presets[idx]
                    if hwnd and win32gui.IsWindow(hwnd):
                        _safe_move_window(hwnd, active_preset, protected, our_pid, dry_run=False)
                        log.info("applied preset %d: %r", idx + 1, active_preset["label"])
                        print(f"[browser] Preset {idx + 1}: {active_preset['label']}  "
                              f"x={active_preset['x']} y={active_preset['y']} "
                              f"w={active_preset['w']} h={active_preset['h']}")
                    else:
                        print("[browser] Window no longer available.")
                else:
                    print(f"[browser] No preset {idx + 1} configured.")


# ---------------------------------------------------------------------------
# Mode A — isolated system browser
# ---------------------------------------------------------------------------

def launch_system_browser(
    url: str,
    cfg: dict,
    profile_id: str = "",
    dry_run: bool = False,
) -> int:
    """Launch url in an isolated Chrome instance, place on CRT, block until closed."""
    bp_cfg: dict = cfg.get("browser_playback", {})
    browser_path: str = bp_cfg.get("browser_path", "").strip()
    isolated_profile_base: str = bp_cfg.get("isolated_profile_dir", "runtime/browser_isolated")
    isolated_profile_mode: str = bp_cfg.get("isolated_profile_mode", "persistent")
    window_find_timeout: float = float(bp_cfg.get("window_find_timeout_sec", 15))
    profiles: dict = bp_cfg.get("profiles", {})
    profile_cfg: dict = profiles.get(profile_id, {})
    browser_args: list = list(profile_cfg.get("browser_args", []))

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    browser_rect = _resolve_browser_rect(cfg, project_root)

    if not browser_path:
        log.error("browser_path not configured")
        print("[browser] ERROR: browser_playback.browser_path must be set in crt_config.json.")
        return 1
    if not os.path.isfile(browser_path):
        log.error("browser_path not found: %s", browser_path)
        print(f"[browser] ERROR: browser not found at {browser_path!r}")
        return 1

    if not os.path.isabs(isolated_profile_base):
        isolated_profile_base = os.path.join(project_root, isolated_profile_base)
    isolated_profile_dir = os.path.join(isolated_profile_base, profile_id or "default")

    if isolated_profile_mode == "ephemeral" and os.path.exists(isolated_profile_dir):
        try:
            shutil.rmtree(isolated_profile_dir)
        except Exception as exc:
            log.warning("could not wipe stale profile dir: %s", exc)

    try:
        os.makedirs(isolated_profile_dir, exist_ok=True)
    except Exception as exc:
        log.error("failed to create profile dir: %s", exc)
        print(f"[browser] ERROR: could not create profile dir: {exc}")
        return 1

    protected_hwnds = _snapshot_chrome_windows()
    log.info("Mode A: protected set %d window(s)", len(protected_hwnds))

    # Resolve local (unpacked) extensions — these work with --load-extension
    # unlike CWS extensions. Paths are relative to project root.
    local_ext_dirs: list = profile_cfg.get("local_extensions", [])
    local_ext_paths = []
    for d in local_ext_dirs:
        if not os.path.isabs(d):
            d = os.path.join(project_root, d)
        if os.path.isdir(d):
            local_ext_paths.append(d)
            log.info("Mode A: local extension: %s", d)
        else:
            log.warning("Mode A: local extension dir not found: %s", d)

    x, y, w, h = browser_rect["x"], browser_rect["y"], browser_rect["w"], browser_rect["h"]
    cmd = [
        browser_path,
        f"--user-data-dir={isolated_profile_dir}",
        "--new-window",
        "--no-restore-last-session",
        "--disable-session-crashed-bubble",
        f"--window-position={x},{y}",
        f"--window-size={w},{h}",
    ] + browser_args
    if local_ext_paths:
        cmd.append(f"--load-extension={','.join(local_ext_paths)}")
    cmd.append(url)

    if dry_run:
        print(f"[browser] [dry-run] Mode A")
        print(f"[browser] [dry-run] cmd: {' '.join(cmd)}")
        print(f"[browser] [dry-run] isolated profile: {isolated_profile_dir}")
        print(f"[browser] [dry-run] protected hwnds: {len(protected_hwnds)}")
        print(f"[browser] [dry-run] target rect: x={x} y={y} w={w} h={h}")
        return 0

    log.info("Mode A: launching (profile=%r)", profile_id or "default")
    proc = subprocess.Popen(cmd)
    our_pid = proc.pid
    log.info("Mode A: browser launched pid=%d", our_pid)
    print(f"[browser] Launched isolated Chrome pid={our_pid}, finding window...")

    presets = _build_preset_list(browser_rect, profile_cfg)

    try:
        hwnd = _poll_for_window(our_pid, window_find_timeout, proc)
        if hwnd is None:
            log.warning("window not found within %.0fs — skipping placement", window_find_timeout)
            print("[browser] Could not find browser window — skipping CRT placement.")
        else:
            log.info("Mode A: found window hwnd=%d", hwnd)
            placed = _safe_move_window(hwnd, browser_rect, protected_hwnds, our_pid, dry_run=False)
            if not placed:
                time.sleep(0.5)
                _safe_move_window(hwnd, browser_rect, protected_hwnds, our_pid, dry_run=False)

        rc_holder = [0]
        stop_event = threading.Event()

        def _wait_thread():
            rc_holder[0] = proc.wait()
            stop_event.set()

        t = threading.Thread(target=_wait_thread, daemon=True)
        t.start()
        _run_key_loop(
            hwnd=hwnd, presets=presets, protected=protected_hwnds,
            our_pid=our_pid, stop_event=stop_event, close_fn=proc.terminate,
            profile_id=profile_id, project_root=project_root, mode_label="Mode A",
        )
        t.join()
        rc = rc_holder[0]
        log.info("Mode A: browser exited rc=%d", rc)
        return rc

    finally:
        if isolated_profile_mode == "ephemeral":
            try:
                shutil.rmtree(isolated_profile_dir, ignore_errors=True)
                log.info("ephemeral: wiped %s", isolated_profile_dir)
            except Exception as exc:
                log.warning("ephemeral cleanup failed: %s", exc)


# ---------------------------------------------------------------------------
# Mode B — Playwright
# ---------------------------------------------------------------------------

def launch_playwright_browser(
    url: str,
    cfg: dict,
    profile_id: str = "",
    dry_run: bool = False,
) -> int:
    """Launch url via Playwright with fullscreen CSS/JS injection for CRT-correct sizing."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("playwright not installed — pip install playwright && playwright install chromium")
        print("[browser] Playwright not installed — falling back to Mode A.")
        print("[browser]   To install: pip install playwright && playwright install chromium")
        return launch_system_browser(url, cfg, profile_id, dry_run)

    bp_cfg: dict = cfg.get("browser_playback", {})
    browser_path: str = bp_cfg.get("browser_path", "").strip()
    isolated_profile_base: str = bp_cfg.get("isolated_profile_dir", "runtime/browser_isolated")
    isolated_profile_mode: str = bp_cfg.get("isolated_profile_mode", "persistent")
    timeout_ms: int = int(float(bp_cfg.get("playwright_timeout_sec", 30)) * 1000)
    headless: bool = bool(bp_cfg.get("playwright_headless", False))
    use_system_chrome: bool = bool(bp_cfg.get("playwright_use_system_chrome", True))
    profiles: dict = bp_cfg.get("profiles", {})
    profile_cfg: dict = profiles.get(profile_id, {})
    browser_args: list = list(profile_cfg.get("browser_args", []))
    wait_until: str = profile_cfg.get("playwright_wait_until", "domcontentloaded")
    fullscreen_js: bool = bool(profile_cfg.get("playwright_fullscreen_js", False))
    fullscreen_css: str = profile_cfg.get("playwright_fullscreen_css", _DEFAULT_FULLSCREEN_CSS)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    browser_rect = _resolve_browser_rect(cfg, project_root)

    if not os.path.isabs(isolated_profile_base):
        isolated_profile_base = os.path.join(project_root, isolated_profile_base)
    isolated_profile_dir = os.path.join(isolated_profile_base, profile_id or "default")

    if isolated_profile_mode == "ephemeral" and os.path.exists(isolated_profile_dir):
        shutil.rmtree(isolated_profile_dir, ignore_errors=True)

    try:
        os.makedirs(isolated_profile_dir, exist_ok=True)
    except Exception as exc:
        log.error("failed to create profile dir: %s", exc)
        print(f"[browser] ERROR: could not create profile dir: {exc}")
        return 1

    x, y, w, h = browser_rect["x"], browser_rect["y"], browser_rect["w"], browser_rect["h"]

    if dry_run:
        print(f"[browser] [dry-run] Mode B (Playwright)")
        print(f"[browser] [dry-run] url: {url}")
        print(f"[browser] [dry-run] isolated profile: {isolated_profile_dir}")
        print(f"[browser] [dry-run] target rect: x={x} y={y} w={w} h={h}")
        print(f"[browser] [dry-run] use_system_chrome={use_system_chrome}  "
              f"fullscreen_js={fullscreen_js}  headless={headless}")
        return 0

    protected_hwnds = _snapshot_chrome_windows()
    log.info("Mode B: protected set %d window(s)", len(protected_hwnds))
    presets = _build_preset_list(browser_rect, profile_cfg)

    launch_args = [
        "--no-restore-last-session",
        "--disable-session-crashed-bubble",
        "--disable-blink-features=AutomationControlled",
        f"--window-position={x},{y}",
        f"--window-size={w},{h}",
    ] + browser_args

    # Extensions are loaded from the persistent profile automatically.
    # CWS-installed extensions are registered in Default/Secure Preferences and
    # Chrome loads them when --disable-extensions is not present (removed via
    # ignore_default_args above). --load-extension is NOT used here because
    # Chrome blocks loading CWS extensions via that flag as a security policy.
    ext_ids: list = profile_cfg.get("playwright_extensions", [])
    if ext_ids:
        found_count = sum(
            1 for eid in ext_ids
            if os.path.isdir(os.path.join(isolated_profile_dir, "Default", "Extensions", eid))
        )
        log.info("Mode B: %d/%d configured extension(s) found in profile "
                 "(loaded via profile — no --load-extension needed)",
                 found_count, len(ext_ids))

    launch_kwargs: dict = dict(
        headless=headless,
        args=launch_args,
        no_viewport=True,
        ignore_default_args=["--enable-automation", "--disable-extensions"],
    )
    if use_system_chrome and browser_path and os.path.isfile(browser_path):
        launch_kwargs["executable_path"] = browser_path
        log.info("Mode B: using system Chrome at %s", browser_path)
    else:
        log.info("Mode B: using Playwright bundled Chromium")

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(isolated_profile_dir, **launch_kwargs)
            log.info("Mode B: context opened — %d page(s) at launch", len(ctx.pages))
            for _i, _pg in enumerate(ctx.pages):
                log.info("  page[%d] url=%r", _i, _pg.url)

            # Stealth: mask CDP/automation fingerprints before any page JS runs.
            # Runs on every page and frame in the context (including cross-origin iframes).
            ctx.add_init_script(_STEALTH_INIT_SCRIPT)

            # Track new pages/popups opened during the session
            def _on_new_page(new_pg):
                log.info("Mode B: new page opened url=%r", new_pg.url)
            ctx.on("page", _on_new_page)

            # Find the main browser tab — skip chrome:// internal pages and extension pages
            def _main_page():
                navigable = [pg for pg in ctx.pages
                             if not pg.url.startswith("chrome://")
                             and not pg.url.startswith("chrome-extension://")]
                log.info("Mode B: _main_page: total=%d navigable=%d",
                         len(ctx.pages), len(navigable))
                for _i, _pg in enumerate(navigable):
                    log.info("  navigable[%d] url=%r", _i, _pg.url)
                return navigable[0] if navigable else ctx.new_page()

            page = _main_page()
            log.info("Mode B: selected page url=%r", page.url)

            # Navigate and bring the tab to front so it's visible
            try:
                log.info("Mode B: calling goto(%r) wait_until=%r", url, wait_until)
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                log.info("Mode B: goto returned — page.url=%r", page.url)
                page.bring_to_front()
            except PWTimeout:
                log.warning("Mode B: page.goto timed out — continuing. page.url=%r", page.url)
                page.bring_to_front()
            except Exception as exc:
                log.warning("Mode B: page.goto raised: %s. page.url=%r", exc, page.url)

            log.info("Mode B: after navigation — %d page(s) in context", len(ctx.pages))
            for _i, _pg in enumerate(ctx.pages):
                log.info("  page[%d] url=%r", _i, _pg.url)

            # JS override — inject before CSS so requestFullscreen is already patched
            if fullscreen_js:
                try:
                    page.evaluate(_FULLSCREEN_JS_OVERRIDE)
                    log.info("Mode B: fullscreen JS override injected")
                    print("[browser] Mode B: fullscreen JS override active — "
                          "video fills window instead of going OS fullscreen.")
                except Exception as exc:
                    log.warning("Mode B: JS injection failed: %s", exc)

            # CSS injection — fix object-fit in fullscreen
            if fullscreen_css:
                try:
                    page.add_style_tag(content=fullscreen_css)
                    log.info("Mode B: fullscreen CSS injected")
                except Exception as exc:
                    log.warning("Mode B: CSS injection failed: %s", exc)

            # Find window via snapshot diff (no PID from Playwright)
            hwnd = _poll_for_new_window(protected_hwnds, timeout=15.0)
            if hwnd:
                log.info("Mode B: found window hwnd=%d", hwnd)
                placed = _safe_move_window(hwnd, browser_rect, protected_hwnds,
                                           our_pid=None, dry_run=False)
                if not placed:
                    time.sleep(0.5)
                    _safe_move_window(hwnd, browser_rect, protected_hwnds,
                                      our_pid=None, dry_run=False)
            else:
                log.warning("Mode B: window not found — skipping placement")
                print("[browser] Could not find browser window — skipping CRT placement.")

            # Close signalling
            close_event = threading.Event()
            ctx.on("close", lambda: close_event.set())
            for pg in ctx.pages:
                pg.on("close", lambda: close_event.set())

            def _close_fn():
                try:
                    ctx.close()
                except Exception:
                    pass

            _run_key_loop(
                hwnd=hwnd, presets=presets, protected=protected_hwnds,
                our_pid=None, stop_event=close_event, close_fn=_close_fn,
                profile_id=profile_id, project_root=project_root, mode_label="Mode B",
            )

            try:
                ctx.close()
            except Exception:
                pass

    except Exception as exc:
        log.error("Mode B failed: %s", exc)
        print(f"[browser] Mode B error: {exc}")
        print("[browser] Falling back to Mode A.")
        return launch_system_browser(url, cfg, profile_id)

    finally:
        if isolated_profile_mode == "ephemeral":
            try:
                shutil.rmtree(isolated_profile_dir, ignore_errors=True)
            except Exception:
                pass

    return 0
