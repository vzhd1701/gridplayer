import logging

from streamlink import Streamlink

from gridplayer.models.stream import Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy.wrappers import (
    HLSMuxedStream,
    HLSProxy,
    HLSProxyLive,
    HTTPStreamProxy,
)


class StreamSession(object):
    def __init__(self, stream_session: StreamSessionOpts, server):
        self._log = logging.getLogger(self.__class__.__name__)

        self._stream_session = stream_session
        self._server = server

        self._session = Streamlink()
        self._session.http.headers.update(stream_session.session_headers)

    def get_stream(self, url: str, protocol: str):
        if protocol == "http":
            self._log.debug("Stream is http, using HTTPStreamProxy")
            return HTTPStreamProxy(
                server=self._server,
                session_opts=self._stream_session,
                session_=self._session,
                url=url,
            )
        elif protocol == "hls_proxy":
            self._log.debug("Stream is hls_proxy, using HLSProxy")
            return HLSProxy(
                server=self._server,
                session_opts=self._stream_session,
                session_=self._session,
                url=url,
            )
        elif protocol == "hls":
            self._log.debug("Stream is hls, using HLSProxyLive")
            return HLSProxyLive(session_=self._session, url=url, force_restart=True)

        raise RuntimeError(f"Cannot handle protocol {protocol}")

    def get_muxed_stream(self, stream: Stream):
        return HLSMuxedStream(server=self._server, stream=stream)
