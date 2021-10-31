import logging
import os

from PyQt5.QtCore import QMimeData

from gridplayer.params_static import SUPPORTED_VIDEO_EXT

logger = logging.getLogger(__name__)


def drag_has_video_id(dnd_data: QMimeData):
    return dnd_data.hasFormat("application/x-gridplayer-video-id")


def drag_get_video_id(dnd_data: QMimeData):
    return bytes(dnd_data.data("application/x-gridplayer-video-id")).decode()


def drag_get_files(dnd_data):
    return filter_valid_files(_exctract_local_files(dnd_data))


def _exctract_local_files(dnd_data):
    files = []

    if not dnd_data.hasUrls():
        return []

    for url in dnd_data.urls():
        if not url.isLocalFile():
            logger.warning(f"{url} is not a local file!")
            continue

        files.append(url.toLocalFile())

    return files


def filter_valid_files(files):
    files = _filter_accesible_files(files)

    if not files:
        return []

    if len(files) == 1 and _filter_extensions(files, "gpls"):
        return files

    if _filter_extensions(files, "gpls"):
        logger.warning("Only single playlist file can be opened at a time!")
        return []

    video_files = _filter_extensions(files, SUPPORTED_VIDEO_EXT)

    for f in set(files) - set(video_files):
        logger.warning(f"{f} is not supported!")

    return video_files


def _filter_accesible_files(files):
    filtered = []

    for f in files:
        filepath = os.path.normpath(f)

        if not (os.path.isfile(filepath) and os.access(filepath, os.R_OK)):
            logger.warning(f"{filepath} file is not accessible!")
            continue

        filtered.append(filepath)

    return filtered


def _filter_extensions(files, extensions):
    filtered = []

    for f in files:
        _, ext = os.path.splitext(f)
        ext = ext[1:]

        if ext in extensions:
            filtered.append(f)

    return filtered
