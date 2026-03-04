# Change Impact Checklist

Use this as a minimum regression gate after editing a subsystem.

## A) Menu and Launch Routing (`crt_station.py`, launchers)

Run:

```powershell
python crt_station.py
```

Verify:

- Menu options still open the expected modes.
- `q`/`9` exits cleanly.
- Ctrl+C in menu returns safely without orphan behavior.

## B) Gaming Session (`launch_session.py`, `session/manifest.py`, `session/watcher.py`, `session/patcher.py`, `session/patches/*`)

Run:

```powershell
python validate_session.py --manifest profiles/gaming-manifest.json
```

Then do one live smoke run:

```powershell
python launch_session.py --manifest profiles/gaming-manifest.json --debug
```

Verify:

- Backup -> patch -> restore works with no persistent config drift.
- Single Ctrl+C performs soft stop (window restore behavior).
- Double Ctrl+C (within window) performs full shutdown and cleanup.
- `.session.lock` is removed on exit.

## C) Media Orchestrator (`youtube/launcher.py`, `youtube/*`)

Run:

```powershell
python launch_youtube.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Verify:

- `runtime/youtube.log` and `runtime/mpv.log` are recreated each run.
- mpv window lands on expected CRT rect.
- Basic controls (`Space`, arrows, `q`) still work.

## D) Provider Registry or Provider Contracts (`media/providers/base.py`, `registry.py`)

Run:

```powershell
python -c "from youtube.config import load_config; from media.providers import registry as r; c=load_config(); r.setup(c); print([p.name() for p in r.all_providers()])"
```

Verify:

- Provider list loads in expected order.
- No provider import error silently removed required providers.

## E) Tier 2 Providers (Aniwatch/WCO)

Aniwatch smoke:

```powershell
python launch_youtube.py --url "<known-working-hianime-episode-url>"
```

WCO smoke:

```powershell
python launch_youtube.py --url "<known-working-wco-episode-url>"
```

Verify:

- Aniwatch resolver subprocess returns and playback starts.
- WCO path serves via localhost proxy and seeking works.
- For WCO episode pages with valid series metadata, next/prev metadata is populated.

## F) Tier 3 Browser Playback (`media/browser_launcher.py`, `media/providers/kisscartoon.py`)

Run:

```powershell
python launch_youtube.py --url "<tier3-provider-url>"
```

Verify:

- Browser launches with isolated profile behavior.
- Window is placed on CRT rect without moving personal browser windows.
- Exiting browser returns control to launcher without hanging.

## G) RE Stack (`launch_resident_evil_stack.py`, `session/re_*`, `session/display_api.py`, `session/moonlight.py`, `session/audio.py`)

Run:

```powershell
python launch_resident_evil_stack.py inspect
python launch_resident_evil_stack.py manual --game re1
```

Verify:

- Inspect reports expected prerequisites.
- Manual mode flow can complete and restore path returns audio/window state.
- Recovery path still works:

```powershell
python launch_resident_evil_stack.py restore
```

## H) CRT Tools (`tools/*`, `crt_tools.py`)

Run:

```powershell
python crt_tools.py prereqs
python crt_tools.py config check
python crt_tools.py display dump
python crt_tools.py audio status
```

Verify:

- Subcommand routing is intact.
- Tools fail with actionable errors (not stack traces) on missing dependencies.

## I) Config Schema Changes (`crt_config.json`, `re_stack_config.json`, `profiles/*.json`)

After changing config keys:

1. Update the relevant docs (`docs/configuration.md` and any related runbook).
2. Verify callers use defaults for missing keys.
3. Test at least one real flow for each affected caller (gaming, media, RE, tools).

## J) Logging or Runtime File Path Changes

Verify all affected logs are still written under `runtime/` and rotated/overwritten as intended:

- `runtime/youtube.log`
- `runtime/mpv.log`
- `runtime/re_stack.log`

If a path moved, update runbooks that reference it.
