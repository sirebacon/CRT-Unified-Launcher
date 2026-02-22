"""Guided manual Resident Evil stack mode."""

import json
import os
import subprocess
import time
from typing import Optional, Tuple

from session.audio import set_default_audio_best_effort
from session.display_api import get_crt_display_rect
from session.moonlight import (
    ensure_moonlight_running,
    find_moonlight_window,
    move_moonlight_to_crt,
    move_moonlight_to_internal,
)
from session.re_config import (
    CRT_CONFIG_PATH,
    GAME_PROFILES,
    MOONLIGHT_CRT_RECT,
    MOONLIGHT_DIR,
    MOONLIGHT_EXE,
    MOONLIGHT_IDLE_RECT,
    RE_AUDIO_DEVICE_TOKEN,
    REQUIRED_DISPLAY_GROUPS,
    RESTORE_AUDIO_DEVICE_TOKEN,
    STOP_FLAG,
    VDD_ATTACH_TIMEOUT_SECONDS,
)
from session.re_game import is_re_game_running
from session.re_preflight import (
    attached_display_count,
    ensure_required_displays,
    open_windows_display_settings,
)
from session.vdd import plug_vdd_and_wait
from session.window_utils import find_window, get_rect, move_window


def _open_re_game_folder(profile_path: str) -> None:
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
            for cmd in (["explorer.exe", target_dir], ["cmd", "/c", "start", "", target_dir]):
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
                for cmd in (["explorer.exe", exe_dir], ["cmd", "/c", "start", "", exe_dir]):
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


def _find_re_folder_window(profile_path: str) -> Optional[int]:
    title_hint = _folder_window_title_hint_from_profile(profile_path)
    hwnd = find_window(None, ["cabinetwclass"], [title_hint], match_any_pid=True)
    if hwnd is None:
        hwnd = find_window(None, ["cabinetwclass"], [], match_any_pid=True)
    return hwnd


def _get_re_folder_window_size(profile_key: str) -> Optional[Tuple[int, int]]:
    profile_path = GAME_PROFILES.get(profile_key)
    if not profile_path or not os.path.exists(profile_path):
        return None
    title_hint = _folder_window_title_hint_from_profile(profile_path)
    hwnd = find_window(None, ["cabinetwclass"], [title_hint], match_any_pid=True)
    if hwnd is None:
        return None
    try:
        _, _, w, h = get_rect(hwnd)
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return (w, h)


def _get_re_folder_template_size() -> Optional[Tuple[int, int]]:
    for key in ("re1", "re2", "re3"):
        size = _get_re_folder_window_size(key)
        if size is None:
            continue
        w, h = size
        print(f"[re-stack] Using current {key.upper()} folder window size as template: w={w}, h={h}")
        return size
    return None


def _move_re_folder_window_to_internal(profile_path: str) -> bool:
    rect = get_crt_display_rect(REQUIRED_DISPLAY_GROUPS["internal_display"])
    if rect is None:
        if MOONLIGHT_IDLE_RECT is not None:
            ix, iy, iw, ih = MOONLIGHT_IDLE_RECT
        else:
            print("[re-stack] Could not detect internal display for RE folder placement.")
            return False
    else:
        ix, iy, iw, ih = rect

    margin_x = 60
    margin_y = 60
    x = ix + margin_x
    y = iy + margin_y
    ref_size = _get_re_folder_template_size()
    if ref_size is not None:
        pref_w, pref_h = ref_size
    else:
        pref_w, pref_h = (1400, 900)
    w = max(700, min(pref_w, iw - (margin_x * 2)))
    h = max(500, min(pref_h, ih - (margin_y * 2)))

    title_hint = _folder_window_title_hint_from_profile(profile_path)
    for _ in range(24):
        hwnd = find_window(None, ["cabinetwclass"], [title_hint], match_any_pid=True)
        if hwnd is None:
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


def _rect_overlap_ratio(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
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


def _capture_moonlight_rect_for_manual_restore() -> Optional[Tuple[int, int, int, int]]:
    try:
        hwnd = find_moonlight_window(MOONLIGHT_DIR)
        if not hwnd:
            return None
        rect = get_rect(hwnd)
        x, y, w, h = rect
        print(
            "[re-stack] Captured Moonlight manual restore rect: "
            f"x={x}, y={y}, w={w}, h={h}"
        )
        return rect
    except Exception:
        return None


def _move_moonlight_back_to_internal_manual(
    restore_rect: Optional[Tuple[int, int, int, int]] = None,
) -> bool:
    if restore_rect is not None:
        x, y, w, h = restore_rect
        print(
            "[re-stack] Returning Moonlight to pre-move manual rect: "
            f"x={x}, y={y}, w={w}, h={h}"
        )
        if move_moonlight_to_internal(
            REQUIRED_DISPLAY_GROUPS["internal_display"],
            MOONLIGHT_DIR,
            idle_rect=restore_rect,
        ):
            return True
        print("[re-stack] Pre-move rect restore failed; trying current internal display layout...")
    else:
        print("[re-stack] Returning Moonlight to Internal Display using current display layout...")

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


def manual_stack(game: str) -> int:
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
    manual_return_rect: Optional[Tuple[int, int, int, int]] = None

    try:
        if is_re_game_running():
            print("[re-stack] RE game is already running; aborting manual mode.")
            return 1

        if not ensure_moonlight_running(MOONLIGHT_EXE, MOONLIGHT_DIR):
            print("[re-stack] Moonlight requirement failed; aborting.")
            return 1

        manual_return_rect = _capture_moonlight_rect_for_manual_restore()

        _open_re_game_folder(profile)
        _move_re_folder_window_to_internal(profile)

        if not plug_vdd_and_wait(
            REQUIRED_DISPLAY_GROUPS["moonlight_display"][0],
            timeout_seconds=VDD_ATTACH_TIMEOUT_SECONDS,
        ):
            print("[re-stack] VDD plug in failed; aborting.")
            return 1

        open_windows_display_settings()
        _move_re_folder_window_to_internal(profile)
        print()
        _print_manual_mode_checklist(game)
        print()
        input("[re-stack] Press Enter after you have finished the manual display setup steps...")

        count = attached_display_count()
        print(f"[re-stack] Attached display count after manual setup: {count}")
        if count != 3:
            print("[re-stack] Expected 3 attached displays. Please fix display setup and try again.")
            return 1
        if not ensure_required_displays(REQUIRED_DISPLAY_GROUPS):
            print("[re-stack] Required display set not found after manual setup.")
            return 1

        print("[re-stack] Verified 3 displays and required display matches.")
        if manual_return_rect is None:
            manual_return_rect = _capture_moonlight_rect_for_manual_restore()
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
                _move_moonlight_back_to_internal_manual(manual_return_rect)
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
            _move_moonlight_back_to_internal_manual(manual_return_rect)
            set_default_audio_best_effort(RESTORE_AUDIO_DEVICE_TOKEN)
        except Exception:
            pass
        print("[re-stack] Reminder: set your primary display manually as needed.")

    return 130 if interrupted else 0
