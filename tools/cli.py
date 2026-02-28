"""argparse routing for crt_tools."""

import argparse
from typing import Callable

from tools import audio as audio_tools
from tools import calibration as calibration_tools
from tools import config as config_tools
from tools import display as display_tools
from tools import preset as preset_tools
from tools import prereqs as prereq_tools
from tools import session as session_tools
from tools import windows as window_tools


Handler = Callable[[argparse.Namespace], int]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CRT tools (diagnostics/recovery)")
    sub = p.add_subparsers(dest="category", required=True)

    # ------------------------------------------------------------------ display
    p_display = sub.add_parser("display", help="Display diagnostics and recovery")
    sub_display = p_display.add_subparsers(dest="display_cmd", required=True)

    sub_display.add_parser("dump", help="Dump attached displays and resolve config tokens")

    p_display_modes = sub_display.add_parser("modes", help="List driver-reported modes for a display")
    p_display_modes.add_argument(
        "--display", dest="display_token",
        help="Display token to filter (e.g. crt, SudoMaker). Omit to show all attached displays.",
    )

    sub_display.add_parser("vdd", help="Check SudoMaker VDD presence and attachment status")

    p_display_token = sub_display.add_parser("token", help="Resolve a token string to a display")
    p_display_token.add_argument("token", help="Token substring to resolve")

    p_display_restore = sub_display.add_parser(
        "restore", help="Restore primary display and CRT refresh rate"
    )
    p_display_restore.add_argument(
        "--primary-only", action="store_true", help="Restore primary display only, skip CRT refresh"
    )
    p_display_restore.add_argument("--force", action="store_true", help="Apply without prompt")

    # ------------------------------------------------------------------ config
    p_config = sub.add_parser("config", help="Config diagnostics")
    sub_config = p_config.add_subparsers(dest="config_cmd", required=True)
    sub_config.add_parser("dump", help="Show resolved RE stack config values")
    p_config_check = sub_config.add_parser("check", help="Validate RE stack config against live system")
    p_config_check.add_argument(
        "--wrapper", dest="wrapper_path", metavar="PROFILE",
        help="Validate a wrapper profile JSON instead of the main config",
    )

    # ----------------------------------------------------------------- prereqs
    sub.add_parser("prereqs", help="Check runtime prerequisites")

    # ------------------------------------------------------------------ window
    p_window = sub.add_parser("window", help="Window diagnostics/recovery")
    sub_window = p_window.add_subparsers(dest="window_cmd", required=True)

    p_window_list = sub_window.add_parser("list", help="List visible top-level windows")
    p_window_list.add_argument("--filter", dest="filter_text", help="Title/process substring filter")

    p_window_watch = sub_window.add_parser("watch", help="Watch a window rect live (Ctrl+C to stop)")
    p_window_watch.add_argument("title", help="Window title substring")
    p_window_watch.add_argument(
        "--interval", type=float, default=1.0, help="Poll interval in seconds (default 1.0)"
    )

    p_window_move = sub_window.add_parser("move", help="Move a window to a display or explicit rect")
    p_window_move.add_argument("--title", required=True, help="Window title substring")
    p_window_move.add_argument(
        "--display", dest="display_token",
        help="Display token (e.g. crt, internal, SudoMaker)",
    )
    p_window_move.add_argument(
        "--rect", nargs=4, type=int, metavar=("X", "Y", "W", "H"), help="Explicit target rect",
    )
    p_window_move.add_argument("--force", action="store_true", help="Apply without prompt")

    p_window_restore = sub_window.add_parser(
        "restore", help="Move Moonlight back to idle (restore) position"
    )
    p_window_restore.add_argument("--force", action="store_true", help="Apply without prompt")

    # ------------------------------------------------------------------- audio
    p_audio = sub.add_parser("audio", help="Audio diagnostics/recovery")
    sub_audio = p_audio.add_subparsers(dest="audio_cmd", required=True)

    sub_audio.add_parser("status", help="Show audio backend, devices, and configured tokens")

    p_audio_set = sub_audio.add_parser("set", help="Set default audio device by token")
    p_audio_set.add_argument("token", help="Audio device token substring")
    p_audio_set.add_argument("--force", action="store_true", help="Apply without prompt")

    p_audio_restore = sub_audio.add_parser(
        "restore", help="Restore audio to the configured restore token"
    )
    p_audio_restore.add_argument("--force", action="store_true", help="Apply without prompt")

    # ----------------------------------------------------------------- session
    p_session = sub.add_parser("session", help="Session/log diagnostics")
    sub_session = p_session.add_subparsers(dest="session_cmd", required=True)

    sub_session.add_parser(
        "state", help="Show saved auto-mode session state (runtime/re_stack_state.json)"
    )

    p_session_log = sub_session.add_parser("log", help="Tail the RE stack log")
    p_session_log.add_argument(
        "--lines", type=int, default=30, help="Number of lines to show (default 30)"
    )
    p_session_log.add_argument("--follow", action="store_true", help="Follow log live (Ctrl+C to stop)")

    sub_session.add_parser("processes", help="List RE/Moonlight/session-related processes")

    p_session_flag = sub_session.add_parser("flag", help="Check or clear the wrapper stop flag")
    p_session_flag.add_argument("--clear", action="store_true", help="Remove the flag file")

    # ------------------------------------------------------------------ preset
    p_preset = sub.add_parser("preset", help="CRT resolution preset management")
    sub_preset = p_preset.add_subparsers(dest="preset_cmd", required=True)

    sub_preset.add_parser("list", help="Show all presets, mark active with *")

    p_preset_apply = sub_preset.add_parser("apply", help="Apply a named preset to all config targets")
    p_preset_apply.add_argument("name", help="Preset name (e.g. 1280x960)")

    p_preset_save = sub_preset.add_parser(
        "save", help="Save current config values as a preset (creates or updates)"
    )
    p_preset_save.add_argument(
        "--name", dest="preset_name", metavar="NAME",
        help="Preset name to save into (default: currently active preset)",
    )

    # --------------------------------------------------------------- calibrate
    p_cal = sub.add_parser("calibrate", help="Moonlight window calibration")
    sub_cal = p_cal.add_subparsers(dest="calibrate_cmd", required=True)

    sub_cal.add_parser(
        "adjust", help="Interactive window position/size adjuster (Moonlight must be open)"
    )
    sub_cal.add_parser("set-crt", help="Save current Moonlight position as CRT rect")
    sub_cal.add_parser("set-idle", help="Save current Moonlight position as idle (restore) rect")

    p_cal_offsets = sub_cal.add_parser(
        "set-crt-offsets",
        help="Compute and save CRT calibration as relative offsets from live CRT display bounds",
    )
    p_cal_offsets.add_argument(
        "--from-current", action="store_true",
        help="Use current Moonlight position without opening the adjuster",
    )

    p_cal_overlap = sub_cal.add_parser("overlap", help="Check window/display overlap ratio")
    p_cal_overlap.add_argument("--window", required=True, help="Window title fragment")
    p_cal_overlap.add_argument("--display", required=True, dest="display_token", help="Display token")
    p_cal_overlap.add_argument(
        "--threshold", type=float, default=0.95,
        help="Minimum acceptable overlap ratio (default 0.95)",
    )

    return p


