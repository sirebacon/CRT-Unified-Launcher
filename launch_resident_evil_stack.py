"""Resident Evil stack launcher and restore helper.

Usage:
    python launch_resident_evil_stack.py start --game re1
    python launch_resident_evil_stack.py start --game re2
    python launch_resident_evil_stack.py restore
    python launch_resident_evil_stack.py inspect
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

from default_restore import restore_defaults_from_backup
from session.audio import audio_tool_status, set_default_audio_best_effort
from session.display_api import (
    current_primary_device_name,
    current_primary_display,
    enumerate_attached_displays,
    find_display_by_device_name,
    find_display_by_token,
    set_display_refresh_best_effort,
    set_primary_display_entry,
    set_primary_display_verified,
)
from session.moonlight import (
    ensure_moonlight_running,
    is_gameplay_window_visible,
    is_moonlight_fullscreen,
    move_moonlight_to_crt,
    move_moonlight_to_internal,
)
from session.vdd import plug_vdd_and_wait

try:
    import psutil
except Exception:
    psutil = None


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
STOP_FLAG = os.path.join(PROJECT_ROOT, "wrapper_stop_enforce.flag")
STATE_PATH = os.path.join(PROJECT_ROOT, "runtime", "re_stack_state.json")
RE_STACK_LOG_PATH = os.path.join(PROJECT_ROOT, "runtime", "re_stack.log")
CRT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "crt_config.json")
RE_STACK_CONFIG_PATH = os.path.join(PROJECT_ROOT, "re_stack_config.json")


def _load_config() -> dict:
    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[re-stack] Config not found: {RE_STACK_CONFIG_PATH} — using built-in defaults.")
        return {}
    except Exception as e:
        print(f"[re-stack] Config load error: {e} — using built-in defaults.")
        return {}


_cfg = _load_config()
_display_cfg = _cfg.get("display", {})
_audio_cfg = _cfg.get("audio", {})
_profiles_cfg = _cfg.get("game_profiles", {})
_moonlight_cfg = _cfg.get("moonlight", {})

MOONLIGHT_DIR: str = _cfg.get(
    "moonlight_dir", r"D:\Emulators\MoonlightPortable-x64-6.1.0"
)
MOONLIGHT_EXE: str = os.path.join(MOONLIGHT_DIR, "Moonlight.exe")


def _parse_rect_cfg(d: Optional[dict]) -> Optional[tuple]:
    if not d:
        return None
    try:
        return (int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
    except (KeyError, TypeError, ValueError):
        return None


MOONLIGHT_IDLE_RECT: Optional[tuple] = _parse_rect_cfg(_moonlight_cfg.get("idle_rect"))
MOONLIGHT_CRT_RECT: Optional[tuple] = _parse_rect_cfg(_moonlight_cfg.get("crt_rect"))

VDD_ATTACH_TIMEOUT_SECONDS: int = int(_cfg.get("vdd_attach_timeout_seconds", 15))
FULLSCREEN_CONFIRM_SECONDS: float = float(_cfg.get("fullscreen_confirm_seconds", 2.0))

RE_PRIMARY_DISPLAY_TOKEN: str = _display_cfg.get(
    "re_primary_token", "SudoMaker Virtual Display"
)
CRT_DISPLAY_TOKEN: str = _display_cfg.get(
    "crt_token", "NVIDIA GeForce RTX 4090 Laptop GPU"
)
CRT_TARGET_REFRESH_HZ: int = int(_display_cfg.get("crt_target_refresh_hz", 60))
RESTORE_PRIMARY_DISPLAY_TOKEN: str = _display_cfg.get(
    "restore_primary_token", "Intel(R) UHD Graphics"
)
REQUIRED_DISPLAY_GROUPS: Dict[str, List[str]] = _display_cfg.get(
    "required_groups",
    {
        "internal_display": ["Internal Display", "Intel(R) UHD Graphics"],
        "crt_display": ["CP-1262HE", "NVIDIA GeForce RTX 4090 Laptop GPU"],
        "moonlight_display": ["SudoMaker Virtual Display"],
    },
)

RE_AUDIO_DEVICE_TOKEN: str = _audio_cfg.get(
    "re_device_token", "CP-1262HE (NVIDIA High Definition Audio)"
)
RESTORE_AUDIO_DEVICE_TOKEN: str = _audio_cfg.get(
    "restore_device_token", "Speakers (Realtek(R) Audio)"
)

_default_profiles = {
    "re1": "integrations/launchbox/wrapper/profiles/re1-gog.json",
    "re2": "integrations/launchbox/wrapper/profiles/re2-gog.json",
    "re3": "integrations/launchbox/wrapper/profiles/re3-gog.json",
}
GAME_PROFILES: Dict[str, str] = {
    k: (v if os.path.isabs(v) else os.path.join(PROJECT_ROOT, v))
    for k, v in (_profiles_cfg or _default_profiles).items()
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Set up the CRT environment for Resident Evil and wait for the game."
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser(
        "start",
        help="Prepare the stack and wait for manual game launch in Moonlight.",
    )
    p_start.add_argument(
        "--game",
        choices=sorted(GAME_PROFILES.keys()),
        required=True,
        help="Which game profile to use (for gameplay window detection).",
    )

    sub.add_parser("restore", help="Stop enforcement and restore display/audio defaults.")
    sub.add_parser("inspect", help="Inspect display matches and audio tool availability.")
    sub.add_parser(
        "set-idle-pos",
        help="Capture current Moonlight window position and save as the idle (restore) rect.",
    )
    sub.add_parser(
        "set-crt-pos",
        help="Capture current Moonlight window position and save as the CRT rect.",
    )
    sub.add_parser(
        "adjust-moonlight",
        help="Interactive keyboard adjuster: nudge the Moonlight window and save the result.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class _TeeWriter:
    def __init__(self, original_stream, log_stream):
        self._original = original_stream
        self._log = log_stream

    def write(self, data):
        self._original.write(data)
        self._log.write(data)

    def flush(self):
        self._original.flush()
        self._log.flush()


def _enable_persistent_logging() -> None:
    os.makedirs(os.path.dirname(RE_STACK_LOG_PATH), exist_ok=True)
    log_f = open(RE_STACK_LOG_PATH, "a", encoding="utf-8")
    log_f.write(
        "\n==== re-stack session "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====\n"
    )
    log_f.flush()
    sys.stdout = _TeeWriter(sys.stdout, log_f)
    sys.stderr = _TeeWriter(sys.stderr, log_f)
    print(f"[re-stack] Logging to: {RE_STACK_LOG_PATH}")


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

def _write_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def _read_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def _ensure_required_displays() -> bool:
    attached = enumerate_attached_displays()
    print(f"[re-stack] Attached display count: {len(attached)}")

    missing: List[str] = []
    for label, tokens in REQUIRED_DISPLAY_GROUPS.items():
        match = next((find_display_by_token(t) for t in tokens if find_display_by_token(t)), {})
        if match:
            matched_token = next(t for t in tokens if find_display_by_token(t))
            print(
                f"[re-stack] Required display '{label}' matched: "
                f"{match['device_name']} via token '{matched_token}'"
            )
        else:
            missing.append(f"{label} ({' | '.join(tokens)})")

    if missing:
        print("[re-stack] Required display check failed. Missing:")
        for item in missing:
            print(f" - {item}")
        return False

    return True


# ---------------------------------------------------------------------------
# System state
# ---------------------------------------------------------------------------

def _apply_re_mode_system_state() -> None:
    """Save restore state, set CRT refresh, and switch audio.

    The primary display switch is intentionally deferred until the gameplay
    window is confirmed in the enforcement loop.  This keeps the configuration
    screen on the physical Intel UHD display so the user can see and interact
    with it without Moonlight streaming being active.
    """
    primary = current_primary_display()
    _write_state({"previous_primary_device_name": primary.get("device_name", "")})
    set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    set_default_audio_best_effort(RE_AUDIO_DEVICE_TOKEN)


def _apply_restore_system_state() -> bool:
    state = _read_state()
    restored_by_state = False
    prev_device = str(state.get("previous_primary_device_name", "")).strip()
    if prev_device:
        prev = find_display_by_device_name(prev_device)
        if prev and set_primary_display_entry(prev):
            print(f"[re-stack] Primary display restored to previous device: {prev_device}")
            restored_by_state = True

    ok_display = restored_by_state or set_primary_display_verified(RESTORE_PRIMARY_DISPLAY_TOKEN)
    set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    set_default_audio_best_effort(RESTORE_AUDIO_DEVICE_TOKEN)
    # The SudoMaker VDD is an IddCx driver managed by Apollo — it cannot be
    # re-attached via standard Windows display APIs once detached. Leave it
    # attached between sessions; only the primary display and audio are restored.
    move_moonlight_to_internal(
        REQUIRED_DISPLAY_GROUPS["internal_display"],
        MOONLIGHT_DIR,
        idle_rect=MOONLIGHT_IDLE_RECT,
    )
    return ok_display


# ---------------------------------------------------------------------------
# Wrapper process helpers
# ---------------------------------------------------------------------------

def _find_wrapper_pids() -> List[int]:
    if psutil is None:
        return []
    pids: List[int] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if "launchbox_generic_wrapper.py" in cmdline:
                pids.append(int(proc.info["pid"]))
        except Exception:
            continue
    return pids


def _re_process_names() -> List[str]:
    """Return the lowercase process names declared across all loaded game profiles."""
    names: List[str] = []
    for profile_path in GAME_PROFILES.values():
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name in data.get("process_name", []):
                names.append(str(name).lower())
        except Exception:
            continue
    return names


def _is_re_game_running() -> bool:
    """Return True if any RE game process from the known profiles is currently running."""
    if psutil is None:
        return False
    known = set(_re_process_names())
    if not known:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() in known:
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def start_stack(game: str) -> int:
    """Prepare the CRT environment and wait for the user to launch the game manually.

    Flow:
      1. Ensure Moonlight is open (start it if not already running).
      2. Plug VDD, verify required displays, save state, set CRT refresh + audio.
      3. Wait for the gameplay window to appear (user launches the game in Moonlight).
      4. Once confirmed: switch primary to SudoMaker, move Moonlight to CRT.
      5. Monitor for game exit; restore automatically when the game closes.
         (Ctrl+C also triggers restore.)
    """
    profile = GAME_PROFILES[game]
    if not os.path.exists(profile):
        print(f"[re-stack] Profile not found: {profile}")
        return 1

    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
    except Exception:
        pass

    interrupted = False
    state_applied = False

    try:
        if _is_re_game_running():
            print("[re-stack] RE game is already running; aborting.")
            return 1

        # Open Moonlight if it isn't already.  The user launches the game manually
        # from within Moonlight rather than the script auto-launching the exe.
        if not ensure_moonlight_running(MOONLIGHT_EXE, MOONLIGHT_DIR):
            print("[re-stack] Moonlight requirement failed; aborting.")
            return 1
        if not plug_vdd_and_wait(
            REQUIRED_DISPLAY_GROUPS["moonlight_display"][0],
            timeout_seconds=VDD_ATTACH_TIMEOUT_SECONDS,
        ):
            print("[re-stack] VDD plug in failed; aborting.")
            return 1
        if not _ensure_required_displays():
            print("[re-stack] Required display set not found; aborting.")
            return 1

        # Save state, set CRT refresh, switch audio.  Primary switch is deferred
        # until the gameplay window is confirmed so the config GUI remains on the
        # physical Intel UHD display and is visible without Moonlight streaming.
        _apply_re_mode_system_state()
        state_applied = True

        # Load gameplay/config window title hints from the profile.
        gameplay_title: Optional[str] = None
        config_title: Optional[str] = None
        try:
            with open(profile, "r", encoding="utf-8") as f:
                _prof_data = json.load(f)
            gameplay_title = _prof_data.get("_gameplay_title")
            config_title = _prof_data.get("_config_title")
        except Exception:
            pass

        print(f"[re-stack] Environment ready for {game}.")
        print("[re-stack] Launch the game manually in Moonlight when ready.")
        if gameplay_title:
            print(
                f"[re-stack] Waiting for gameplay window '{gameplay_title}'"
                + (f" (blocked while '{config_title}' is visible)" if config_title else "")
            )
        else:
            print("[re-stack] No _gameplay_title in profile; using Moonlight fullscreen detection.")

        target_display = find_display_by_token(RE_PRIMARY_DISPLAY_TOKEN)
        wanted_primary = str(target_display.get("device_name", "")).strip().lower()
        last_refresh_enforce = 0.0
        moonlight_moved_to_crt = False
        moonlight_game_detected_since: Optional[float] = None
        last_detection_log = 0.0
        # primary_switched: False until gameplay is confirmed.  Intel UHD stays
        # primary until then so the config GUI is physically visible.
        primary_switched = False
        game_was_running = False

        while True:
            now = time.time()

            # Only enforce primary drift once we've actually switched it.
            if primary_switched and wanted_primary:
                active = current_primary_device_name().lower()
                if active != wanted_primary:
                    print(
                        f"[re-stack] Primary drift detected "
                        f"({active or 'UNKNOWN'} -> {wanted_primary}). Re-applying."
                    )
                    set_primary_display_verified(RE_PRIMARY_DISPLAY_TOKEN, retries=1)

            if now - last_refresh_enforce >= 5.0:
                set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
                last_refresh_enforce = now

            if not moonlight_moved_to_crt:
                # --- Waiting for user to launch the game ---
                if gameplay_title:
                    in_gameplay = is_gameplay_window_visible(gameplay_title)
                    in_config = bool(config_title and is_gameplay_window_visible(config_title))
                    detected = in_gameplay and not in_config
                else:
                    detected = is_moonlight_fullscreen(MOONLIGHT_DIR)

                if detected:
                    if moonlight_game_detected_since is None:
                        moonlight_game_detected_since = now
                        print(
                            f"[re-stack] Gameplay window '{gameplay_title or 'fullscreen'}' detected "
                            f"(config gone); confirming for {FULLSCREEN_CONFIRM_SECONDS}s..."
                        )
                    elif now - moonlight_game_detected_since >= FULLSCREEN_CONFIRM_SECONDS:
                        print(
                            "[re-stack] Gameplay confirmed; "
                            "switching primary to SudoMaker and moving Moonlight to CRT."
                        )
                        set_primary_display_verified(RE_PRIMARY_DISPLAY_TOKEN)
                        primary_switched = True
                        # Re-enforce CRT refresh after topology change from primary switch.
                        set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
                        # Brief settle: Windows rearranges windows when the primary
                        # changes; Moonlight may be briefly invisible or iconic.
                        print("[re-stack] Waiting 2 s for display topology to settle...")
                        time.sleep(2.0)
                        if move_moonlight_to_crt(
                            REQUIRED_DISPLAY_GROUPS["crt_display"],
                            MOONLIGHT_DIR,
                            crt_config_path=CRT_CONFIG_PATH,
                            crt_rect=MOONLIGHT_CRT_RECT,
                        ):
                            moonlight_moved_to_crt = True
                            print()
                            try:
                                answer = input(
                                    "[re-stack] Adjust Moonlight position on the CRT? [y/N]: "
                                ).strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                answer = ""
                            if answer in ("y", "yes"):
                                print(
                                    "[re-stack] Adjuster open — Arrow keys: move | "
                                    "[ ]: width | -=: height | 1-9: step | "
                                    "c: save CRT | i: save idle | q: quit"
                                )
                                adjust_moonlight()
                                print("[re-stack] Adjuster closed. Resuming session monitoring.")
                        else:
                            # Reset the confirmation timer so the next attempt waits
                            # for the confirm window again instead of retrying immediately.
                            moonlight_game_detected_since = None
                            print("[re-stack] CRT move failed; will retry after re-confirming gameplay.")
                else:
                    if moonlight_game_detected_since is not None:
                        print(
                            f"[re-stack] Gameplay window '{gameplay_title or 'fullscreen'}' "
                            "no longer confirmed; resetting detection timer."
                        )
                    moonlight_game_detected_since = None
                    if now - last_detection_log >= 15.0:
                        if gameplay_title:
                            in_gp = is_gameplay_window_visible(gameplay_title)
                            in_cfg = bool(config_title and is_gameplay_window_visible(config_title))
                            print(
                                f"[re-stack] Waiting for gameplay: "
                                f"'{gameplay_title}'={'yes' if in_gp else 'no'}"
                                + (f", '{config_title}'={'yes (blocking)' if in_cfg else 'no'}"
                                   if config_title else "")
                            )
                        else:
                            print("[re-stack] Waiting for Moonlight fullscreen...")
                        last_detection_log = now
            else:
                # --- Game is running on CRT; watch for exit ---
                is_running = _is_re_game_running()
                if is_running:
                    game_was_running = True
                elif game_was_running:
                    print("[re-stack] RE game has exited. Restoring system state...")
                    break

            time.sleep(1.0)

    except KeyboardInterrupt:
        interrupted = True
        print("[re-stack] Ctrl+C detected. Restoring system state...")

    finally:
        if state_applied:
            restore_rc = restore_stack()
            if restore_rc != 0:
                print("[re-stack] WARNING: restore reported errors.")

    if interrupted:
        return 130
    return 0


def restore_stack() -> int:
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as f:
            f.write("stop\n")
    except Exception:
        pass

    stopped: List[int] = []
    pids = _find_wrapper_pids()
    for pid in pids:
        try:
            proc = psutil.Process(pid) if psutil is not None else None
            if proc is None:
                continue
            proc.terminate()
            proc.wait(timeout=3)
            stopped.append(pid)
        except Exception:
            try:
                if psutil is not None:
                    psutil.Process(pid).kill()
                    stopped.append(pid)
            except Exception:
                pass

    ok, msg, restored = restore_defaults_from_backup()
    print(f"[re-stack] {msg}")
    if stopped:
        print("[re-stack] Stopped wrapper PID(s): " + ", ".join(str(pid) for pid in stopped))
    if restored:
        print("[re-stack] Restored files:")
        for item in restored:
            print(f" - {item}")

    try:
        if os.path.exists(STOP_FLAG):
            os.remove(STOP_FLAG)
    except Exception:
        pass

    state_ok = _apply_restore_system_state()
    return 0 if (ok and state_ok) else 1


def inspect_state() -> int:
    displays = enumerate_attached_displays()
    if not displays:
        print("[re-stack] No attached displays found or display API unavailable.")
    else:
        print("[re-stack] Attached displays:")
        for d in displays:
            mons = ", ".join(d["monitor_strings"]) if d["monitor_strings"] else "(none)"
            print(
                f" - {d['device_name']} | {d['device_string']} | "
                f"pos={d['position'][0]},{d['position'][1]} | monitors={mons}"
            )

    re_match = find_display_by_token(RE_PRIMARY_DISPLAY_TOKEN)
    restore_match = find_display_by_token(RESTORE_PRIMARY_DISPLAY_TOKEN)
    primary_now = current_primary_display()
    print(
        f"[re-stack] Current primary display: "
        f"{primary_now.get('device_name', 'UNKNOWN')} | "
        f"{primary_now.get('device_string', '')}"
    )
    print(
        f"[re-stack] RE primary token '{RE_PRIMARY_DISPLAY_TOKEN}' match: "
        f"{re_match.get('device_name', 'NOT FOUND')}"
    )
    print(
        f"[re-stack] Restore primary token '{RESTORE_PRIMARY_DISPLAY_TOKEN}' match: "
        f"{restore_match.get('device_name', 'NOT FOUND')}"
    )

    tool = audio_tool_status()
    print(f"[re-stack] Audio switch tool: {tool}")
    print(f"[re-stack] RE audio token: {RE_AUDIO_DEVICE_TOKEN}")
    print(f"[re-stack] Restore audio token: {RESTORE_AUDIO_DEVICE_TOKEN}")
    return 0


def _write_moonlight_rect(config_key: str, x: int, y: int, w: int, h: int) -> bool:
    """Write a Moonlight rect to re_stack_config.json. Returns True on success."""
    try:
        with open(RE_STACK_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[re-stack] Could not read config: {e}")
        return False
    if "moonlight" not in cfg:
        cfg["moonlight"] = {}
    cfg["moonlight"][config_key] = {"x": x, "y": y, "w": w, "h": h}
    try:
        with open(RE_STACK_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"[re-stack] Could not write config: {e}")
        return False


def capture_moonlight_pos(config_key: str) -> int:
    """Capture the current Moonlight window rect and write it to re_stack_config.json."""
    from session.window_utils import find_window, get_rect
    import win32gui
    hwnd = find_window(None, [], ["moonlight"])
    if hwnd is None:
        print("[re-stack] No Moonlight window found — make sure Moonlight is open.")
        return 1
    x, y, w, h = get_rect(hwnd)
    title = win32gui.GetWindowText(hwnd)
    print(f"[re-stack] Moonlight window: {title!r}  x={x}, y={y}, w={w}, h={h}")
    label = "idle (restore)" if config_key == "idle_rect" else "CRT"
    if _write_moonlight_rect(config_key, x, y, w, h):
        print(f"[re-stack] Saved as Moonlight {label} rect in re_stack_config.json.")
        return 0
    return 1


def adjust_moonlight() -> int:
    """Interactive keyboard-driven Moonlight window position/size adjuster.

    Move and resize the Moonlight window live, then save the result to config.

    Controls
    --------
    Arrow keys          Move left / right / up / down
    [ / ]               Narrower / wider  (decrease/increase width)
    - / =               Shorter / taller  (decrease/increase height)
    1 – 9               Step size: 1, 5, 10, 25, 50, 100, 200, 500, 1000 px
    i                   Save current position as idle (restore) rect
    c                   Save current position as CRT rect
    q  or  Esc          Quit without saving
    """
    import msvcrt
    import win32gui
    from session.window_utils import find_window, get_rect, move_window

    STEPS = [1, 5, 10, 25, 50, 100, 200, 500, 1000]
    step_idx = 2  # default 10 px

    hwnd = find_window(None, [], ["moonlight"])
    if hwnd is None:
        print("No Moonlight window found — make sure Moonlight is open.")
        return 1

    x, y, w, h = get_rect(hwnd)
    title = win32gui.GetWindowText(hwnd)

    print(f"=== Moonlight Window Adjuster  ({title}) ===")
    print("  Arrow keys   move x/y          [ / ]   narrower / wider")
    print("  - / =        shorter / taller  1-9     step size")
    print("  i  save idle rect              c       save CRT rect")
    print("  q / Esc      quit without saving")
    print()

    def _show():
        step = STEPS[step_idx]
        print(
            f"\r  x={x:6d}  y={y:6d}  w={w:6d}  h={h:6d}  step={step:4d}px    ",
            end="",
            flush=True,
        )

    def _apply():
        try:
            move_window(hwnd, x, y, w, h, strip_caption=False)
        except Exception as e:
            print(f"\n  move failed: {e}")

    _show()

    while True:
        ch = msvcrt.getch()

        if ch == b"\xe0":
            # Extended key — read the second byte
            ch2 = msvcrt.getch()
            step = STEPS[step_idx]
            if ch2 == b"H":    y -= step                            # up
            elif ch2 == b"P":  y += step                            # down
            elif ch2 == b"K":  x -= step                            # left
            elif ch2 == b"M":  x += step                            # right
            else:
                continue
            _apply()
            _show()

        elif ch == b"[":
            w = max(1, w - STEPS[step_idx]); _apply(); _show()
        elif ch == b"]":
            w += STEPS[step_idx]; _apply(); _show()
        elif ch == b"-":
            h = max(1, h - STEPS[step_idx]); _apply(); _show()
        elif ch in (b"=", b"+"):
            h += STEPS[step_idx]; _apply(); _show()

        elif ch in b"123456789":
            step_idx = int(ch) - 1
            _show()

        elif ch in (b"i", b"I"):
            print()
            if _write_moonlight_rect("idle_rect", x, y, w, h):
                print(f"  Saved idle rect: x={x}, y={y}, w={w}, h={h}")
            _show()

        elif ch in (b"c", b"C"):
            print()
            if _write_moonlight_rect("crt_rect", x, y, w, h):
                print(f"  Saved CRT rect:  x={x}, y={y}, w={w}, h={h}")
            _show()

        elif ch in (b"q", b"Q", b"\x1b"):
            print("\n  Quit — no changes saved.")
            break

    return 0


def main() -> int:
    args = parse_args()
    # adjust-moonlight is interactive; skip log tee so \r status line works cleanly.
    if args.command == "adjust-moonlight":
        return adjust_moonlight()
    _enable_persistent_logging()
    if args.command == "start":
        return start_stack(args.game)
    if args.command == "restore":
        return restore_stack()
    if args.command == "set-idle-pos":
        return capture_moonlight_pos("idle_rect")
    if args.command == "set-crt-pos":
        return capture_moonlight_pos("crt_rect")
    return inspect_state()


if __name__ == "__main__":
    raise SystemExit(main())
