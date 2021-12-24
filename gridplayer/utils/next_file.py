import random
from pathlib import Path
from typing import Optional

from gridplayer.params_static import SUPPORTED_VIDEO_EXT


def next_video_file(file: Path, is_before=False, is_shuffle=False) -> Optional[Path]:
    siblings = _file_siblings(file)

    if is_shuffle:
        random.shuffle(siblings)

    seek_increment = -1 if is_before else 1

    try:
        next_id = siblings.index(file) + seek_increment
    except ValueError:
        return None

    if next_id >= len(siblings):
        next_id = 0

    return siblings[next_id]


def _file_siblings(file: Path):
    return sorted(
        f
        for f in file.parent.iterdir()
        if f.is_file() and f.suffix[1:] in SUPPORTED_VIDEO_EXT
    )