def _dispatch(args: argparse.Namespace) -> int:
    if args.category == "display":
        if args.display_cmd == "dump":
            return display_tools.print_display_dump(display_tools.display_dump())
        if args.display_cmd == "modes":
            return display_tools.print_display_modes(
                display_tools.display_modes(getattr(args, "display_token", None))
            )
        if args.display_cmd == "vdd":
            return display_tools.print_display_vdd(display_tools.display_vdd())
        if args.display_cmd == "token":
            return display_tools.print_display_token(display_tools.display_token_resolve(args.token))
        if args.display_cmd == "restore":
            return display_tools.display_restore(
                primary_only=args.primary_only, force=args.force
            )

    if args.category == "config":
        if args.config_cmd == "dump":
            return config_tools.print_config_dump(config_tools.config_dump())
        if args.config_cmd == "check":
            if getattr(args, "wrapper_path", None):
                return config_tools.print_config_check_wrapper(
                    config_tools.config_check_wrapper(args.wrapper_path)
                )
            return config_tools.print_config_check(config_tools.config_check())

    if args.category == "prereqs":
        return prereq_tools.print_prereqs_check(prereq_tools.prereqs_check())

    if args.category == "window":
        if args.window_cmd == "list":
            return window_tools.print_window_list(window_tools.window_list(args.filter_text))
        if args.window_cmd == "watch":
            return window_tools.window_watch(args.title, interval=args.interval)
        if args.window_cmd == "move":
            rect = tuple(args.rect) if args.rect else None
            return window_tools.window_move(
                title=args.title,
                display_token=args.display_token,
                rect=rect,
                force=args.force,
            )
        if args.window_cmd == "restore":
            return window_tools.window_restore(force=args.force)

    if args.category == "audio":
        if args.audio_cmd == "status":
            return audio_tools.print_audio_status(audio_tools.audio_status())
        if args.audio_cmd == "set":
            return audio_tools.audio_set(args.token, force=args.force)
        if args.audio_cmd == "restore":
            return audio_tools.audio_restore(force=args.force)

    if args.category == "session":
        if args.session_cmd == "state":
            return session_tools.session_state()
        if args.session_cmd == "log":
            return session_tools.session_log(lines=args.lines, follow=args.follow)
        if args.session_cmd == "processes":
            return session_tools.session_processes()
        if args.session_cmd == "flag":
            return session_tools.session_flag(clear=args.clear)

    if args.category == "preset":
        if args.preset_cmd == "list":
            return preset_tools.print_preset_list(preset_tools.preset_list())
        if args.preset_cmd == "apply":
            return preset_tools.print_preset_apply(preset_tools.preset_apply(args.name))
        if args.preset_cmd == "save":
            name = args.preset_name
            if name is None:
                data = preset_tools.preset_list()
                if not data.get("ok"):
                    print(f"[preset] FAIL: cannot determine active preset: {data.get('error')}")
                    return 1
                name = data.get("active")
                if not name:
                    print("[preset] FAIL: no active preset set — use --name to specify one")
                    return 1
            return preset_tools.print_preset_save(preset_tools.preset_save(name))

    if args.category == "calibrate":
        if args.calibrate_cmd == "adjust":
            return calibration_tools.calibrate_adjust()
        if args.calibrate_cmd == "set-crt":
            return calibration_tools.calibrate_set_crt()
        if args.calibrate_cmd == "set-idle":
            return calibration_tools.calibrate_set_idle()
        if args.calibrate_cmd == "set-crt-offsets":
            return calibration_tools.calibrate_set_crt_offsets(
                from_current=args.from_current
            )
        if args.calibrate_cmd == "overlap":
            return calibration_tools.calibrate_overlap(
                window_title=args.window,
                display_token=args.display_token,
                threshold=args.threshold,
            )

    print(f"[tools] FAIL: {args.category} -- unhandled command")
    return 2


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("\n[tools] Interrupted.")
        return 130
    except Exception as e:
        print(f"[tools] FAIL: {args.category} -- {e}")
        return 1
