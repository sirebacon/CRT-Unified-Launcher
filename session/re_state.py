"""State file I/O and system-state apply/restore for the RE stack."""

import json
import os
import time

from session.re_config import (
    STATE_PATH,
    CRT_DISPLAY_TOKEN,
    CRT_TARGET_REFRESH_HZ,
    RE_AUDIO_DEVICE_TOKEN,
    RESTORE_AUDIO_DEVICE_TOKEN,
    MOONLIGHT_DIR,
    MOONLIGHT_IDLE_RECT,
    REQUIRED_DISPLAY_GROUPS,
    RESTORE_PRIMARY_DISPLAY_TOKEN,
)
from session.display_api import (
    current_primary_display,
    get_display_mode,
    restore_display_mode,
    set_display_refresh_best_effort,
    set_primary_display_verified,
)
from session.audio import set_default_audio_best_effort
from session.moonlight import move_moonlight_to_internal


def write_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def read_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def apply_re_mode_system_state() -> None:
    """Save restore state, set CRT refresh, and switch audio.

    The primary display switch is intentionally deferred until the gameplay
    window is confirmed in the enforcement loop.  This keeps the configuration
    screen on the physical Intel UHD display so the user can see and interact
    with it without Moonlight streaming being active.
    """
    primary = current_primary_display()
    crt_mode = get_display_mode(CRT_DISPLAY_TOKEN)
    write_state({
        "previous_primary_device_name": primary.get("device_name", ""),
        "crt_mode": crt_mode,
    })
    if crt_mode:
        print(
            f"[re-stack] CRT mode saved: "
            f"{crt_mode['width']}x{crt_mode['height']}@{crt_mode['hz']}Hz "
            f"on {crt_mode['device_name']}"
        )
    set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
    set_default_audio_best_effort(RE_AUDIO_DEVICE_TOKEN)


def apply_restore_system_state() -> bool:
    # Always restore via the verified path: it reads back current_primary_device_name()
    # after each attempt and retries up to 3 times.  The previous unverified
    # set_primary_display_entry() path would return True even when SetDisplayConfig
    # reported success but the primary hadn't actually switched, causing the
    # short-circuit `or` to skip any further attempts.
    ok_display = set_primary_display_verified(RESTORE_PRIMARY_DISPLAY_TOKEN)

    # After a primary switch the NVIDIA hybrid-GPU driver may be in a transitional
    # state for several seconds, causing ChangeDisplaySettingsEx to return
    # DISP_CHANGE_FAILED (-1) even for valid modes.  Retry with backoff until the
    # driver accepts the change or we exhaust attempts.
    saved_crt = read_state().get("crt_mode")
    for attempt, wait in enumerate((1.5, 2.0, 3.0, 4.0), start=1):
        time.sleep(wait)
        if saved_crt:
            ok = restore_display_mode(saved_crt)
        else:
            ok = set_display_refresh_best_effort(CRT_DISPLAY_TOKEN, CRT_TARGET_REFRESH_HZ)
        if ok:
            break
        print(f"[re-stack] CRT mode apply attempt {attempt} failed; retrying...")

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
