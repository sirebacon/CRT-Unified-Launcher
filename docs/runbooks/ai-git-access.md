# AI Git Access Runbook (CRT-Unified-Launcher)

This document defines the Git setup for AI agents working in:

`D:\Emulators\CRT-Unified-Launcher`

## Goal

Allow an AI agent to run Git commands for this repo with repo-local credentials, without depending on user profile SSH setup.

## Current Known Constraint

Some sandboxed AI sessions can fail remote Git commands with:

- `sh.exe: ... couldn't create signal pipe, Win32 error 5`

If that happens, the issue is session runtime permissions, not repo auth. In that case, AI can still edit and commit locally, and the human runs `git push`.

## Repo-Local SSH Auth Setup

This repo uses a local key under `.codex/` and repo-local `core.sshCommand`.

### 1) Required files

- Private key: `D:\Emulators\CRT-Unified-Launcher\.codex\id_ed25519`
- Public key: `D:\Emulators\CRT-Unified-Launcher\.codex\id_ed25519.pub`
- Known hosts file (auto-managed): `D:\Emulators\CRT-Unified-Launcher\.codex\known_hosts`

`.codex/` is ignored by Git via `.gitignore`.

### 2) Repo-local Git config

Ensure this is set:

```powershell
git -C D:\Emulators\CRT-Unified-Launcher config --get core.sshCommand
```

Expected value:

```text
ssh -i D:/Emulators/CRT-Unified-Launcher/.codex/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=D:/Emulators/CRT-Unified-Launcher/.codex/known_hosts -o StrictHostKeyChecking=accept-new
```

If missing, set it:

```powershell
git -C D:\Emulators\CRT-Unified-Launcher config core.sshCommand "ssh -i D:/Emulators/CRT-Unified-Launcher/.codex/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=D:/Emulators/CRT-Unified-Launcher/.codex/known_hosts -o StrictHostKeyChecking=accept-new"
```

### 3) GitHub deploy key

Add the public key from `.codex\id_ed25519.pub` to repo deploy keys:

- Repo: `sirebacon/CRT-Unified-Launcher`
- Settings -> Deploy keys -> Add deploy key
- Enable write access

## Verification Commands

Run from any shell:

```powershell
git -C D:\Emulators\CRT-Unified-Launcher remote -v
git -C D:\Emulators\CRT-Unified-Launcher ls-remote origin
git -C D:\Emulators\CRT-Unified-Launcher pull --ff-only origin main
```

Expected healthy pull output includes:

- `From github.com:sirebacon/CRT-Unified-Launcher`
- `Already up to date.` (if no upstream changes)

## If Remote Commands Fail In AI Session

If AI gets runtime sandbox errors (especially `Win32 error 5` from `sh.exe`):

1. AI performs edits and local commits only.
2. Human runs network Git commands locally:
   - `git -C D:\Emulators\CRT-Unified-Launcher pull --ff-only origin main`
   - `git -C D:\Emulators\CRT-Unified-Launcher push -v origin main`

## New Session Checklist (for any AI agent)

1. Confirm repo path is exactly `D:\Emulators\CRT-Unified-Launcher`.
2. Check `git status -sb`.
3. Check `core.sshCommand` value.
4. Try `git ls-remote origin`.
5. If runtime error occurs, switch to "AI commits locally, human pushes" workflow.
