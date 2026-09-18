import logging
from abc import ABC, abstractmethod

from streamlink import PluginError

from gridplayer.models.stream import (
    HashableDict,
    Stream,
    Streams,
    StreamSessionOpts,
)
from gridplayer.utils.network import needs_relay
from gridplayer.utils.url_resolve.static import BadURLException, ResolvedVideo
from gridplayer.utils.url_resolve.stream_detect import is_http_live_stream

# every URL relayed this way shares one session: they carry no headers of
# their own, so there is nothing to tell them apart by
DIRECT_SERVICE = "direct"


class ResolverBase(ABC):
    def __init__(self, url: str):
        self._log = logging.getLogger(self.__class__.__name__)

        self.url = url

    @property
    @abstractmethod
    def title(self) -> str: ...

    @property
    @abstractmethod
    def is_live(self) -> bool: ...

    @property
    @abstractmethod
    def streams(self) -> Streams: ...

    @staticmethod
    @abstractmethod
    def is_able_to_handle(url) -> bool: ...

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
        """The URL as it stands, unless fetching it takes more than VLC has.

        libVLC's http access offers a referrer and a user agent and
        nothing else: no cookie, no proxy it honours everywhere, no
        address family. A URL that needs any of those is fetched by the
        proxy and relayed instead of being handed over. The relay is not
        free, so it is only put in the way where something would
        otherwise be quietly dropped.
        """

        if not needs_relay(self.url):
            return Streams({"generic": Stream(url=self.url, protocol="direct")})

        self._log.debug("URL needs more than VLC has, relaying it through the proxy")

        return Streams(
            {
                "generic": Stream(
                    url=self.url,
                    protocol="http",
                    session=StreamSessionOpts(
                        service=DIRECT_SERVICE,
                        session_headers=HashableDict(),
                    ),
                )
            }
        )

    @staticmethod
    def is_able_to_handle(url: str):
        return True
