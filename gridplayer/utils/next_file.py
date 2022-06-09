import random
from pathlib import Path
from typing import Optional

from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT


def next_video_file(file: Path, is_shuffle=False) -> Optional[Path]:
    siblings = _file_siblings(file)

    if is_shuffle:
        random.shuffle(siblings)

    try:
        next_id = siblings.index(file) + 1
    except ValueError:
        return None

    if next_id >= len(siblings):
        next_id = 0

    return siblings[next_id]


def previous_video_file(file: Path) -> Optional[Path]:
    siblings = _file_siblings(file)

    try:
        next_id = siblings.index(file) - 1
    except ValueError:
        return None

    if next_id >= len(siblings):
        next_id = 0

    return siblings[next_id]


def _file_siblings(file: Path):
    return sorted(
        f
        for f in file.parent.iterdir()
        if f.is_file() and f.suffix[1:].lower() in SUPPORTED_MEDIA_EXT
    )
