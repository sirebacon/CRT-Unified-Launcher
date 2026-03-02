"""YouTube telemetry snapshot engine (single writer, copy-on-publish)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TelemetryConfig:
    core_poll_sec: float = 0.25
    advanced_poll_sec: float = 1.0
    core_timeout_sec: float = 0.20
    advanced_timeout_sec: float = 0.25
    max_calls_per_sec: int = 20
    stale_after_sec: float = 5.0


class TelemetryEngine:
    """Polls mpv properties with bounded cadence/backoff and publishes snapshots."""

    def __init__(self, ipc, is_playlist: bool, cfg: Optional[TelemetryConfig] = None):
        self.ipc = ipc
        self.is_playlist = is_playlist
        self.cfg = cfg or TelemetryConfig()
        self._values: Dict[str, Any] = {}
        self._value_ts: Dict[str, float] = {}
        self._snapshot: Dict[str, Any] = {
            "health": "ok",
            "state_label": "N/A",
            "time_label": "N/A / N/A",
            "volume_label": "Vol N/A",
            "mute_label": "Mute N/A",
            "queue_label": "Item N/A",
            "zoom_label": "Zoom OFF",
            "advanced": {},
            "ipc_mode": "write-only",
        }
        self._last_core = 0.0
        self._last_secondary = 0.0
        self._last_adv = 0.0
        self._window_start = 0.0
        self._window_calls = 0
        self._fail_streak = 0
        self._ok_streak = 0
        self._last_error = ""

    def _format_time(self, v: Optional[float]) -> str:
        if v is None:
            return "N/A"
        try:
            s = int(max(0, v))
        except Exception:
            return "N/A"
        m, s = divmod(s, 60)
        return f"{m}:{s:02d}"

    def _budget_reset_if_needed(self, now: float) -> None:
        if (now - self._window_start) >= 1.0:
            self._window_start = now
            self._window_calls = 0

    def _can_call(self, now: float) -> bool:
        self._budget_reset_if_needed(now)
        return self._window_calls < self.cfg.max_calls_per_sec

    def _get(self, name: str, timeout: float, now: float):
        if not self._can_call(now):
            return None, False
        self._window_calls += 1
        try:
            val = self.ipc.get_property(name, timeout=timeout)
            if val is not None:
                self._values[name] = val
                self._value_ts[name] = now
                return val, True
            return None, False
        except Exception as e:
            self._last_error = str(e)
            return None, False

    def _fresh(self, name: str, now: float):
        ts = self._value_ts.get(name)
        if ts is None:
            return None
        if (now - ts) > self.cfg.stale_after_sec:
            return None
        return self._values.get(name)

    def _update_health(self, read_attempts: int, read_failures: int) -> None:
        if read_attempts <= 0:
            return
        if read_failures > 0:
            self._fail_streak += 1
            self._ok_streak = 0
        else:
            self._ok_streak += 1
            self._fail_streak = 0

        if self._fail_streak >= 6:
            self._snapshot["health"] = "reconnecting"
        elif self._fail_streak >= 3:
            self._snapshot["health"] = "degraded"
        elif self._ok_streak >= 3:
            self._snapshot["health"] = "ok"

    def _core_interval(self) -> float:
        health = self._snapshot.get("health", "ok")
        if health == "reconnecting":
            return self.cfg.core_poll_sec * 4
        if health == "degraded":
            return self.cfg.core_poll_sec * 2
        return self.cfg.core_poll_sec

    def _build_snapshot(self, now: float, zoom_locked: bool, zoom_preset_name: Optional[str]) -> None:
        pause = self._fresh("pause", now)
        state = "Paused" if pause is True else ("Playing" if pause is False else "N/A")
        tpos = self._fresh("time-pos", now)
        dur = self._fresh("duration", now)
        vol = self._fresh("volume", now)
        mute = self._fresh("mute", now)
        ppos = self._fresh("playlist-pos", now)
        pcount = self._fresh("playlist-count", now)

        self._snapshot["state_label"] = state
        self._snapshot["time_label"] = f"{self._format_time(tpos)} / {self._format_time(dur)}"
        self._snapshot["volume_label"] = f"Vol {int(vol):d}" if vol is not None else "Vol N/A"
        if mute is None:
            self._snapshot["mute_label"] = "Mute N/A"
        else:
            self._snapshot["mute_label"] = "Mute On" if bool(mute) else "Mute Off"

        if self.is_playlist and pcount is not None:
            disp_pos = (int(ppos) + 1) if ppos is not None else None
            if disp_pos is None:
                self._snapshot["queue_label"] = f"Item N/A / {int(pcount)}"
            else:
                self._snapshot["queue_label"] = f"Item {disp_pos} / {int(pcount)}"
        elif self.is_playlist:
            self._snapshot["queue_label"] = "Item N/A"
        else:
            self._snapshot["queue_label"] = "Single video"

        if zoom_locked and zoom_preset_name:
            self._snapshot["zoom_label"] = f"Zoom {zoom_preset_name}"
        else:
            self._snapshot["zoom_label"] = "Zoom OFF"

    def set_ipc_mode(self, mode: str) -> None:
        self._snapshot["ipc_mode"] = mode or "N/A"
        if self._snapshot["ipc_mode"] == "offline":
            self._snapshot["health"] = "reconnecting"

    def tick(self, now: float, show_advanced: bool, zoom_locked: bool, zoom_preset_name: Optional[str]) -> Dict[str, Any]:
        attempts = 0
        failures = 0
        core_interval = self._core_interval()

        if self._snapshot.get("ipc_mode") != "duplex":
            # In write-only mode, property reads are not reliable by design.
            self._snapshot["health"] = "ok"
            self._build_snapshot(now, zoom_locked, zoom_preset_name)
            return dict(self._snapshot)

        if (now - self._last_core) >= core_interval:
            self._last_core = now
            for key in ("pause", "time-pos", "duration"):
                attempts += 1
                _, ok = self._get(key, self.cfg.core_timeout_sec, now)
                if not ok:
                    failures += 1

        if (now - self._last_secondary) >= 0.50:
            self._last_secondary = now
            for key in ("volume", "mute"):
                attempts += 1
                _, ok = self._get(key, self.cfg.core_timeout_sec, now)
                if not ok:
                    failures += 1
            if self.is_playlist:
                for key in ("playlist-pos", "playlist-count"):
                    attempts += 1
                    _, ok = self._get(key, self.cfg.core_timeout_sec, now)
                    if not ok:
                        failures += 1

        if show_advanced and (now - self._last_adv) >= self.cfg.advanced_poll_sec:
            self._last_adv = now
            advanced = {}
            for key in (
                "cache-buffering-state",
                "demuxer-cache-duration",
                "speed",
                "video-codec",
                "video-params/w",
                "video-params/h",
                "container-fps",
                "estimated-vf-fps",
                "audio-codec-name",
                "audio-params/channel-count",
                "audio-params/samplerate",
                "hwdec-current",
            ):
                attempts += 1
                val, ok = self._get(key, self.cfg.advanced_timeout_sec, now)
                if not ok:
                    failures += 1
                advanced[key] = val
            self._snapshot["advanced"] = advanced

        self._update_health(attempts, failures)
        self._build_snapshot(now, zoom_locked, zoom_preset_name)
        return dict(self._snapshot)
