import logging
from abc import ABC, abstractmethod

from streamlink import PluginError

from gridplayer.models.stream import Stream, Streams
from gridplayer.models.video import VideoURL
from gridplayer.utils.url_resolve.static import BadURLException, ResolvedVideo
from gridplayer.utils.url_resolve.stream_detect import is_http_live_stream


class ResolverBase(ABC):
    def __init__(self, url: VideoURL):
        self._log = logging.getLogger(self.__class__.__name__)

        self.url = url

    @property
    @abstractmethod
    def title(self) -> str:
        ...

    @property
    @abstractmethod
    def is_live(self) -> bool:
        ...

    @property
    @abstractmethod
    def streams(self) -> Streams:
        ...

    @staticmethod
    @abstractmethod
    def is_able_to_handle(url) -> bool:  # noqa: WPS602
        ...

    def resolve(self) -> ResolvedVideo:
        return ResolvedVideo(
            title=self.title,
            streams=self.streams,
            is_live=self.is_live,
        )


class DirectResolver(ResolverBase):
    @property
    def title(self) -> str:
        return self.url

    @property
    def is_live(self) -> bool:
        try:
            return is_http_live_stream(self.url)
        except PluginError:
            raise BadURLException(f"Cannot open URL {self.url}")

    @property
    def streams(self) -> Streams:
        return Streams({"generic": Stream(url=self.url, protocol="direct")})

    @staticmethod
    def is_able_to_handle(url: VideoURL):  # noqa: WPS602
        return True
