# Window Tools

Module: `tools/windows.py` (proposed) | Entry: `python crt_tools.py window <subcommand>`

**Status: Proposed.** All tools in this group are planned. The legacy `tools/inspectRetro.py`
script covers some of this ground but is hardcoded to Dolphin -- see `window list` for the
generalized replacement.

---

## window list

```
python crt_tools.py window list
python crt_tools.py window list --filter "moonlight"
python crt_tools.py window list --filter "resident evil"
```

Lists all currently visible top-level windows. For each window shows:

- HWND (hex)
- Window title
- Class name
- Position and size `(x, y, w, h)`
- Whether it is maximized, minimized, or fullscreen (WS_CAPTION check + monitor-fill check)
- PID and process name

`--filter` is a case-insensitive substring match against the window title. Without a filter,
all visible windows are listed.

**Sample output:**

```
HWND      Title                              Class            x      y      w     h      State
0x001C04  Moonlight                          SDL_app         69     99   1598   851  normal
0x003A18  RESIDENT EVIL                      re_main_wnd    100    120   1280   960  normal
0x002B44  Display Settings                   ApplicationFr    0      0    900   800  normal
```

**Use for:**
- Finding the exact title substring to use in `re_stack_config.json` `_gameplay_title`
- Confirming a window is on the expected display (by comparing `x,y` against display `position`)
- Checking whether a window was moved by a previous command

**Backing function:** `session/window_utils.py` -- `enum_windows()`, `get_rect()`,
`is_window_fullscreen()`

**Replaces:** `tools/inspectRetro.py` (hardcoded to Dolphin, not extensible)

---

## window watch

```
python crt_tools.py window watch "moonlight"
python crt_tools.py window watch "RESIDENT EVIL"
```

Polls for a window matching the given title fragment and prints its rect and state once per
second. Continues until the window closes or `Ctrl+C`.

Useful for:
- Verifying that the enforcement loop is actually moving the window to the correct rect
- Watching a window's position in real time during a calibration session
- Confirming `move_moonlight_to_crt` landed where expected

**Sample output:**

```
Watching: "moonlight"
  [00:00]  HWND=0x001C04  x=69  y=99  w=1598  h=851  (normal)
  [00:01]  HWND=0x001C04  x=69  y=99  w=1598  h=851  (normal)
  [00:04]  HWND=0x001C04  x=1170  y=-80  w=1410  h=1110  (moved to CRT)
  ...
```

---

## window move

```
python crt_tools.py window move --title "moonlight" --display crt
python crt_tools.py window move --title "moonlight" --rect 1170 -80 1410 1110
python crt_tools.py window move --title "moonlight" --display crt --force
```

Moves the window matching `--title` to either a named display or an explicit rect. Without
`--force`, prints the planned move and prompts for confirmation.

`--display` accepts a token (e.g. `crt`, `internal`, `sudomaker`). The tool resolves the token to
a live display rect via `find_display_by_token()` -- the window is moved to fill that display.

`--rect x y w h` uses an explicit rect instead. Useful for testing calibration values before
writing them to config.

**Backing function:** `session/window_utils.py` -- `find_window()`, `move_window()`

**Read-back:** After applying the move, `window move` reads the window rect back and prints
the confirmed position. Use `window watch` to monitor the rect over time if the window might
drift (e.g. due to an enforcement loop running elsewhere).

---

## window restore

```
python crt_tools.py window restore
python crt_tools.py window restore --force
```

Moves all known managed windows back to their idle/restore positions as defined in
`re_stack_config.json`. Currently covers the Moonlight window (`idle_rect`).

Without `--force`, prints what will be moved and prompts for confirmation.

**Use for:** recovery after a session left a window stranded on the wrong display.

---

## Legacy: tools/inspectRetro.py

```
python tools\inspectRetro.py
```

The original window inspector. Enumerates the Dolphin window specifically -- hardcoded to look
for the Dolphin process and window class. Useful for finding Dolphin window details, but not
generalized to other apps.

For any non-Dolphin inspection use `window list` (once implemented).

**Status:** Exists. Not planned for removal -- kept as a quick Dolphin-specific tool.
