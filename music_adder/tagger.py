"""
Identify and tag audio files.

Pipeline per file:
  1. AcoustID fingerprint → MusicBrainz recording lookup
  2. Fallback: parse filename → MusicBrainz text search
  3. Write tags via mutagen (easy interface)
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import acoustid
import musicbrainzngs
import mutagen
from rich.console import Console

console = Console()

musicbrainzngs.set_useragent("music-adder", "0.1.0", "andrew.lincoln.smith@gmail.com")
musicbrainzngs.set_rate_limit(True)


@dataclass
class TrackInfo:
    artist: str
    title: str
    album: str | None = None
    album_artist: str | None = None
    year: str | None = None
    track_number: str | None = None
    identified: bool = True


# ---------------------------------------------------------------------------
# AcoustID path
# ---------------------------------------------------------------------------

def _mb_recording_lookup(
    mbid: str,
    hint_title: str | None = None,
    hint_artist: str | None = None,
) -> TrackInfo | None:
    """Look up a recording by MBID.

    Prefer search_recordings when hint_title/hint_artist are available because
    the search endpoint embeds release-group primary-type in each release;
    get_recording_by_id with inc=releases does not.
    """
    rec: dict | None = None

    if hint_title and hint_artist:
        try:
            results = musicbrainzngs.search_recordings(
                recording=hint_title, artist=hint_artist, limit=20
            )
            for r in results.get("recording-list", []):
                if r.get("id") == mbid:
                    rec = r
                    break
        except musicbrainzngs.WebServiceError:
            pass

    if rec is None:
        try:
            data = musicbrainzngs.get_recording_by_id(
                mbid,
                includes=["artists", "releases"],
            )
        except musicbrainzngs.WebServiceError:
            return None
        rec = data.get("recording", {})

    title = rec.get("title", "").strip()
    if not title:
        return None

    artist = _flatten_artist_credit(rec.get("artist-credit", []))
    if not artist:
        return None

    releases = rec.get("release-list", [])
    best = _pick_best_release(releases)

    info = TrackInfo(artist=artist, title=title)
    if best:
        info.album = best.get("title")
        info.album_artist = artist
        info.year = _extract_year(best.get("date", ""))

    return info


def _acoustid_lookup(path: Path, api_key: str) -> TrackInfo | None:
    try:
        results = list(acoustid.match(api_key, str(path)))
    except acoustid.NoBackendError:
        console.print("[red]fpcalc not found — install chromaprint-tools[/red]")
        raise
    except acoustid.FingerprintGenerationError:
        console.print(f"[yellow]  Could not fingerprint {path.name}[/yellow]")
        return None
    except acoustid.WebServiceError as e:
        console.print(f"[yellow]  AcoustID API error: {e}[/yellow]")
        return None

    for score, rid, _title, _artist in results:
        if score < 0.5:
            break
        if not rid:
            continue
        info = _mb_recording_lookup(rid, hint_title=_title, hint_artist=_artist)
        if info:
            return info

    return None


# ---------------------------------------------------------------------------
# Filename fallback path
# ---------------------------------------------------------------------------

_NOISE_RE = re.compile(
    r"\s*[\(\[](official|audio|video|hd|4k|mv|lyrics?|visualizer|"
    r"full\s+album|feat\.|ft\.|explicit|remaster)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

_INDEX_RE = re.compile(r"^\d+\s+")  # leading "01 " from yt-dlp playlist index


def _parse_filename(path: Path) -> tuple[str | None, str | None]:
    stem = _INDEX_RE.sub("", path.stem)
    stem = _NOISE_RE.sub("", stem).strip()

    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()

    return None, stem.strip()


def _filename_lookup(path: Path) -> TrackInfo | None:
    artist, title = _parse_filename(path)
    # Without a parseable artist we can't trust the MB text match — send to review
    if not artist or not title:
        return None

    try:
        results = musicbrainzngs.search_recordings(
            recording=title,
            artist=artist,
            limit=5,
        )
    except musicbrainzngs.WebServiceError:
        return None

    recordings = results.get("recording-list", [])
    if not recordings:
        return None

    best = max(recordings, key=lambda r: int(r.get("ext:score", 0)))
    if int(best.get("ext:score", 0)) < 70:
        return None

    rec_title = best.get("title", "").strip()
    rec_artist = _flatten_artist_credit(best.get("artist-credit", [])) or artist
    if not rec_title or not rec_artist:
        return None

    releases = best.get("release-list", [])
    best_release = _pick_best_release(releases)

    info = TrackInfo(artist=rec_artist, title=rec_title)
    if best_release:
        info.album = best_release.get("title")
        info.album_artist = rec_artist
        info.year = _extract_year(best_release.get("date", ""))

    return info


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_artist_credit(credits: list) -> str:
    parts = []
    for credit in credits:
        if isinstance(credit, dict):
            name = credit.get("name") or credit.get("artist", {}).get("name", "")
            parts.append(name)
            joinphrase = credit.get("joinphrase", "")
            if joinphrase:
                parts.append(joinphrase)
        elif isinstance(credit, str):
            parts.append(credit)
    return "".join(parts).strip()


def _extract_year(date_str: str) -> str | None:
    if not date_str:
        return None
    match = re.match(r"(\d{4})", date_str)
    return match.group(1) if match else None


# Keywords in release/release-group titles that indicate non-primary releases
_TITLE_SKIP_WORDS = {
    "instrumental", "sampler", "demo", "promo", "karaoke",
    "live", "acoustic", "unplugged", "remix", "remixes",
    "compilation", "best of", "greatest hits", "warped tour",
    "all areas", "tour compilation",
}


def _release_title_is_clean(r: dict) -> bool:
    title = (r.get("title") or "").lower()
    rg_title = (r.get("release-group", {}).get("title") or "").lower()
    return not any(w in title or w in rg_title for w in _TITLE_SKIP_WORDS)


def _rg_primary_type(r: dict) -> str:
    """Return release-group primary type, checking both 'primary-type' and 'type' keys."""
    rg = r.get("release-group", {})
    return rg.get("primary-type") or rg.get("type") or ""


def _pick_best_release(releases: list) -> dict | None:
    if not releases:
        return None

    secondary_bad = {"Live", "Compilation", "Remix", "DJ-mix", "Mixtape/Street"}

    def _is_clean_album(r: dict) -> bool:
        if _rg_primary_type(r) != "Album":
            return False
        rg = r.get("release-group", {})
        if any(s in secondary_bad for s in rg.get("secondary-type-list", [])):
            return False
        return _release_title_is_clean(r)

    def _is_clean_non_single(r: dict) -> bool:
        """EP or other non-Single, non-compilation release — better than a single."""
        if _rg_primary_type(r) == "Single":
            return False
        rg = r.get("release-group", {})
        if any(s in secondary_bad for s in rg.get("secondary-type-list", [])):
            return False
        return _release_title_is_clean(r)

    def _is_any_clean(r: dict) -> bool:
        rg = r.get("release-group", {})
        if any(s in secondary_bad for s in rg.get("secondary-type-list", [])):
            return False
        return _release_title_is_clean(r)

    # Preference order: clean album > clean non-single (EP etc.) > any clean > anything
    for pool_fn in (_is_clean_album, _is_clean_non_single, _is_any_clean, lambda r: True):
        pool = [r for r in releases if pool_fn(r)]
        if pool:
            dated = [r for r in pool if r.get("date")]
            if dated:
                return min(dated, key=lambda r: r["date"])
            return pool[0]

    return releases[0]


# ---------------------------------------------------------------------------
# Read existing tags
# ---------------------------------------------------------------------------

def read_existing_tags(path: Path) -> TrackInfo | None:
    """
    Build a TrackInfo from tags already on the file (e.g. set by MusicBrainz Picard).
    Returns None if artist or title are missing.
    """
    try:
        f = mutagen.File(str(path), easy=True)
    except Exception:
        return None
    if f is None:
        return None

    def _get(key: str) -> str | None:
        vals = f.get(key)
        return vals[0].strip() if vals else None

    artist = _get("artist")
    title = _get("title")
    if not artist or not title:
        return None

    return TrackInfo(
        artist=artist,
        title=title,
        album=_get("album"),
        album_artist=_get("albumartist"),
        year=_get("date"),
    )


# ---------------------------------------------------------------------------
# Write tags
# ---------------------------------------------------------------------------

def write_tags(path: Path, info: TrackInfo) -> None:
    f = mutagen.File(str(path), easy=True)
    if f is None:
        raise ValueError(f"mutagen cannot handle {path.name}")
    f["title"] = info.title
    f["artist"] = info.artist
    if info.album:
        f["album"] = info.album
    if info.album_artist:
        f["albumartist"] = info.album_artist
    if info.year:
        f["date"] = info.year
    if info.track_number:
        f["tracknumber"] = str(info.track_number)
    f.save()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def identify_and_tag(path: Path, api_key: str | None) -> TrackInfo | None:
    """
    Attempt to identify the file and write tags.
    Returns TrackInfo on success, None if unidentified.
    """
    info = None

    if api_key:
        console.print(f"  [dim]fingerprinting...[/dim]", end=" ")
        info = _acoustid_lookup(path, api_key)
        if info:
            console.print(f"[green]AcoustID match[/green]")
        else:
            console.print(f"[yellow]no match[/yellow]")

    if info is None:
        console.print(f"  [dim]filename fallback...[/dim]", end=" ")
        info = _filename_lookup(path)
        if info:
            console.print(f"[green]MB text match[/green]")
        else:
            console.print(f"[red]unidentified[/red]")

    if info:
        write_tags(path, info)

    return info
