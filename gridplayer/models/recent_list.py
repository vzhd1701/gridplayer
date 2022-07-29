from pathlib import Path
from typing import Generic, Iterable, List, Optional, TypeVar, Union

from pydantic import parse_obj_as

from gridplayer.models.video_uri import VideoURI

T = TypeVar("T")

IN_URI = Union[str, VideoURI]
IN_PATH = Union[str, Path]


class RecentList(Generic[T]):
    def __init__(self):
        self._list: List[T] = []

    def __bool__(self) -> bool:
        return bool(self._list)

    def __iter__(self) -> Iterable[T]:
        return iter(self._list)

    def __len__(self):
        return len(self._list)

    def add(self, items: List[T]) -> None:
        for item in reversed(items):
            if item in self._list:
                self._list.remove(item)
            self._list.insert(0, item)

    def truncate(self, limit: int) -> None:
        if len(self._list) > limit:
            self._list = self._list[:limit]


class RecentListVideos(RecentList[VideoURI]):
    def __init__(self, uris: Optional[List[IN_URI]] = None):
        super().__init__()

        if uris is None:
            return

        for uri in uris:
            if isinstance(uri, str):
                try:
                    uri = parse_obj_as(VideoURI, uri)
                except ValueError:
                    continue

            self._list.append(uri)


class RecentListPlaylists(RecentList[Path]):
    def __init__(self, paths: Optional[List[IN_PATH]] = None):
        super().__init__()

        if paths is None:
            return

        for path in paths:
            self._list.append(Path(path))
