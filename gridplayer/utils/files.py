import logging
from pathlib import Path
from typing import List, Optional, Union

from PyQt5.QtCore import QMimeData

from gridplayer.utils.misc import is_url

logger = logging.getLogger(__name__)


def drag_has_video_id(dnd_data: QMimeData):
    return dnd_data.hasFormat("application/x-gridplayer-video-id")


def drag_get_video_id(dnd_data: QMimeData):
    return bytes(dnd_data.data("application/x-gridplayer-video-id")).decode()


def drag_get_uris(dnd_data: QMimeData) -> List[str]:
    return _extract_uris(dnd_data)


def _extract_uris(dnd_data: QMimeData) -> List[str]:
    uris = []

    if dnd_data.hasUrls():
        for url in dnd_data.urls():
            if url.isLocalFile():
                uris.append(url.toLocalFile())
            else:
                uris.append(url.url())

    elif dnd_data.hasText():
        dnd_text = dnd_data.text().splitlines()
        uris = [line.strip() for line in dnd_text if line.strip()]

    return _filter_uris(uris)


def _filter_uris(uris: List[str]) -> List[str]:
    return [u for u in uris if is_url(u) or Path(u).is_file()]


def get_playlist_path(uris: List[Union[str, Path]]) -> Optional[Path]:
    for uri in uris:
        uri_path = Path(uri)
        if uri_path.suffix.lower() == ".gpls" and uri_path.is_file():
            return uri_path

    return None
