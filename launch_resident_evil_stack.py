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
from typing import List, Optional

from default_restore import restore_defaults_from_backup
from session.audio import audio_tool_status, set_default_audio_best_effort
from session.display_api import (
    current_primary_device_name,
    current_primary_display,
    enumerate_attached_displays,
    find_display_by_token,
    get_crt_display_rect,
    get_display_mode,
    set_display_refresh_best_effort,
    set_primary_display_verified,
)
from session.moonlight import (
    ensure_moonlight_running,
    is_gameplay_window_visible,
    is_moonlight_fullscreen,
    move_moonlight_to_crt,
    move_moonlight_to_internal,
)
from session.moonlight_adjuster import adjust_moonlight, capture_moonlight_pos
from session.re_config import (
    CRT_CONFIG_PATH,
    CRT_DISPLAY_TOKEN,
    CRT_TARGET_REFRESH_HZ,
    FULLSCREEN_CONFIRM_SECONDS,
    GAME_PROFILES,
    MOONLIGHT_CRT_RECT,
    MOONLIGHT_DIR,
    MOONLIGHT_EXE,
    MOONLIGHT_IDLE_RECT,
    RE_AUDIO_DEVICE_TOKEN,
    RE_PRIMARY_DISPLAY_TOKEN,
    RE_STACK_CONFIG_PATH,
    RE_STACK_LOG_PATH,
    REQUIRED_DISPLAY_GROUPS,
    RESTORE_AUDIO_DEVICE_TOKEN,
    RESTORE_PRIMARY_DISPLAY_TOKEN,
    STATE_PATH,
    STOP_FLAG,
    VDD_ATTACH_TIMEOUT_SECONDS,
)
from session.re_game import find_wrapper_pids, is_re_game_running
from session.re_state import apply_re_mode_system_state, apply_restore_system_state
from session.vdd import plug_vdd_and_wait
from session.window_utils import find_window, get_rect, move_window

try:
    import psutil
