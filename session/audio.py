"""Audio switching helpers: PowerShell runner, device selection, tool status."""

import subprocess
from typing import Optional


def _run_powershell(script: str, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def audio_tool_status() -> str:
    """Return which audio-switching backend is available: 'audiodevicecmdlets', 'nircmd', or 'none'."""
    ps = """
if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) { Write-Output "AudioDeviceCmdlets"; exit 0 }
$nircmd = Get-Command nircmd.exe -ErrorAction SilentlyContinue
if ($null -ne $nircmd) { Write-Output "nircmd"; exit 0 }
Write-Output "none"
"""
    proc = _run_powershell(ps)
    return (proc.stdout or "").strip().lower() or "none"


def set_default_audio_best_effort(name_token: str) -> bool:
    """Set the default playback device to the first device matching name_token.

    Tries AudioDeviceCmdlets first, falls back to nircmd. Logs a warning if
    neither backend is available and returns False, but the caller may continue.
    """
    ps = rf"""
$ErrorActionPreference = "Stop"
$token = "{name_token.replace('"', '""')}"
if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) {{
    Import-Module AudioDeviceCmdlets -ErrorAction Stop
    $device = Get-AudioDevice -List | Where-Object {{
        $_.Type -eq "Playback" -and $_.Name -like "*$token*"
    }} | Select-Object -First 1
    if ($null -eq $device) {{
        Write-Output "NOT_FOUND"
        exit 2
    }}
    Set-AudioDevice -Index $device.Index | Out-Null
    Write-Output "OK"
    exit 0
}}

# Fallback path: nircmd if available.
$nircmd = Get-Command nircmd.exe -ErrorAction SilentlyContinue
if ($null -ne $nircmd) {{
    & $nircmd.Source setdefaultsounddevice $token 0
    & $nircmd.Source setdefaultsounddevice $token 1
    & $nircmd.Source setdefaultsounddevice $token 2
    Write-Output "OK"
    exit 0
}}

Write-Output "AUDIO_TOOL_MISSING"
exit 3
"""
    proc = _run_powershell(ps)
    out = (proc.stdout or "").strip()
    if proc.returncode == 0:
        print(f"[re-stack] Default audio set: {name_token}")
        return True
    if "NOT_FOUND" in out:
        print(f"[re-stack] Audio device not found for token: {name_token}")
        return False
    if "AUDIO_TOOL_MISSING" in out:
        print(
            "[re-stack] Could not set default audio automatically. "
            "Install AudioDeviceCmdlets or nircmd.exe."
        )
        return False
    err = (proc.stderr or "").strip()
    if err:
        print(f"[re-stack] Audio switch error: {err}")
    return False
