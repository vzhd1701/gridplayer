from typing import Optional

from streamlink import NoPluginError, PluginError, Streamlink
from streamlink.stream import HLSStream

from gridplayer.utils.url_resolve.static import (
    BadURLException,
    NoResolverPlugin,
    ResolvedVideo,
)
from gridplayer.utils.url_resolve.stream_detect import (
    is_hls_live_stream,
    is_http_live_stream,
)
from gridplayer.video import VideoURL


class StreamlinkResolver(object):
    def __init__(self, url):
        self.url = url

        self.session = Streamlink()

        self.plugin = self._get_plugin(self.url)

        self._streams = self._get_streams()

    @property
    def streams(self):
        return {
            res: stream.url
            for res, stream in self._streams.items()
            if res not in {"best", "worst"}
        }

    @property
    def title(self):
        return self.plugin.get_title() or self.url

    @property
    def is_live(self):
        if isinstance(self._streams["best"], HLSStream):
            return is_hls_live_stream(self._streams["best"].url)

        return is_http_live_stream(self._streams["best"].url)

    def _get_streams(self):
        try:
            streams = self.plugin.streams(stream_types=["hls", "http"])
        except PluginError:
            raise BadURLException("Plugin error")

        if not streams:
            raise BadURLException("No streams found")

        return streams

    def _get_plugin(self, url):
        try:
            plugin_class, resolved_url = self.session.resolve_url(url)
        except NoPluginError as e:
            raise NoResolverPlugin from e

        return plugin_class(resolved_url)


def resolve_streamlink(
    url: VideoURL, is_live: Optional[bool] = None
) -> Optional[ResolvedVideo]:
    resolver = StreamlinkResolver(url)

    if is_live is None:
        is_live = resolver.is_live

    return ResolvedVideo(title=resolver.title, urls=resolver.streams, is_live=is_live)
