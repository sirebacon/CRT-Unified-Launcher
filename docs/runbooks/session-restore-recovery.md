# Session Restore Recovery Runbook

Use this if session cleanup fails to restore one or more patched files.

## Expected behavior

When restore fails, the session tool should:
- keep attempting remaining files
- print each failed source/destination path
- print manual copy instructions

## Manual recovery steps

1. Identify backup directory from session output.
2. For each failed file:
- copy backup file to original target path
- verify file contents match expected defaults
3. Remove session lockfile if no session process is running:
- expected path: `.session.lock` (project root, next to `crt_station.py`)
4. Remove stale stop flag if present:
- `wrapper_stop_enforce.flag`

## PowerShell example

```powershell
Copy-Item "C:\path\to\backup\Emulators.xml" "D:\Emulators\LaunchBox\Data\Emulators.xml" -Force
```

## Post-recovery validation

1. Launch LaunchBox and verify emulator paths/settings are normal.
2. Run session dry-run validation before next live session.
3. If restore repeatedly fails on same file, check file locks and permissions.

