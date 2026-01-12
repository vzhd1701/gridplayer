from functools import cached_property

from streamlink import NoPluginError, PluginError, Streamlink
from streamlink.plugin import Plugin
from streamlink.stream import HLSStream, MuxedHLSStream

from gridplayer.models.stream import HashableDict, Stream, Streams, StreamSessionOpts
from gridplayer.settings import Settings
from gridplayer.utils.url_resolve.resolver_base import ResolverBase
from gridplayer.utils.url_resolve.static import NoResolverPlugin
from gridplayer.utils.url_resolve.stream_detect import (
    is_hls_live_stream,
    is_http_live_stream,
)


class StreamlinkResolver(ResolverBase):
    @property
    def title(self):
        return self._plugin.get_title() or self.url

    @cached_property
    def is_live(self):
        best_stream = list(self._raw_streams.values())[-1]

        if isinstance(best_stream, MuxedHLSStream):
            return is_hls_live_stream(best_stream.substreams[0].url, self._session)

        elif isinstance(best_stream, HLSStream):
            return is_hls_live_stream(best_stream.url, self._session)

        return is_http_live_stream(best_stream.url, self._session)

    @property
    def streams(self):
        video_streams = {
            resolution: self._convert_stream(src_stream=stream, is_live=self.is_live)
            for resolution, stream in self._raw_streams_with_video.items()
        }

        audio_only_streams = {
            resolution: self._convert_stream(
                src_stream=stream, is_live=self.is_live, is_audio_only=True
            )
            for resolution, stream in self._raw_streams_audio_only.items()
        }

        return Streams({**video_streams, **audio_only_streams})

    @staticmethod
    def is_able_to_handle(url: str):
        try:
            return bool(Streamlink().resolve_url(url))
        except NoPluginError:
            return False

    @cached_property
    def _session(self) -> Streamlink:
        return Streamlink()

    @cached_property
    def _plugin(self) -> Plugin:
        try:
            _, plugin_class, resolved_url = self._session.resolve_url(self.url)
        except NoPluginError as e:
            raise NoResolverPlugin from e

        return plugin_class(self._session, resolved_url)

    @property
    def _stream_types(self):
        # vimeo's muxed hls streams are a mess, half of them return 404
        if self._plugin.module == "vimeo":
            return ["hls", "http"]

        return ["hls", "http", "hls-multi"]

    @cached_property
    def _raw_streams(self):
        try:
            streams = self._plugin.streams(stream_types=self._stream_types)
        except PluginError as e:
            self._log.warning(f"Streamlink - plugin error [{e}]")
            self._log.debug("Traceback", exc_info=e)
            raise NoResolverPlugin

        if not streams:
            self._log.debug("Streamlink - no streams found")
            raise NoResolverPlugin

        self._log.debug(f"Streamlink - {len(streams)} stream(s) found")

        streams.pop("best", None)
        streams.pop("worst", None)

        return streams

    @cached_property
    def _raw_streams_with_video(self):
        return {
            resolution: stream
            for resolution, stream in self._raw_streams.items()
            if "audio" not in resolution
        }

    @cached_property
    def _raw_streams_audio_only(self):
        audio_streams = {
            resolution: stream
            for resolution, stream in self._raw_streams.items()
            if "audio" in resolution
        }

        audio_streams.update(self._raw_streams_audio_only_muxed)

        return audio_streams

    @cached_property
    def _raw_streams_audio_only_muxed(self):
        muxed_streams = [
            stream
            for stream in self._raw_streams.values()
            if isinstance(stream, MuxedHLSStream)
        ]

        # ensure that we are extracting unique audio streams
        audio_streams_filter = {}
        for m_stream in muxed_streams:
            for audio_track in m_stream.substreams[1:]:
                audio_streams_filter[audio_track.url] = audio_track

        return {
            f"Audio Only {stream_idx}": stream
            for stream_idx, stream in enumerate(audio_streams_filter.values())
        }

    @property
    def _service_id(self):
        return f"streamlink-{self._plugin.module}"

    def _convert_stream(self, src_stream, is_live: bool, is_audio_only: bool = False):
        if isinstance(src_stream, MuxedHLSStream):
            audio_tracks = Streams(
                {
                    f"Audio {i}": self._convert_stream(
                        src_stream=s, is_live=False, is_audio_only=True
                    )
                    for i, s in enumerate(src_stream.substreams[1:])
                }
            )

            return Stream(
                url=src_stream.substreams[0].url,
                protocol="hls_proxy",
                audio_tracks=audio_tracks,
                session=StreamSessionOpts(
                    service=self._service_id,
                    session_headers=HashableDict(self._session.http.headers),
                ),
            )

        protocol = src_stream.shortname()

        is_via_streamlink = Settings().get("streaming/hls_via_streamlink")

        if protocol == "hls" and (not is_via_streamlink or not is_live):
            protocol = "hls_proxy"

        return Stream(
            url=src_stream.url,
            protocol=protocol,
            is_audio_only=is_audio_only,
            session=StreamSessionOpts(
                service=self._service_id,
                session_headers=HashableDict(self._session.http.headers),
            ),
        )
