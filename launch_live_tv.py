"""Launch VLC Live TV and manage CRT/main window placement."""

from __future__ import annotations

import logging
import msvcrt
import os
import subprocess
import sys
import time

from media.live_tv.config import load_live_tv_config, validate_live_tv_config
from media.live_tv.adjust import handle_adjust_key, show_adjust_mode, show_adjust_status
from media.live_tv.controls import decode_key
from media.live_tv.vlc_process import start_vlc
from media.live_tv.window_session import get_rect_text, move_to_rect, wait_for_vlc_window
from session.window_utils import get_rect


def _setup_log() -> logging.Logger:
    project_root = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(project_root, "runtime", "live_tv.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    log = logging.getLogger("live_tv")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    log.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return log


def main() -> int:
    log = _setup_log()
    log.info("=== live_tv launcher started")

    cfg = load_live_tv_config()
    log.debug(
        "config loaded: enabled=%s vlc_path=%s fullscreen=%s user_rect_is_set=%s disable_vlc_autoresize=%s cache_ms=%s crt_rect=%s main_rect=%s playlist_set=%s",
        cfg.get("enabled"),
        cfg.get("vlc_path"),
        cfg.get("fullscreen"),
        cfg.get("user_rect_is_set"),
        cfg.get("disable_vlc_autoresize"),
        cfg.get("network_caching_ms"),
        cfg.get("crt_rect"),
        cfg.get("main_rect"),
        bool(cfg.get("playlist_url")),
    )
    err = validate_live_tv_config(cfg)
    if err:
        log.warning("config validation failed: %s", err)
        print(f"[live-tv] {err}")
        return 1

    print("[live-tv] Starting VLC...")
    try:
        proc = start_vlc(cfg)
        log.info("vlc started pid=%s", proc.pid)
    except Exception as e:
        log.exception("failed to start vlc: %s", e)
        print(f"[live-tv] Failed to start VLC: {e}")
        return 1

    hwnd = wait_for_vlc_window(proc.pid, cfg["window_find_timeout_sec"])
    if hwnd:
        log.info("vlc window attached hwnd=0x%x", hwnd)
        move_to_rect(hwnd, cfg["crt_rect"])
        log.info("window moved to crt rect=%s", cfg["crt_rect"])
        print(f"[live-tv] Window moved to CRT ({get_rect_text(hwnd)}).")
    else:
        log.warning("vlc window not found within %.1fs", cfg["window_find_timeout_sec"])
        print("[live-tv] WARNING: VLC window not found in time; controls still active.")

    print("[live-tv] Controls: [A] adjust window  [R] CRT  [M] main  [Q] quit")

    force_quit = False
    adjust_mode = False
    step_idx = 2
    cur_rect = cfg["crt_rect"]
    try:
        while proc.poll() is None:
            if adjust_mode and hwnd:
                show_adjust_status(*cur_rect, step_idx)
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if adjust_mode and hwnd:
                    res = handle_adjust_key(
                        ch,
                        hwnd,
                        {
                            "rect": cur_rect,
                            "step_idx": step_idx,
                            "crt_rect": cfg["crt_rect"],
                            "main_rect": cfg["main_rect"],
                        },
                    )
                    cur_rect = res["rect"]
                    step_idx = res["step_idx"]
                    if res.get("saved"):
                        log.info("adjust: saved live_tv_rect=%s to local config", cur_rect)
                        print("\n[live-tv] Saved current rect to crt_config.local.json")
                    if res["quit"]:
                        log.info("user requested quit from adjust mode")
                        force_quit = True
                        break
                    if not res["adjust_mode"]:
                        adjust_mode = False
                        print("\n[live-tv] Controls: [A] adjust window  [R] CRT  [M] main  [Q] quit")
                else:
                    if ch in (b"a", b"A"):
                        if hwnd is None:
                            hwnd = wait_for_vlc_window(proc.pid, 1.0)
                        if hwnd:
                            try:
                                cur_rect = get_rect(hwnd)
                            except Exception:
                                pass
                            show_adjust_mode()
                            adjust_mode = True
                        continue
                    action = decode_key(ch)
                    if action == "quit":
                        log.info("user requested quit")
                        force_quit = True
                        break
                    if hwnd is None:
                        hwnd = wait_for_vlc_window(proc.pid, 1.0)
                    if hwnd and action == "move_crt":
                        move_to_rect(hwnd, cfg["crt_rect"])
                        cur_rect = cfg["crt_rect"]
                        log.info("window moved to crt rect=%s", cfg["crt_rect"])
                        print(f"\n[live-tv] Re-anchored to CRT ({get_rect_text(hwnd)}).")
                    elif hwnd and action == "move_main":
                        move_to_rect(hwnd, cfg["main_rect"])
                        cur_rect = cfg["main_rect"]
                        log.info("window moved to main rect=%s", cfg["main_rect"])
                        print(f"\n[live-tv] Moved to main ({get_rect_text(hwnd)}).")
            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("keyboard interrupt received")
        force_quit = True

    if force_quit and hwnd and cfg.get("restore_main_on_exit", True):
        try:
            move_to_rect(hwnd, cfg["main_rect"])
            log.info("exit restore to main rect=%s", cfg["main_rect"])
            time.sleep(0.1)
        except Exception:
            log.exception("failed to restore window to main on exit")
            pass

    if force_quit and proc.poll() is None:
        log.info("terminating vlc pid=%s", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            log.warning("vlc terminate timeout; killing pid=%s", proc.pid)
            proc.kill()

    rc = proc.poll()
    log.info("=== live_tv session end rc=%s", rc)
    print("[live-tv] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
