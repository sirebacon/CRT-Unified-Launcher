# tools/media.py — Media Progress and History Diagnostics

Diagnostic commands for inspecting the Continue Watching progress file and the unified
watch history file without opening a JSON editor.

---

## Commands

### `media progress`

```
python crt_tools.py media progress
```

Reads `runtime/media_progress.json` and prints all stored entries in a formatted table.
In-progress items are shown first (sorted by `last_watched_at` descending), then
completed/skipped items.

**Sample output:**

```
=== Media Progress  (2 in-progress, 3 done) ===

In-progress:
  ▶ [hia] Super Demon Hero Wataru  [Episode 3 - Fierce Battle]  ep 3
       12:44/24:01  53%  2026-03-04 22:10  key=hianime:series:super-demon-hero-wataru-4045
  ▶ [you] Cool YouTube Video
       4:12/10:30  40%  2026-03-03 18:44  key=youtube:video:dQw4w9WgXcQ

Done (completed/skipped):
  ✓ [hia] Another Show  [Episode 12]  ep 12
       22:11/22:30  98%  2026-03-02 21:05  key=hianime:series:another-show-1234
  » [hia] Show I Skipped  [Episode 2]  ep 2
       3:00/22:30  13%  2026-03-01 14:22  key=hianime:series:skipped-show-999
  ✓ [you] Another Video
       9:55/10:00  99%  2026-02-28 19:30  key=youtube:video:abc456
```

**Columns:**

| Column | Description |
|--------|-------------|
| Badge `▶/✓/»` | `▶` in-progress, `✓` completed, `»` skipped |
| `[prov]` | Provider abbreviated to 3 chars: `hia` = HiAnime, `you` = YouTube |
| Title | Up to 40 chars of the title, plus `[sub_title]` and `ep N` if available |
| `pos/dur` | Resume position and total duration in `M:SS` format |
| `pct%` | Percent watched |
| Timestamp | `last_watched_at` truncated to `YYYY-MM-DD HH:MM` |
| `key=...` | Full `continue_key` for cross-referencing log entries |

Returns exit code 0 even when the file does not exist yet (prints a notice instead).

---

### `media history`

```
python crt_tools.py media history
```

Reads `runtime/media_history.json` and prints:

1. Total entry count
2. Breakdown by provider
3. Breakdown by outcome (with badge)
4. The 15 most recent entries

**Sample output:**

```
=== Watch History  (47 total entries) ===

By provider:
  youtube       32
  hianime       15

By outcome:
  ✓ completed        28
  ▶ in_progress      12
  » skipped           7

Most recent 15 entries:
  ▶ [you] Cool YouTube Video                                    40%  2026-03-03
  ✓ [hia] Another Show                                         100%  2026-03-02
  ...
```

Returns exit code 0 when the file does not exist (prints a notice).

---

## When to Use These Commands

| Scenario | Command |
|----------|---------|
| Resume position looks wrong | `media progress` — check `pos` and `key` for the item |
| Item won't leave Continue lane | `media progress` — confirm `playback_outcome` is still `in_progress` |
| History shows wrong provider or outcome | `media history` — inspect breakdown + recent rows |
| Want to see the raw JSON | Open `runtime/media_progress.json` or `runtime/media_history.json` directly |
| Want to remove a progress entry | Continue lane → `R<N>`, or delete the entry from the JSON manually |
| Want to clear all history | Continue lane → `H` → `C` |

---

## Underlying Files

| File | Description | Cap |
|------|-------------|-----|
| `runtime/media_progress.json` | Continue Watching entries | 40 items (20 in-prog + 20 done) |
| `runtime/media_history.json` | Unified watch history | 500 entries |

Both files use atomic writes (write to `.tmp` then `os.replace()`) so they are never left
in a corrupt half-written state after a hard kill.

---

## Module

```
tools/media.py
  media_progress() -> int     # formats and prints progress entries
  media_history()  -> int     # formats and prints history stats + recent entries
```

No external dependencies beyond the standard library and the project's own
`youtube/progress.py` and `youtube/media_history.py` runtime files.

---

## Related

- `docs/runbooks/media-history-continue-watching-plan.md` — full design and phase notes
- `docs/youtube-on-crt.md` — Continue Watching UX, config knobs, key reference
