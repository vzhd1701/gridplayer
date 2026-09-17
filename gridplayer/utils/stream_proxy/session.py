import logging

from streamlink import Streamlink

from gridplayer.models.stream import Stream, StreamSessionOpts
from gridplayer.utils.cookies import apply_to_streamlink, cookies_stamp
from gridplayer.utils.stream_proxy.wrappers import (
    DASHManifestProxy,
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

        self._cookies_stamp = cookies_stamp()

        apply_to_streamlink(self._session)

    def get_stream(self, stream: Stream):
        self._sync_cookies()

        if stream.audio_tracks:
            self._log.debug("Stream has separate audio, using HLSMuxedStream")
            return HLSMuxedStream(server=self._server, stream=stream)

        return self._get_solo_stream(stream)

    def _sync_cookies(self) -> None:
        """Pick up cookies that were edited since this session was made.

        A session is kept for as long as the proxy runs and shared by every
        stream from the same service, so a login added or taken away in
        settings would otherwise not be noticed until a restart.
        """

        stamp = cookies_stamp()

        if stamp == self._cookies_stamp:
            return

        self._log.debug("Cookies were edited, applying them to the session")

        self._cookies_stamp = stamp

        apply_to_streamlink(self._session)

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
                session_=self._session,
                stream=stream,
            )
        elif protocol == "dash":
            self._log.debug("Stream is dash, using DASHPlaylistStream")
            return DASHPlaylistStream(server=self._server, stream=stream)
        elif protocol == "dash_proxy":
            self._log.debug("Stream is dash_proxy, using DASHManifestProxy")
            return DASHManifestProxy(
                server=self._server,
                session_opts=self._stream_session,
                session_=self._session,
                url=stream.url,
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
