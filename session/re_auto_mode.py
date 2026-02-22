"""Automatic Resident Evil stack mode (currently on hold but preserved)."""

import json
import os
import time
from typing import Callable, Optional

from session.display_api import (
    current_primary_device_name,
    find_display_by_token,
    set_display_refresh_best_effort,
    set_primary_display_verified,
)
from session.moonlight import (
    ensure_moonlight_running,
    is_gameplay_window_visible,
    is_moonlight_fullscreen,
    move_moonlight_to_crt,
)
from session.moonlight_adjuster import adjust_moonlight
from session.re_config import (
    CRT_CONFIG_PATH,
    CRT_DISPLAY_TOKEN,
    CRT_TARGET_REFRESH_HZ,
    FULLSCREEN_CONFIRM_SECONDS,
    GAME_PROFILES,
    MOONLIGHT_CRT_RECT,
    MOONLIGHT_DIR,
    MOONLIGHT_EXE,
    RE_PRIMARY_DISPLAY_TOKEN,
    REQUIRED_DISPLAY_GROUPS,
    STOP_FLAG,
    VDD_ATTACH_TIMEOUT_SECONDS,
)
from session.re_game import is_re_game_running
from session.re_preflight import ensure_required_displays
from session.re_state import apply_re_mode_system_state
from session.vdd import plug_vdd_and_wait


def start_stack(game: str, restore_fn: Callable[[], int]) -> int:
    """Prepare the CRT environment and wait for the user to launch the game manually."""
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

        if not ensure_moonlight_running(MOONLIGHT_EXE, MOONLIGHT_DIR):
            print("[re-stack] Moonlight requirement failed; aborting.")
            return 1
        if not plug_vdd_and_wait(
            REQUIRED_DISPLAY_GROUPS["moonlight_display"][0],
            timeout_seconds=VDD_ATTACH_TIMEOUT_SECONDS,
        ):
            print("[re-stack] VDD plug in failed; aborting.")
            return 1
        if not ensure_required_displays(REQUIRED_DISPLAY_GROUPS):
            print("[re-stack] Required display set not found; aborting.")
            return 1

        apply_re_mode_system_state()
        state_applied = True

        gameplay_title: Optional[str] = None
        config_title: Optional[str] = None
        try:
            with open(profile, "r", encoding="utf-8") as f:
                prof_data = json.load(f)
            gameplay_title = prof_data.get("_gameplay_title")
            config_title = prof_data.get("_config_title")
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
        primary_switched = False
        game_was_running = False

        while True:
            now = time.time()

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
                        set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
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
                                    "[re-stack] Adjuster open - Arrow keys: move | "
                                    "[ ]: width | -=: height | 1-9: step | "
                                    "c: save CRT | i: save idle | q: quit"
                                )
                                adjust_moonlight()
                                print("[re-stack] Adjuster closed. Resuming session monitoring.")
                        else:
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
            restore_rc = restore_fn()
            if restore_rc != 0:
                print("[re-stack] WARNING: restore reported errors.")

    return 130 if interrupted else 0
