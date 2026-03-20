# music-adder

Downloads audio from YouTube, identifies and tags each track via AcoustID + MusicBrainz, and moves files directly into the vault library. No beets. No database. No match thresholds.

## Commands

```bash
music-adder add <url|path>   # single URL (track or playlist), or re-process a local folder
music-adder batch <file>     # file of URLs, one per line (# comments ignored)
music-adder status           # library track count + review queue count
music-adder review           # show items in the review queue with instructions
```

## Requirements

- Python 3.10+
- `fpcalc` (chromaprint): `sudo apt install chromaprint-tools`
- `ffmpeg`: `sudo apt install ffmpeg`
- Python packages: installed automatically via `pip install -e .`

## Installation

```bash
pip install -e ~/projects/music-adder
```

## Configuration

Uses the shared config at `~/.config/music-tools/config.yaml`. Requires:

```yaml
library:
  path: /vault/media/music

acoustid:
  api_key: YOUR_KEY_HERE   # free key at https://acoustid.org/api-key
```

See `docs/usage.md` for full details.
