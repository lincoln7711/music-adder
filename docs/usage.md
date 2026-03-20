# music-adder — Usage Guide

## Overview

`music-adder` is a three-command tool for downloading music from YouTube and adding it to a vault library. Each file is identified by audio fingerprint (AcoustID → MusicBrainz) and moved directly using its tags. Files that can't be identified go to a review queue.

---

## Commands

### `add` — Single URL or local folder

```bash
music-adder add "https://www.youtube.com/playlist?list=..."
music-adder add "https://www.youtube.com/watch?v=..."
music-adder add /vault/media/incoming/_review/20260319_123456/
```

Accepts:
- A YouTube URL (single video or full playlist — both work the same way)
- A local folder path (skips download, re-processes files already on disk)

The local path option is how you re-process files from the review queue after tagging them manually in MusicBrainz Picard.

---

### `batch` — Multiple URLs from a file

```bash
music-adder batch ~/projects/plex-music-collection/ytdlp_tier1_playlists.txt

# With color preserved through tee:
FORCE_COLOR=1 music-adder batch ~/projects/plex-music-collection/artist_batch.txt 2>&1 | tee ~/run.log
```

The batch file format:
- One URL per line
- Lines starting with `#` are ignored (use for artist/album labels)
- Blank lines are ignored

Example batch file:
```
# The Offspring
https://www.youtube.com/playlist?list=PLcZMZxR9uxC86NE7jaibvYapgUzSPIv5Z

# Atreyu — Suicide Notes and Butterfly Kisses
https://www.youtube.com/playlist?list=PL5N7LP2xFA03HdHUBGRVE5vRp5IPnRkpK
```

---

### `status` — Library and queue overview

```bash
music-adder status
```

Shows total track count in the library and how many files are waiting in the review queue.

---

### `review` — Review queue

```bash
music-adder review
```

Shows all files that couldn't be identified, with their `.note` files containing instructions. Unidentified files land in `/vault/media/incoming/_review/<staging-dir>/`.

**To fix a review item:**
1. Open the file in MusicBrainz Picard
2. Look up and save the correct tags
3. Re-run: `music-adder add /vault/media/incoming/_review/<staging-dir>/`

---

## Pipeline (what happens per file)

```
Download (yt-dlp) → staging dir
    ↓
Duration filter: < 60s or > 20min → deleted (intros, DJ mixes)
    ↓
AcoustID fingerprint (fpcalc) → MusicBrainz recording lookup
    ↓ (if no match)
Filename parse ("Artist - Title") → MusicBrainz text search
    ↓ (if no artist parseable from filename → review queue)
Write tags via mutagen (artist, title, album, albumartist, year)
    ↓
Move to library:
    Artist + Album  →  /vault/media/music/{Artist}/{Album} ({Year})/{Title}.ext
    No album        →  /vault/media/music/Non-Album/{Artist} - {Title}.ext
    Already exists  →  skip (delete staging copy)
    Unidentified    →  /vault/media/incoming/_review/
```

---

## File organisation

| Situation | Destination |
|-----------|-------------|
| Artist + Album identified | `/vault/media/music/{Artist}/{Album} ({Year})/{Title}.ext` |
| Artist + Title, no album | `/vault/media/music/Non-Album/{Artist} - {Title}.ext` |
| Already in library (same path) | Skipped, staging copy deleted |
| Unidentified | `/vault/media/incoming/_review/{staging-dir}/` |

Format preference when a file already exists at the destination: FLAC > M4A > OPUS > MP3.

---

## Configuration

Shared config: `~/.config/music-tools/config.yaml`

```yaml
library:
  path: /vault/media/music        # root of the music vault

acoustid:
  api_key: YOUR_KEY_HERE          # https://acoustid.org/api-key
```

The AcoustID key can also be set via environment variable:
```bash
export ACOUSTID_KEY=YOUR_KEY_HERE
```

---

## Known limitations

- **Fan playlists**: Fan-uploaded full-album playlists sometimes include non-album videos (intros, live clips from other shows, algorithm-suggested tracks). The duration filter catches most of these (< 60s or > 20min), but edge cases still land in `_review/`.
- **MusicBrainz release selection**: Prefers the earliest clean studio album. May occasionally pick an EP or single if the track was released there first. Check `_review/` after large batches.
- **Age-restricted videos**: yt-dlp skips these with an error. They won't appear in staging.
- **The Pronoia Sessions (Atreyu)**: The official playlist only had 1 video available at time of download.
- **MEDZ (The Used) track 02**: Age-restricted, skipped by yt-dlp.

---

## Logs

Operation log: `/vault/media/incoming/music_adder.log`

Each line is one of:
```
[timestamp] MOVED  filename → /full/dest/path
[timestamp] SKIP   filename (already at /full/dest/path)
[timestamp] REVIEW filename → /review/path
[timestamp] ERROR  url: reason
```
