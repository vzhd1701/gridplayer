import logging
import os
from pathlib import Path
from typing import List, Set

from PyQt5.QtCore import QMimeData

from gridplayer.params_static import SUPPORTED_VIDEO_EXT

logger = logging.getLogger(__name__)


def drag_has_video_id(dnd_data: QMimeData):
    return dnd_data.hasFormat("application/x-gridplayer-video-id")


def drag_get_video_id(dnd_data: QMimeData):
    return bytes(dnd_data.data("application/x-gridplayer-video-id")).decode()


def drag_get_files(dnd_data: QMimeData) -> List[Path]:
    return filter_valid_files(_exctract_local_files(dnd_data))


def _exctract_local_files(dnd_data: QMimeData) -> List[Path]:
    files = []

    if not dnd_data.hasUrls():
        return []

    for url in dnd_data.urls():
        if not url.isLocalFile():
            logger.warning(f"{url} is not a local file!")
            continue

        files.append(Path(url.toLocalFile()))

    return files


def filter_valid_files(files: List[Path]):
    files = _filter_accesible_files(files)

    if not files:
        return []

    if len(files) == 1 and _filter_extensions(files, {"gpls"}):
        return files

    if _filter_extensions(files, {"gpls"}):
        logger.warning("Only single playlist file can be opened at a time!")
        return []

    video_files = _filter_extensions(files, SUPPORTED_VIDEO_EXT)

    for f in set(files) - set(video_files):
        logger.warning(f"{f} is not supported!")

    return video_files


def _filter_accesible_files(files: List[Path]) -> List[Path]:
    filtered = []

    for f in files:
        if not (f.is_file() and os.access(f, os.R_OK)):
            logger.warning(f"{f} file is not accessible!")
            continue

        filtered.append(f)

    return filtered


def _filter_extensions(files: List[Path], extensions: Set[str]):
    return [f for f in files if f.suffix[1:] in extensions]
