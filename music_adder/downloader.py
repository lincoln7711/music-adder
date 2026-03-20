import subprocess
from datetime import datetime
from pathlib import Path

from rich.console import Console

console = Console()


def download(url: str, incoming_base: Path) -> Path:
    """Download audio from a URL (single track or playlist) into a timestamped staging dir."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_dir = incoming_base / timestamp
    staging_dir.mkdir(parents=True, exist_ok=True)

    console.rule(f"[bold cyan]Downloading[/bold cyan]")
    console.print(f"[dim]{url}[/dim]")
    console.print(f"[dim]→ {staging_dir}[/dim]\n")

    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "-x",
        "--audio-quality", "0",
        "--audio-format", "opus",
        "-o", str(staging_dir / "%(playlist_index)s %(title)s.%(ext)s"),
        "--yes-playlist",
        url,
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp exited with code {result.returncode}")

    return staging_dir


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".opus", ".ogg", ".wav", ".wma", ".aac", ".webm"}

MIN_DURATION_S = 60       # shorter = intro skit / ad
MAX_DURATION_S = 60 * 20  # longer = mix / full-album stream / workout video


def find_audio_files(staging_dir: Path) -> list[Path]:
    import mutagen as _mutagen

    accepted, rejected = [], []
    for f in sorted(staging_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            audio = _mutagen.File(str(f))
            duration = audio.info.length if audio else None
        except Exception:
            duration = None

        if duration is not None and (duration < MIN_DURATION_S or duration > MAX_DURATION_S):
            rejected.append((f, duration))
        else:
            accepted.append(f)

    if rejected:
        console.print(f"[dim]Skipping {len(rejected)} file(s) outside duration range ({MIN_DURATION_S}s–{MAX_DURATION_S}s):[/dim]")
        for f, d in rejected:
            console.print(f"[dim]  {f.name} ({int(d)}s)[/dim]")
            f.unlink()

    return accepted
