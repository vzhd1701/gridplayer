import dataclasses
import logging
import os
from functools import partial
from io import IOBase
from itertools import chain
from typing import Dict

from requests import Response
from streamlink import StreamError
from streamlink.stream import (
    HLSStream,
    HTTPStream,
    StreamIOIterWrapper,
    StreamIOThreadWrapper,
)
from streamlink.stream.hls_playlist import M3U8
from streamlink.stream.hls_playlist import load as load_hls_playlist

from gridplayer.models.stream import Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy.m3u8 import m3u8_to_str

CHUNK_SIZE = 8192


class HTTPStreamProxy(HTTPStream):
    def __init__(  # noqa: WPS211
        self,
        server,
        session_opts: StreamSessionOpts,
        session_,  # noqa: WPS120
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

    def set_request_headers(self, headers: Dict[str, str]):
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

        base_url = os.path.dirname(self.args["url"]) + "/"
        hls_playlist = load_hls_playlist(self._res.text, base_url)

        hls_playlist_txt = self._proxify_hls_playlist(hls_playlist)

        self._set_hls_playlist_as_response(hls_playlist_txt)

    def _proxify_hls_playlist(self, hls_playlist: M3U8) -> str:
        for i, segment in enumerate(hls_playlist.segments):
            segment_url = self._proxify_url(segment.uri)

            hls_playlist.segments[i] = segment._replace(uri=segment_url)

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

    def set_request_headers(self, headers: Dict[str, str]):
        ...


class HLSMuxedStream(object):
    def __init__(self, server, stream: Stream):
        self.server = server
        self.stream = stream

        self._playlist = None

    def open(self):
        self._playlist = self._generate_hls_playlist()

    @property
    def response(self):
        res = Response()

        res.status_code = 200
        res.reason = "OK"

        res._content = self._playlist.encode("utf-8")

        res.headers["Content-Type"] = "application/vnd.apple.mpegurl"
        res.headers["Content-Length"] = str(len(res._content))

        return res

    def set_request_headers(self, headers: Dict[str, str]):
        ...

    def _generate_hls_playlist(self) -> str:
        res = ["#EXTM3U"]
        res += ["#EXT-X-INDEPENDENT-SEGMENTS"]

        # takes too long to load all tracks, picking the best one
        name, audio_track = self.stream.audio_tracks.best

        res += [
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
            'NAME="{name}",DEFAULT=YES,URI="{track_url}"'.format(
                name=name,
                track_url=self.server.add_stream(audio_track),
            )
        ]

        solo_stream = dataclasses.replace(self.stream, audio_tracks=None)

        res += ['#EXT-X-STREAM-INF:BANDWIDTH=0,AUDIO="audio"']
        res += [self.server.add_stream(solo_stream)]

        return "\n".join(res)


class StreamReader(object):
    def __init__(self, stream: HTTPStreamProxy, request_headers: Dict[str, str]):
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
