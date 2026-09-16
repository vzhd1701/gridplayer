import dataclasses
import logging
from functools import partial
from io import IOBase
from itertools import chain
from pathlib import Path

from requests import Response
from streamlink import StreamError
from streamlink.stream.hls import M3U8, HLSStream, parse_m3u8
from streamlink.stream.http import HTTPStream
from streamlink.stream.wrappers import StreamIOIterWrapper, StreamIOThreadWrapper

from gridplayer.models.stream import Stream, StreamFragment, StreamSessionOpts
from gridplayer.utils.stream_proxy.m3u8 import (
    build_master_playlist,
    build_media_playlist,
    m3u8_to_str,
)
from gridplayer.utils.stream_proxy.mp4 import (
    INDEX_PROBE_SIZE,
    INDEX_PROBE_SIZE_MAX,
    parse_segment_index,
)

CHUNK_SIZE = 8192

# last resort when neither an index nor a known duration is available
SINGLE_SEGMENT_DURATION = 86400.0


class HTTPStreamProxy(HTTPStream):
    def __init__(
        self,
        server,
        session_opts: StreamSessionOpts,
        session_,
        url: str,
        buffered: bool = True,
        **args,
    ):
        super().__init__(session_, url, buffered, **args)

        self._log = logging.getLogger(self.__class__.__name__)

        self._res = None

        self.server = server
        self.session_opts = session_opts

    @property
    def response(self) -> Response:
        return self._res

    def set_request_headers(self, headers: dict[str, str]):
        self.args["headers"] = headers

    def open(self):
        reqargs = self.session.http.valid_request_args(**self.args)
        reqargs.setdefault("method", "GET")
        timeout = self.session.options.get("stream-timeout")
        self._res = self.session.http.request(
            stream=True,
            exception=StreamError,
            timeout=timeout,
            **reqargs,
        )

        fd = StreamIOIterWrapper(self._res.iter_content(CHUNK_SIZE))
        if self.buffered:
            fd = StreamIOThreadWrapper(self.session, fd, timeout=timeout)

        return fd


class HLSProxy(HTTPStreamProxy):
    def open(self):
        reqargs = self.session.http.valid_request_args(**self.args)
        reqargs.setdefault("method", "GET")
        timeout = self.session.options.get("stream-timeout")
        self._res = self.session.http.request(
            exception=StreamError,
            timeout=timeout,
            **reqargs,
        )

        base_url = f"{Path(self.args['url']).parent}/"
        hls_playlist = parse_m3u8(self._res.text, base_url)

        hls_playlist_txt = self._proxify_hls_playlist(hls_playlist)

        self._set_hls_playlist_as_response(hls_playlist_txt)

    def _proxify_hls_playlist(self, hls_playlist: M3U8) -> str:
        for segment in hls_playlist.segments:  # type: HLSSegment
            segment.uri = self._proxify_url(segment.uri)
            if segment.map:
                segment.map = segment.map._replace(
                    uri=self._proxify_url(segment.map.uri)
                )

        return m3u8_to_str(hls_playlist)

    def _proxify_url(self, url):
        stream = Stream(
            url=url,
            protocol="http",
            session=self.session_opts,
        )
        return self.server.add_stream(stream)

    def _set_hls_playlist_as_response(self, hls_playlist: str):
        self.response._content = hls_playlist.encode("utf-8")

        self.response.status_code = 200
        self.response.reason = "OK"

        self.response.headers.clear()
        self.response.headers["Content-Type"] = "application/vnd.apple.mpegurl"
        self.response.headers["Content-Length"] = str(len(self.response._content))


class HLSProxyLive(HLSStream):
    @property
    def response(self):
        res = Response()
        res.status_code = 200
        res.reason = "OK"
        res.headers["Content-Type"] = "video/unknown"

        return res

    def set_request_headers(self, headers: dict[str, str]): ...


class GeneratedPlaylistStream:
    """Serves an HLS playlist that GridPlayer builds itself.

    Everything VLC cannot open on its own (DASH representations, bare
    fMP4 files, video paired with a separate audio track) is expressed as
    an HLS playlist whose entries point back at this proxy.
    """

    def __init__(self, server, session_opts: StreamSessionOpts, stream: Stream):
        self._log = logging.getLogger(self.__class__.__name__)

        self.server = server
        self.session_opts = session_opts
        self.stream = stream

        self._playlist = None

    def open(self):
        self._playlist = self._generate_playlist()

    @property
    def response(self):
        res = Response()

        res.status_code = 200
        res.reason = "OK"

        res._content = self._playlist.encode("utf-8")

        res.headers["Content-Type"] = "application/vnd.apple.mpegurl"
        res.headers["Content-Length"] = str(len(res._content))

        return res

    def set_request_headers(self, headers: dict[str, str]): ...

    def _generate_playlist(self) -> str:
        raise NotImplementedError

    def _proxify(self, stream: Stream) -> str:
        return self.server.add_stream(stream)

    def _proxify_url(self, url: str) -> str:
        return self._proxify(
            Stream(url=url, protocol="http", session=self.session_opts)
        )


