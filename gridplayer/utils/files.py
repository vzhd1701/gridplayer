from pathlib import Path
from typing import List, Optional, Union

from PyQt5.QtCore import QMimeData

from gridplayer.models.video import VideoBlockMime
from gridplayer.utils.misc import is_url


def drag_has_video(dnd_data: QMimeData) -> bool:
    return dnd_data.hasFormat("application/x-gridplayer-video")


def drag_get_video(dnd_data: QMimeData) -> Optional[VideoBlockMime]:
    if not drag_has_video(dnd_data):
        return None

    return VideoBlockMime.parse_raw(
        bytes(dnd_data.data("application/x-gridplayer-video")).decode("utf-8")
    )


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
