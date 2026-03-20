"""
Core pipeline: download → tag → move.
Handles a single staging directory.
"""

import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import config
from .downloader import download, find_audio_files
from .mover import destination, move_to_library, move_to_review
from .tagger import identify_and_tag, read_existing_tags

console = Console()


def _log(message: str) -> None:
    import datetime
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}\n"
    try:
        with open(config.log_path(), "a") as f:
            f.write(line)
    except OSError:
        pass


def process_staging_dir(staging_dir: Path, honor_tags: bool = False) -> dict:
    """
    Tag and move every audio file in staging_dir.
    Returns a summary dict: {moved: int, skipped: int, review: int}

    If honor_tags is True, use existing file tags instead of fingerprinting.
    """
    api_key = config.acoustid_key()
    library_root = config.library_path()
    review_root = config.review_path()

    if not honor_tags and not api_key:
        console.print(
            "[yellow]No AcoustID API key — fingerprinting disabled. "
            "Add acoustid.api_key to config.yaml or set ACOUSTID_KEY env var.[/yellow]"
        )

    audio_files = find_audio_files(staging_dir)
    if not audio_files:
        console.print(f"[yellow]No audio files found in {staging_dir}[/yellow]")
        return {"moved": 0, "skipped": 0, "review": 0}

    console.print(f"\nFound [bold]{len(audio_files)}[/bold] audio file(s)\n")

    moved, skipped, review = 0, 0, 0

    for f in audio_files:
        console.print(f"[bold]{f.name}[/bold]")

        if honor_tags:
            info = read_existing_tags(f)
            if info:
                console.print(f"  [dim]using existing tags[/dim]")
            else:
                console.print(f"  [yellow]no usable tags — skipping[/yellow]")
        else:
            info = identify_and_tag(f, api_key)

        if info:
            already = destination(info, f, library_root).exists()
            dest = move_to_library(f, info, library_root)
            if already:
                console.print(f"  [dim]already in library, skipped[/dim]")
                _log(f"SKIP  {f.name} (already at {dest})")
                skipped += 1
            else:
                console.print(
                    f"  [cyan]→ {dest.relative_to(library_root)}[/cyan]"
                )
                _log(f"MOVED {f.name} → {dest}")
                moved += 1
        else:
            dest = move_to_review(f, staging_dir, review_root)
            console.print(
                f"  [bold red]→ review queue[/bold red] ({dest.parent.name}/{dest.name})"
            )
            _log(f"REVIEW {f.name} → {dest}")
            review += 1

        console.print()

    # Clean up empty staging dir
    try:
        remaining = list(staging_dir.iterdir())
        if not remaining:
            staging_dir.rmdir()
        elif all(f.suffix == ".note" or f.name.startswith(".") for f in remaining):
            for f in remaining:
                f.unlink(missing_ok=True)
            staging_dir.rmdir()
    except OSError:
        pass

    return {"moved": moved, "skipped": skipped, "review": review}


def _print_summary(totals: dict) -> None:
    console.rule()
    t = Table.grid(padding=(0, 2))
    t.add_row("[green]Moved to library[/green]", str(totals["moved"]))
    t.add_row("[dim]Already in library[/dim]", str(totals["skipped"]))
    t.add_row("[bold red]Sent to review[/bold red]", str(totals["review"]))
    console.print(t)
    if totals["review"] > 0:
        console.print(
            "\n[bold red]! Review queue has items.[/bold red] "
            "Run [bold]music-adder review[/bold] to see them."
        )


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_add(target: str) -> None:
    incoming = config.incoming_path()
    incoming.mkdir(parents=True, exist_ok=True)

    if target.startswith("http://") or target.startswith("https://"):
        staging_dir = download(target, incoming)
        honor_tags = False
    else:
        staging_dir = Path(target).expanduser().resolve()
        if not staging_dir.exists():
            console.print(f"[red]Path not found: {staging_dir}[/red]")
            return
        console.print(
            "\n[bold]Local folder detected.[/bold] How should files be processed?\n"
            "  [bold cyan][t][/bold cyan] Honor existing tags (e.g. tagged in MusicBrainz Picard)\n"
            "  [bold cyan][i][/bold cyan] Re-identify via AcoustID + MusicBrainz\n"
        )
        while True:
            choice = console.input("[bold]Choice [t/i]:[/bold] ").strip().lower()
            if choice in ("t", "i"):
                break
            console.print("[yellow]Please enter t or i.[/yellow]")
        honor_tags = choice == "t"

    result = process_staging_dir(staging_dir, honor_tags=honor_tags)
    _print_summary(result)


def cmd_batch(file: str) -> None:
    batch_file = Path(file).expanduser().resolve()
    if not batch_file.exists():
        console.print(f"[red]File not found: {batch_file}[/red]")
        return

    urls = []
    with open(batch_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)

    if not urls:
        console.print("[yellow]No URLs found in file.[/yellow]")
        return

    console.print(f"[bold]Batch mode:[/bold] {len(urls)} URL(s)\n")

    totals = {"moved": 0, "skipped": 0, "review": 0}
    incoming = config.incoming_path()
    incoming.mkdir(parents=True, exist_ok=True)

    for i, url in enumerate(urls, 1):
        console.rule(f"[bold]{i}/{len(urls)}[/bold]")
        try:
            staging_dir = download(url, incoming)
            result = process_staging_dir(staging_dir)
            for k in totals:
                totals[k] += result[k]
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            _log(f"ERROR {url}: {e}")

    console.rule("[bold]Batch complete[/bold]")
    _print_summary(totals)


def cmd_status() -> None:
    library_root = config.library_path()
    review_root = config.review_path()

    lib_count = sum(1 for f in library_root.rglob("*") if f.is_file()) if library_root.exists() else 0
    review_count = sum(
        1 for f in review_root.rglob("*")
        if f.is_file() and f.suffix != ".note"
    ) if review_root.exists() else 0

    t = Table.grid(padding=(0, 2))
    t.add_row("[bold]Library[/bold]", str(library_root))
    t.add_row("  Tracks", f"[green]{lib_count}[/green]")
    t.add_row("[bold]Review queue[/bold]", str(review_root))
    t.add_row("  Pending", f"[{'red' if review_count else 'green'}]{review_count}[/{'red' if review_count else 'green'}]")
    console.print(t)


def cmd_review() -> None:
    review_root = config.review_path()

    if not review_root.exists():
        console.print("[green]Review queue is empty.[/green]")
        return

    items = [d for d in sorted(review_root.iterdir()) if d.is_dir()]
    audio_items = [
        (d, [f for f in d.iterdir() if f.suffix != ".note" and f.is_file()])
        for d in items
    ]
    audio_items = [(d, files) for d, files in audio_items if files]

    if not audio_items:
        console.print("[green]Review queue is empty.[/green]")
        return

    total = sum(len(files) for _, files in audio_items)
    console.print(
        f"\n[bold red blink]! REVIEW QUEUE: {total} file(s) need attention[/bold red blink]\n"
    )

    for d, files in audio_items:
        console.rule(f"[yellow]{d.name}[/yellow]")
        for f in sorted(files):
            note_path = d / f"{f.stem}.note"
            note = note_path.read_text() if note_path.exists() else ""
            console.print(f"  [bold]{f.name}[/bold]")
            if note:
                for line in note.splitlines():
                    console.print(f"  [dim]{line}[/dim]")
            console.print()

    console.rule()
    console.print(
        "[bold]To fix:[/bold] Open files in MusicBrainz Picard → save tags → "
        "run [bold]music-adder add <folder>[/bold]"
    )