except Exception:
    psutil = None


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

    p_manual = sub.add_parser(
        "manual",
        help="Guided manual RE mode (you control display settings/primary).",
    )
    p_manual.add_argument(
        "--game",
        choices=sorted(GAME_PROFILES.keys()),
        required=True,
        help="Which game profile to use (for process monitoring/log labeling).",
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


def _attached_display_count() -> int:
    return len(enumerate_attached_displays())


def _open_windows_display_settings() -> None:
    try:
        if os.name == "nt" and hasattr(os, "startfile"):
            os.startfile("ms-settings:display")  # type: ignore[attr-defined]
            print("[re-stack] Opened Windows Display Settings (ms-settings:display).")
            return
    except Exception as e:
        print(f"[re-stack] Could not open Display Settings via startfile: {e}")

    for cmd in (
        ["explorer.exe", "ms-settings:display"],
        ["cmd", "/c", "start", "", "ms-settings:display"],
    ):
        try:
            subprocess.Popen(cmd)
            print("[re-stack] Opened Windows Display Settings (ms-settings:display).")
            return
        except Exception:
            continue
    print("[re-stack] Could not open Windows Display Settings automatically.")


def _open_re_game_folder(profile_path: str) -> None:
    """Open the selected RE game folder in Windows Explorer for manual launch."""
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        target_dir = str(data.get("dir") or "").strip()
        target_exe = str(data.get("path") or "").strip()
        if target_dir and os.path.isdir(target_dir):
            print(f"[re-stack] Opening RE game folder: {target_dir}")
            try:
                if os.name == "nt" and hasattr(os, "startfile"):
                    os.startfile(target_dir)  # type: ignore[attr-defined]
                    print(f"[re-stack] Opened RE game folder: {target_dir}")
                    return
            except Exception as e:
                print(f"[re-stack] os.startfile failed for RE folder: {e}")
            for cmd in (
                ["explorer.exe", target_dir],
                ["cmd", "/c", "start", "", target_dir],
            ):
                try:
                    subprocess.Popen(cmd)
                    print(f"[re-stack] Opened RE game folder: {target_dir}")
                    return
                except Exception:
                    continue
        if target_exe:
            exe_dir = os.path.dirname(target_exe)
            if exe_dir and os.path.isdir(exe_dir):
                print(f"[re-stack] Opening RE game folder: {exe_dir}")
                try:
                    if os.name == "nt" and hasattr(os, "startfile"):
                        os.startfile(exe_dir)  # type: ignore[attr-defined]
                        print(f"[re-stack] Opened RE game folder: {exe_dir}")
                        return
                except Exception as e:
                    print(f"[re-stack] os.startfile failed for RE folder: {e}")
                for cmd in (
                    ["explorer.exe", exe_dir],
                    ["cmd", "/c", "start", "", exe_dir],
                ):
                    try:
                        subprocess.Popen(cmd)
                        print(f"[re-stack] Opened RE game folder: {exe_dir}")
                        return
                    except Exception:
                        continue
        print("[re-stack] Could not open RE game folder (directory not found in profile).")
    except Exception as e:
        print(f"[re-stack] Could not open RE game folder from profile '{profile_path}': {e}")


def _folder_window_title_hint_from_profile(profile_path: str) -> str:
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        target_dir = str(data.get("dir") or "").strip()
        if target_dir:
            return os.path.basename(os.path.normpath(target_dir)).lower()
        target_exe = str(data.get("path") or "").strip()
        if target_exe:
            return os.path.basename(os.path.dirname(target_exe)).lower()
    except Exception:
        pass
    return "resident evil"


def _move_re_folder_window_to_internal(profile_path: str) -> bool:
    """Best-effort: move the opened RE Explorer folder window onto the internal display."""
    rect = get_crt_display_rect(REQUIRED_DISPLAY_GROUPS["internal_display"])
    if rect is None:
        if MOONLIGHT_IDLE_RECT is not None:
            ix, iy, iw, ih = MOONLIGHT_IDLE_RECT
        else:
            print("[re-stack] Could not detect internal display for RE folder placement.")
            return False
    else:
        ix, iy, iw, ih = rect

    # Keep a margin so the Explorer frame stays fully visible.
    margin_x = 60
    margin_y = 60
    x = ix + margin_x
    y = iy + margin_y
    w = max(700, min(1400, iw - (margin_x * 2)))
    h = max(500, min(900, ih - (margin_y * 2)))

    title_hint = _folder_window_title_hint_from_profile(profile_path)
    for _ in range(24):
        hwnd = find_window(None, ["cabinetwclass"], [title_hint], match_any_pid=True)
        if hwnd is None:
            # Fallback: any visible Explorer window if exact title is not available yet.
            hwnd = find_window(None, ["cabinetwclass"], [], match_any_pid=True)
        if hwnd:
            try:
                move_window(hwnd, x, y, w, h, strip_caption=False)
                print(
                    "[re-stack] RE folder window moved to Internal Display: "
                    f"x={x}, y={y}, w={w}, h={h}"
                )
                return True
            except Exception as e:
                print(f"[re-stack] Failed moving RE folder window to Internal Display: {e}")
                return False
        time.sleep(0.25)

    print("[re-stack] Could not find RE folder Explorer window to move to Internal Display.")
    return False


def _find_re_folder_window(profile_path: str) -> Optional[int]:
    title_hint = _folder_window_title_hint_from_profile(profile_path)
    hwnd = find_window(None, ["cabinetwclass"], [title_hint], match_any_pid=True)
    if hwnd is None:
        hwnd = find_window(None, ["cabinetwclass"], [], match_any_pid=True)
    return hwnd


def _rect_overlap_ratio(a: tuple, b: tuple) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    ix = max(0, min(ax2, bx2) - max(ax, bx))
    iy = max(0, min(ay2, by2) - max(ay, by))
    area = aw * ah
    return ((ix * iy) / area) if area > 0 else 0.0


def _is_re_folder_on_moonlight_display(profile_path: str) -> Optional[bool]:
    moon_rect = get_crt_display_rect(REQUIRED_DISPLAY_GROUPS["moonlight_display"])
    if moon_rect is None:
        return None
    hwnd = _find_re_folder_window(profile_path)
    if hwnd is None:
        return None
    try:
        win_rect = get_rect(hwnd)
    except Exception:
        return None
    return _rect_overlap_ratio(win_rect, moon_rect) >= 0.5


def _move_moonlight_back_to_internal_manual() -> bool:
    """Manual mode return path: prefer current internal display bounds over saved idle rect."""
    print("[re-stack] Returning Moonlight to Internal Display using current display layout...")
    # In manual mode the user may have changed topology/positions, so the saved
    # idle rect can be stale. Prefer live internal display bounds first.
    if move_moonlight_to_internal(
        REQUIRED_DISPLAY_GROUPS["internal_display"],
        MOONLIGHT_DIR,
        idle_rect=None,
    ):
        return True
    print("[re-stack] Live internal display move failed; trying configured idle rect fallback...")
    return move_moonlight_to_internal(
        REQUIRED_DISPLAY_GROUPS["internal_display"],
        MOONLIGHT_DIR,
        idle_rect=MOONLIGHT_IDLE_RECT,
    )


def _print_manual_mode_checklist(game: str) -> None:
    print(f"[re-stack] Manual RE mode ready for {game}.")
    print("[re-stack] Follow these steps before continuing:")
    print(" 1. The RE game folder should already be open in Explorer.")
    print(" 2. In Windows Display Settings, confirm all 3 displays are attached.")
    print(" 3. Set/verify resolutions for Internal, CRT, and SudoMaker displays.")
    print(" 4. Set the PRIMARY display manually (you will handle this).")
    print(" 5. Return here and press Enter so I can verify monitor presence.")
    print(" 6. I will move Moonlight to the CRT screen for you.")
    print(" 7. Move the RE folder window onto the Moonlight screen and launch the game manually.")
    print(" 8. When the game exits, I will move Moonlight back to the Internal Display.")
    print("    (You will change primary display back manually.)")


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
        if is_re_game_running():
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
        apply_re_mode_system_state()
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
                is_running = is_re_game_running()
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


def manual_stack(game: str) -> int:
    """Guided manual RE mode.

    This mode launches Moonlight and opens Windows Display Settings, but leaves
    display mode changes and primary switching to the user. It verifies that the
    required displays are present, then waits for the RE game process to start
    and later exit. On exit, Moonlight is moved back to the internal display.
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
    game_was_running = False
    last_wait_log = 0.0

    try:
        if is_re_game_running():
            print("[re-stack] RE game is already running; aborting manual mode.")
            return 1

        if not ensure_moonlight_running(MOONLIGHT_EXE, MOONLIGHT_DIR):
            print("[re-stack] Moonlight requirement failed; aborting.")
            return 1

        _open_re_game_folder(profile)
        _move_re_folder_window_to_internal(profile)

        if not plug_vdd_and_wait(
            REQUIRED_DISPLAY_GROUPS["moonlight_display"][0],
            timeout_seconds=VDD_ATTACH_TIMEOUT_SECONDS,
        ):
            print("[re-stack] VDD plug in failed; aborting.")
            return 1

        _open_windows_display_settings()
        # Re-assert folder placement after topology changes / settings window opens.
        _move_re_folder_window_to_internal(profile)
        print()
        _print_manual_mode_checklist(game)
        print()
        input("[re-stack] Press Enter after you have finished the manual display setup steps...")

        count = _attached_display_count()
        print(f"[re-stack] Attached display count after manual setup: {count}")
        if count != 3:
            print("[re-stack] Expected 3 attached displays. Please fix display setup and try again.")
            return 1
        if not _ensure_required_displays():
            print("[re-stack] Required display set not found after manual setup.")
            return 1

        print("[re-stack] Verified 3 displays and required display matches.")
        print("[re-stack] Moving Moonlight to CRT display...")
        moved = move_moonlight_to_crt(
            REQUIRED_DISPLAY_GROUPS["crt_display"],
            MOONLIGHT_DIR,
            crt_config_path=CRT_CONFIG_PATH,
            crt_rect=MOONLIGHT_CRT_RECT,
        )
        if not moved:
            print("[re-stack] Could not move Moonlight to CRT. Fix placement manually and retry.")
            return 1

        print("[re-stack] Moonlight moved to CRT.")
        set_default_audio_best_effort(RE_AUDIO_DEVICE_TOKEN)
        folder_on_moonlight = _is_re_folder_on_moonlight_display(profile)
        if folder_on_moonlight is True:
            print("[re-stack] RE folder window appears to already be on the Moonlight display.")
        elif folder_on_moonlight is False:
            print("[re-stack] RE folder window does not appear to be on the Moonlight display yet.")
        else:
            print("[re-stack] Could not verify RE folder window placement on Moonlight display.")
        print("[re-stack] Move the already-open RE folder window to the Moonlight screen.")
        print("[re-stack] Start the game manually from that folder when ready.")
        input("[re-stack] Press Enter after you have launched the game...")
        print("[re-stack] I will now wait for the RE game process to start, then monitor for exit.")

        while True:
            now = time.time()
            running = is_re_game_running()
            if running:
                if not game_was_running:
                    game_was_running = True
                    print("[re-stack] RE game process detected. Monitoring for exit...")
            elif game_was_running:
                print("[re-stack] RE game has exited. Moving Moonlight back to Internal Display...")
                _move_moonlight_back_to_internal_manual()
                set_default_audio_best_effort(RESTORE_AUDIO_DEVICE_TOKEN)
                print("[re-stack] Moonlight move-to-internal requested.")
                print("[re-stack] Reminder: set your primary display back manually.")
                break
            elif now - last_wait_log >= 10.0:
                print("[re-stack] Waiting for RE game process to start...")
                last_wait_log = now

            time.sleep(1.0)

    except KeyboardInterrupt:
        interrupted = True
        print("[re-stack] Ctrl+C detected.")
        print("[re-stack] Attempting to move Moonlight back to Internal Display...")
        try:
            _move_moonlight_back_to_internal_manual()
            set_default_audio_best_effort(RESTORE_AUDIO_DEVICE_TOKEN)
        except Exception:
            pass
        print("[re-stack] Reminder: set your primary display manually as needed.")

    return 130 if interrupted else 0


def restore_stack() -> int:
    try:
        with open(STOP_FLAG, "w", encoding="utf-8") as f:
            f.write("stop\n")
    except Exception:
        pass

    stopped: List[int] = []
    pids = find_wrapper_pids()
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

    state_ok = apply_restore_system_state()
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


def main() -> int:
    args = parse_args()
    # adjust-moonlight is interactive; skip log tee so \r status line works cleanly.
    if args.command == "adjust-moonlight":
        return adjust_moonlight()
    _enable_persistent_logging()
    if args.command == "start":
        return start_stack(args.game)
    if args.command == "manual":
        return manual_stack(args.game)
    if args.command == "restore":
        return restore_stack()
    if args.command == "set-idle-pos":
        return capture_moonlight_pos("idle_rect")
    if args.command == "set-crt-pos":
        return capture_moonlight_pos("crt_rect")
    return inspect_state()


if __name__ == "__main__":
    raise SystemExit(main())
