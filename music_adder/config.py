import os
from pathlib import Path

import yaml

_CONFIG_PATH = Path("~/.config/music-tools/config.yaml").expanduser()

_cfg = None


def load() -> dict:
    global _cfg
    if _cfg is not None:
        return _cfg
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {_CONFIG_PATH}")
    with open(_CONFIG_PATH) as f:
        _cfg = yaml.safe_load(f)
    return _cfg


def library_path() -> Path:
    override = os.environ.get("MUSIC_ADDER_LIBRARY")
    if override:
        return Path(override)
    return Path(load()["library"]["path"])


def incoming_path() -> Path:
    override = os.environ.get("MUSIC_ADDER_INCOMING")
    if override:
        return Path(override)
    return library_path().parent / "incoming"


def review_path() -> Path:
    return incoming_path() / "_review"


def log_path() -> Path:
    return incoming_path() / "music_adder.log"


def acoustid_key() -> str | None:
    key = os.environ.get("ACOUSTID_KEY")
    if key:
        return key
    return load().get("acoustid", {}).get("api_key")
