# music-adder — Roadmap

**Status:** v0.3.0 SHIPPED 2026-03-20. Tier-1 batches complete. becca-music-adder added. See lessons learned below.

---

## What This Does

Single command that takes a YouTube URL (single track or playlist), downloads it,
identifies and tags each file, and moves it directly into the vault library.
No beets. No database. No match thresholds.

---

## Command Interface

```bash
music-adder add <url|path>   # single track or full playlist, or local folder
music-adder batch <file>     # file of URLs, one per line (# comments ok)
music-adder status           # library file count + review queue count
music-adder review           # show review queue with instructions
```

Local folder path prompts [t/i]: honor existing tags or re-identify via AcoustID.

---

## Core Pipeline

```
music-adder add <url>
        │
        ▼
    yt-dlp download → /vault/media/incoming/<timestamp>/
        │
        ▼
    count audio files in staging dir
        │
        ▼
    FOR EACH FILE (sequential):
        │
        ├─ fpcalc fingerprint → AcoustID API → MusicBrainz recording lookup
        │       → write artist / title / album / tracknumber via mutagen
        │
        ├─ fallback: parse filename ("Artist - Title (Official...)")
        │       → MusicBrainz text search → write tags via mutagen
        │
        ├─ IDENTIFIED → move to /vault/media/music/Artist/Album (Year)/NN Title.ext
        │       • singletons (no album) → /vault/media/music/Non-Album/Artist - Title.ext
        │       • duplicate check: skip if (artist, title) already in library
        │
        └─ UNIDENTIFIED → /vault/media/incoming/_review/
                • write a .note file with filename and timestamp
                • print flashing warning to terminal
        │
        ▼
    clean up empty staging dir
```

---

## File Organization Rules

| Situation | Destination |
|-----------|-------------|
| Artist + Album identified | `/vault/media/music/{Artist}/{Album} ({Year})/{NN} {Title}.ext` |
| Artist + Title, no album | `/vault/media/music/Non-Album/{Artist} - {Title}.ext` |
| Unidentified | `/vault/media/incoming/_review/{staging-dir-name}/` |
| Already in library (same artist+title) | Skip, delete from staging |

Format preference when deduplicating: FLAC > M4A > OPUS > MP3

---

## Review Queue

Unidentified files land in `/vault/media/incoming/_review/` with a `.note` file.

`music-adder review` shows:
- Flashing/highlighted warning banner
- List of items with their filenames and .note contents
- Instructions: open in Picard, save tags, then re-run `music-adder add <local-path>`

`music-adder add` should also accept a **local folder path** as input (skip yt-dlp,
go straight to fingerprint/tag/move). This is how you re-process Picard-tagged files.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `yt-dlp` | Download audio from YouTube |
| `pyacoustid` + `fpcalc` | Audio fingerprinting |
| `musicbrainzngs` | MusicBrainz metadata lookup |
| `mutagen` | Read/write audio file tags |
| `rich` | Terminal output |

No beets. No beets config. No beets database.

---

## Key Paths

| Path | Purpose |
|------|---------|
| `/vault/media/music/` | Library root |
| `/vault/media/incoming/` | Staging area for downloads |
| `/vault/media/incoming/_review/` | Files needing manual metadata |
| `/vault/media/incoming/music_adder.log` | Operation log |

Write to vault as `sg plex` (plex group ownership required).

---

## Lessons Learned (from v1)

- **No beets in the move path.** Beets' match threshold system fought us at every
  turn. 310 items stuck in review for weeks. Once we moved files directly by tag
  they all landed correctly in minutes.

- **Pre-tag before any import attempt.** AcoustID + MusicBrainz identifies ~85-90%
  of tracks. The remaining ~10-15% go to review. That's acceptable.

- **One pipeline, variable iterations.** Single track or 50-track playlist — same
  code, different loop count. No special cases.

- **No watch mode.** Explicit invocation only. Watch mode added complexity with no
  real benefit for this workflow.

- **TTY issues come from wrapping interactive processes.** If we ever need interactive
  terminal behavior, use `os.execvp()` to replace the process entirely.

- **Quiet mode + threshold = silent failures.** Any tool that silently skips files
  without telling you is a liability.

---

## Implementation History

### v0.1.0 (2026-03-19)
1. `cmd_add` — core pipeline (download → tag → move)
2. `cmd_status` — file count in library + review queue count
3. `cmd_review` — display review queue with instructions
4. Local path support in `cmd_add`
5. `cmd_batch` — file of URLs
6. Docs (README + docs/usage.md)

### v0.2.0 (2026-03-19)
- `add <local-path>` prompts [t/i]: honor existing tags or re-identify
- Release picker switched to search_recordings (returns release-group primary-type;
  get_recording_by_id does not)
- Singles deprioritized over albums/EPs
- Expanded title skip words (compilation, best of, warped tour, etc.)

### v0.3.0 (2026-03-20)
- `becca-music-adder` — separate entrypoint for /vault/media/becca_music
  - Same pipeline, different library + incoming paths
  - `MUSIC_ADDER_LIBRARY` / `MUSIC_ADDER_INCOMING` env vars for path overrides
- Fixed Rich markup bug: `[t]`, `[i]`, `[t/i]` in prompts were consumed as markup
  tags and silently dropped — escaped with `\[`

---

## What's Next

- **Tier-2 artists** — remaining gaps from missing.md not yet downloaded
- **music-quality** — scan → analyze → upgrades → report
  - Repo: github.com/lincoln7711/music-quality
  - Roadmap written, not started
