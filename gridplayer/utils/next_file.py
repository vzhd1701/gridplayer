import random
from pathlib import Path
from typing import Optional

from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT


def next_video_file(file: Path, original_dir: Path = None, is_shuffle=False) -> Optional[Path]:
    if original_dir is None:
        original_dir = file.parent

    siblings = _file_siblings(original_dir)

    if is_shuffle:
        random.shuffle(siblings)

    try:
        next_id = siblings.index(file) + 1
    except ValueError:
        return None

    if next_id >= len(siblings):
        next_id = 0

    return siblings[next_id]


def previous_video_file(file: Path, original_dir: Path = None) -> Optional[Path]:
    if original_dir is None:
        original_dir = file.parent

    siblings = _file_siblings(original_dir)

    try:
        prev_id = siblings.index(file) - 1
    except ValueError:
        return None

    if prev_id < 0:
        prev_id = len(siblings) - 1

    return siblings[prev_id]


def _file_siblings(directory: Path):
    return sorted(
        f
        for f in directory.rglob("*")
        if f.is_file() and f.suffix[1:].lower() in SUPPORTED_MEDIA_EXT
    )
