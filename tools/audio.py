"""Audio diagnostics/recovery commands for crt_tools (Phase 2 scaffold)."""

import subprocess
from typing import Any, Dict, List

from session.audio import audio_tool_status, set_default_audio_best_effort
from session.re_config import RE_AUDIO_DEVICE_TOKEN, RESTORE_AUDIO_DEVICE_TOKEN


def _run_powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
    )


def _list_playback_devices() -> List[str]:
    ps = r"""
if (-not (Get-Module -ListAvailable -Name AudioDeviceCmdlets)) { exit 0 }
Import-Module AudioDeviceCmdlets -ErrorAction Stop
Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' } | ForEach-Object { $_.Name }
"""
    proc = _run_powershell(ps)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _default_playback_device() -> str:
    ps = r"""
if (-not (Get-Module -ListAvailable -Name AudioDeviceCmdlets)) { exit 0 }
Import-Module AudioDeviceCmdlets -ErrorAction Stop
$d = Get-AudioDevice -Playback
if ($null -ne $d) { $d.Name }
"""
    proc = _run_powershell(ps)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def audio_status() -> Dict[str, Any]:
    backend = audio_tool_status()
    devices = _list_playback_devices() if backend == "audiodevicecmdlets" else []
    return {
        "backend": backend,
        "devices": devices,
        "default_playback": _default_playback_device() if backend == "audiodevicecmdlets" else "",
        "re_token": RE_AUDIO_DEVICE_TOKEN,
        "restore_token": RESTORE_AUDIO_DEVICE_TOKEN,
    }


def print_audio_status(data: Dict[str, Any]) -> int:
    print("Audio status")
    print(f"  backend              : {data['backend']}")
    if data.get("default_playback"):
        print(f"  default playback     : {data['default_playback']}")
    print(f"  re_device_token      : {data['re_token']}")
    print(f"  restore_device_token : {data['restore_token']}")
    devices = data.get("devices") or []
    if devices:
        print()
        print("Playback devices:")
        for i, d in enumerate(devices, start=1):
            print(f"  [{i}] {d}")
    return 0


def audio_set(token: str, force: bool = False) -> int:
    print(f"Target audio token: {token}")
    if not force:
        ans = input("Set default audio device now? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("[tools] PASS: audio set -- cancelled")
            return 0
    ok = set_default_audio_best_effort(token)
    if ok:
        print("[tools] PASS: audio set")
        return 0
    print("[tools] FAIL: audio set")
    return 1


def audio_restore(force: bool = False) -> int:
    return audio_set(RESTORE_AUDIO_DEVICE_TOKEN, force=force)
