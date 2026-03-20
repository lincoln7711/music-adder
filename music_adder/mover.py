"""
Move a tagged audio file into the library vault.
"""

import grp
import os
import re
import shutil
from pathlib import Path

from .tagger import TrackInfo

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r"\s{2,}")


def _sanitize(s: str) -> str:
    s = _UNSAFE.sub("_", s)
    s = _MULTI_SPACE.sub(" ", s)
    return s.strip().strip(".")


def destination(info: TrackInfo, src: Path, library_root: Path) -> Path:
    artist = _sanitize(info.artist)
    title = _sanitize(info.title)
    ext = src.suffix.lower()

    if info.album:
        album = _sanitize(info.album)
        year = info.year or "????"
        folder_name = f"{album} ({year})"
        if info.track_number:
            try:
                nn = f"{int(info.track_number):02d} "
            except ValueError:
                nn = f"{info.track_number} "
        else:
            nn = ""
        return library_root / artist / folder_name / f"{nn}{title}{ext}"
    else:
        return library_root / "Non-Album" / f"{artist} - {title}{ext}"


def _set_plex_group(path: Path) -> None:
    try:
        gid = grp.getgrnam("plex").gr_gid
        os.chown(path, -1, gid)
    except (KeyError, PermissionError):
        pass


def move_to_library(src: Path, info: TrackInfo, library_root: Path) -> Path:
    dest = destination(info, src, library_root)

    if dest.exists():
        src.unlink()
        return dest  # already in library — skip

    dest.parent.mkdir(parents=True, exist_ok=True)
    _set_plex_group(dest.parent)

    shutil.move(str(src), str(dest))
    _set_plex_group(dest)

    return dest


def move_to_review(src: Path, staging_dir: Path, review_root: Path) -> Path:
    dest_dir = review_root / staging_dir.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    _set_plex_group(dest_dir)

    dest = dest_dir / src.name
    shutil.move(str(src), str(dest))

    note = dest_dir / f"{src.stem}.note"
    note.write_text(
        f"file: {src.name}\n"
        f"staging: {staging_dir.name}\n"
        f"action: Open in MusicBrainz Picard, tag, then run:\n"
        f"        music-adder add {dest_dir}\n"
    )

    return dest
