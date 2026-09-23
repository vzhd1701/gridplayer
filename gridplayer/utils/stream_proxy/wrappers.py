import dataclasses
import logging
from functools import partial
from io import IOBase
from itertools import chain
from urllib.parse import urljoin

from requests import Response
from streamlink import StreamError
from streamlink.stream.hls import M3U8, HLSStream, parse_m3u8
from streamlink.stream.http import HTTPStream
from streamlink.stream.wrappers import StreamIOIterWrapper, StreamIOThreadWrapper

from gridplayer.models.stream import Stream, StreamFragment, StreamSessionOpts
from gridplayer.utils.stream_proxy.fragments import FRAGMENT_INIT, FRAGMENT_SELF
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
from gridplayer.utils.stream_proxy.mpd import rewrite_manifest

CHUNK_SIZE = 8192

# last resort when neither an index nor a known duration is available
SINGLE_SEGMENT_DURATION = 86400.0

M3U8_CONTENT_TYPE = "application/vnd.apple.mpegurl"
MPD_CONTENT_TYPE = "application/dash+xml"


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
        self._res = self._fetch(stream=True)

        fd = StreamIOIterWrapper(self._res.iter_content(CHUNK_SIZE))
        if self.buffered:
            fd = StreamIOThreadWrapper(self.session, fd, timeout=self._timeout)

        return fd

    def _fetch(self, stream: bool = False) -> Response:
        """Ask the host for this URL, with the session's cookies and headers."""

        reqargs = self.session.http.valid_request_args(**self.args)
        reqargs.setdefault("method", "GET")

        return self.session.http.request(
            stream=stream,
            exception=StreamError,
            timeout=self._timeout,
            **reqargs,
        )

    def _replace_body(self, body: str, content_type: str) -> None:
        """Hand over what was written here rather than what was fetched.

        The response that came back is answered with, headers and all, so
        what it says about its own body has to go with the body.
        """

        self.response._content = body.encode("utf-8")

        self.response.status_code = 200
        self.response.reason = "OK"

        self.response.headers.clear()
        self.response.headers["Content-Type"] = content_type
        self.response.headers["Content-Length"] = str(len(self.response._content))

    @property
    def _fetched_from(self) -> str:
        """Where the document came from in the end, redirects and all.

        What is inside it is written relative to wherever it was served,
        which is not always where it was asked for: a playlist handed to
        another host takes its segments with it.
        """

        return self._res.url

    @property
    def _timeout(self):
        return self.session.options.get("stream-timeout")


class HLSProxy(HTTPStreamProxy):
    def open(self):
        self._res = self._fetch()

        hls_playlist = parse_m3u8(self._res.text, self._playlist_base_url)

        self._replace_body(self._proxify_hls_playlist(hls_playlist), M3U8_CONTENT_TYPE)

    @property
    def _playlist_base_url(self) -> str:
        """What the playlist's own relative segment URIs are relative to.

        A URL is not a path: Path() eats one of the slashes after the
        scheme, and on Windows turns what is left into a backslash, so
        every relative segment came out unopenable.
        """

        return urljoin(self._fetched_from, ".")

    def _proxify_hls_playlist(self, hls_playlist: M3U8) -> str:
        for segment in hls_playlist.segments:  # type: HLSSegment
            segment.uri = self._proxify_url(segment.uri)
            if segment.map:
                segment.map = dataclasses.replace(
                    segment.map, uri=self._proxify_url(segment.map.uri)
                )

        return m3u8_to_str(hls_playlist)

    def _proxify_url(self, url):
        stream = Stream(
            url=url,
            protocol="http",
            session=self.session_opts,
        )
        return self.server.add_stream(stream)


class DASHManifestProxy(HTTPStreamProxy):
    """Serves a live DASH manifest with its URLs pointed back at the proxy.

    VLC has to follow a live manifest itself, because the segment list
    moves and only the player knows when to ask for more. So the
    manifest is fetched here, where the cookies are, and handed over
    with every URL in it replaced by one of ours. VLC refetches it as
    the manifest tells it to, and each refetch is rewritten again.
    """

    def open(self):
        self._res = self._fetch()

        manifest = rewrite_manifest(
            self._res.text,
            manifest_url=self._fetched_from,
            proxify=self._proxify_base,
        )

        self._replace_body(manifest, MPD_CONTENT_TYPE)

    def _proxify_base(self, url: str) -> str:
        return self.server.add_base(url, self.session_opts)


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

    def __init__(self, server, stream: Stream):
        self._log = logging.getLogger(self.__class__.__name__)

        self.server = server
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

        res.headers["Content-Type"] = M3U8_CONTENT_TYPE
        res.headers["Content-Length"] = str(len(res._content))

        return res

    def set_request_headers(self, headers: dict[str, str]): ...

    def _generate_playlist(self) -> str:
        raise NotImplementedError

    def _proxify(self, stream: Stream) -> str:
        return self.server.add_stream(stream)

    def _proxify_fragment_url(self, fragment: str) -> str:
        """Link back to one fragment of this stream, by position."""

        return self.server.add_stream(self.stream, fragment=fragment)


class HLSMuxedStream(GeneratedPlaylistStream):
    """Pairs a video-only stream with a separate audio track."""

    def _generate_playlist(self) -> str:
        # takes too long to load all tracks, picking the best one; which
        # language they are in was settled before we were handed them
        name, audio_track = self.stream.audio_tracks.best

        solo_stream = dataclasses.replace(self.stream, audio_tracks=None)

        return build_master_playlist(
            video_url=self._proxify(solo_stream),
            audio_url=self._proxify(self._with_origin(audio_track, name)),
            audio_name=name,
            audio_language=audio_track.language,
        )

    def _with_origin(self, audio_track: Stream, name: str) -> Stream:
        """Note which track this is, so it can be found again once renewed."""

        origin = self.stream.origin

        if origin is None:
            return audio_track

        return dataclasses.replace(
            audio_track, origin=dataclasses.replace(origin, audio_track=name)
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
                self._proxify_fragment(fragment, str(fragment_idx))
                for fragment_idx, fragment in enumerate(self.stream.fragments)
            ],
            init_segment=(
                self._proxify_fragment(init_fragment, FRAGMENT_INIT)
                if init_fragment is not None
                else None
            ),
        )

    def _proxify_fragment(
        self, fragment: StreamFragment, fragment_id: str
    ) -> StreamFragment:
        return dataclasses.replace(
            fragment, url=self._proxify_fragment_url(fragment_id)
        )


class HTTPPlaylistStream(GeneratedPlaylistStream):
    """Turns a single fragmented MP4 file into an HLS media playlist."""

    def __init__(self, server, session_, stream):
        super().__init__(server=server, stream=stream)

        self.session = session_

    def _generate_playlist(self) -> str:
        proxy_url = self._proxify_fragment_url(FRAGMENT_SELF)

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