class HLSMuxedStream(GeneratedPlaylistStream):
    """Pairs a video-only stream with a separate audio track."""

    def __init__(self, server, stream: Stream):
        super().__init__(server=server, session_opts=stream.session, stream=stream)

    def _generate_playlist(self) -> str:
        # takes too long to load all tracks, picking the best one
        name, audio_track = self.stream.audio_tracks.best

        solo_stream = dataclasses.replace(self.stream, audio_tracks=None)

        return build_master_playlist(
            video_url=self._proxify(solo_stream),
            audio_url=self._proxify(audio_track),
            audio_name=name,
        )


class DASHPlaylistStream(GeneratedPlaylistStream):
    """Turns a single DASH representation into an HLS media playlist.

    VLC's own DASH support picks its representation by itself, so handing
    it the manifest makes the quality menu meaningless. Segments come from
    the resolver, which already expanded the manifest for us.
    """

    def _generate_playlist(self) -> str:
        if not self.stream.fragments:
            raise StreamError("DASH stream has no segments")

        init_fragment = self.stream.init_fragment

        return build_media_playlist(
            segments=[
                self._proxify_fragment(fragment) for fragment in self.stream.fragments
            ],
            init_segment=(
                self._proxify_fragment(init_fragment)
                if init_fragment is not None
                else None
            ),
        )

    def _proxify_fragment(self, fragment: StreamFragment) -> StreamFragment:
        return dataclasses.replace(fragment, url=self._proxify_url(fragment.url))


class HTTPPlaylistStream(GeneratedPlaylistStream):
    """Turns a single fragmented MP4 file into an HLS media playlist."""

    def __init__(self, server, session_opts: StreamSessionOpts, session_, stream):
        super().__init__(server=server, session_opts=session_opts, stream=stream)

        self.session = session_

    def _generate_playlist(self) -> str:
        proxy_url = self._proxify_url(self.stream.url)

        index = self._read_segment_index()

        if index is None:
            self._log.debug("No segment index found, serving file as one segment")

            return build_media_playlist(
                segments=[StreamFragment(url=proxy_url, duration=self._stream_duration)]
            )

        self._log.debug(f"Segment index found, {len(index.segments)} segment(s)")

        return build_media_playlist(
            segments=index.as_fragments(proxy_url),
            init_segment=index.as_init_fragment(proxy_url),
        )

    @property
    def _stream_duration(self) -> float:
        # VLC takes the playlist duration as the media length, so a wrong
        # guess here would misplace the whole seek bar
        return self.stream.duration or SINGLE_SEGMENT_DURATION

    def _read_segment_index(self):
        for probe_size in (INDEX_PROBE_SIZE, INDEX_PROBE_SIZE_MAX):
            head = self._read_head(probe_size)

            if head is None:
                return None

            index = parse_segment_index(head)

            if index is not None:
                return index

            if len(head) < probe_size:
                return None

        return None

    def _read_head(self, size: int) -> bytes | None:
        """Read the start of the file without pulling in the whole thing.

        Servers are free to ignore the range request, so the response is
        streamed and cut short instead of being trusted to be small.
        """

        try:
            with self.session.http.get(
                self.stream.url,
                headers={"Range": f"bytes=0-{size - 1}"},
                stream=True,
                exception=StreamError,
            ) as response:
                return next(response.iter_content(size), b"")
        except (StreamError, OSError) as err:
            self._log.debug(f"Failed to probe stream head: {err}")
            return None


class StreamReader:
    def __init__(self, stream: HTTPStreamProxy, request_headers: dict[str, str]):
        self._log = logging.getLogger(self.__class__.__name__)

        self._stream_fd = None
        self._prebuffer = None

        self.stream = stream
        self.stream.set_request_headers(request_headers)

    def __enter__(self):
        self._stream_fd = self.stream.open()

        if isinstance(self._stream_fd, IOBase):
            return self.stream.response, self.iter_chunks()

        return self.stream.response, None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._stream_fd:
            self._stream_fd.close()

    def iter_chunks(self):
        # Read 8192 bytes before proceeding to check for errors.
        # This is to avoid opening the output unnecessarily.

        self._log.debug(f"Pre-buffering {CHUNK_SIZE} bytes")

        try:
            self._prebuffer = self._stream_fd.read(CHUNK_SIZE)
        except OSError as err:
            self._stream_fd.close()
            raise StreamError(f"Failed to read data from stream: {err}")

        if not self._prebuffer:
            self._stream_fd.close()
            raise StreamError("No data returned from stream")

        try:
            yield from chain(
                [self._prebuffer],
                iter(partial(self._stream_fd.read, CHUNK_SIZE), b""),
            )
        except OSError as err:
            self._log.error(f"Error when reading from stream: {err}, exiting")
