import logging

from streamlink import Streamlink

from gridplayer.models.stream import Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy.wrappers import (
    DASHPlaylistStream,
    HLSMuxedStream,
    HLSProxy,
    HLSProxyLive,
    HTTPPlaylistStream,
    HTTPStreamProxy,
)


class StreamSession:
    def __init__(self, stream_session: StreamSessionOpts, server):
        self._log = logging.getLogger(self.__class__.__name__)

        self._stream_session = stream_session
        self._server = server

        self._session = Streamlink()
        self._session.http.headers.update(stream_session.session_headers)

    def get_stream(self, stream: Stream):
        if stream.audio_tracks:
            self._log.debug("Stream has separate audio, using HLSMuxedStream")
            return HLSMuxedStream(server=self._server, stream=stream)

        return self._get_solo_stream(stream)

    def _get_solo_stream(self, stream: Stream):
        protocol = stream.protocol

        if protocol == "http":
            self._log.debug("Stream is http, using HTTPStreamProxy")
            return HTTPStreamProxy(
                server=self._server,
                session_opts=self._stream_session,
                session_=self._session,
                url=stream.url,
            )
        elif protocol == "http_hls":
            self._log.debug("Stream is http_hls, using HTTPPlaylistStream")
            return HTTPPlaylistStream(
                server=self._server,
                session_opts=self._stream_session,
                session_=self._session,
                stream=stream,
            )
        elif protocol == "dash":
            self._log.debug("Stream is dash, using DASHPlaylistStream")
            return DASHPlaylistStream(
                server=self._server,
                session_opts=self._stream_session,
                stream=stream,
            )
        elif protocol == "hls_proxy":
            self._log.debug("Stream is hls_proxy, using HLSProxy")
            return HLSProxy(
                server=self._server,
                session_opts=self._stream_session,
                session_=self._session,
                url=stream.url,
            )
        elif protocol == "hls":
            self._log.debug("Stream is hls, using HLSProxyLive")
            return HLSProxyLive(
                session=self._session, url=stream.url, force_restart=True
            )

        raise RuntimeError(f"Cannot handle protocol {protocol}")
