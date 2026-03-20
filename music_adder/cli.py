import argparse
import os
import sys

from .pipeline import cmd_add, cmd_batch, cmd_status, cmd_review


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="music-adder",
        description="Download, tag, and add music to the vault library.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Add a single URL or re-process a local folder")
    add_p.add_argument("target", help="YouTube URL or local folder path")

    batch_p = sub.add_parser("batch", help="Process a file of URLs (one per line, # comments ok)")
    batch_p.add_argument("file", help="Path to URL list file")

    sub.add_parser("status", help="Show library and review queue file counts")
    sub.add_parser("review", help="Show items in the review queue")

    args = parser.parse_args()

    try:
        if args.command == "add":
            cmd_add(args.target)
        elif args.command == "batch":
            cmd_batch(args.file)
        elif args.command == "status":
            cmd_status()
        elif args.command == "review":
            cmd_review()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


def becca_main() -> None:
    os.environ.setdefault("MUSIC_ADDER_LIBRARY", "/vault/media/becca_music")
    os.environ.setdefault("MUSIC_ADDER_INCOMING", "/vault/media/becca_incoming")
    main()


if __name__ == "__main__":
    main()
