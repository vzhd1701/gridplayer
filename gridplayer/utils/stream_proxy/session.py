import logging
from types import MappingProxyType

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

# wrappers that fetch their URL from the host themselves, and so are all
# built out of the same session, headers and cookies
RELAYED_PROTOCOLS = MappingProxyType(
    {
        "http": HTTPStreamProxy,
        "hls_proxy": HLSProxy,
        "dash_proxy": DASHManifestProxy,
    }
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
        wrapper = self._solo_wrapper(stream)

        self._log.debug(f"Stream is {stream.protocol}, using {type(wrapper).__name__}")

        return wrapper

    def _solo_wrapper(self, stream: Stream):
        protocol = stream.protocol

        if protocol in RELAYED_PROTOCOLS:
            return RELAYED_PROTOCOLS[protocol](**self._relay_args(stream))

        if protocol == "http_hls":
            return HTTPPlaylistStream(
                server=self._server,
                session_=self._session,
                stream=stream,
            )

        if protocol == "dash":
            return DASHPlaylistStream(server=self._server, stream=stream)

        if protocol == "hls":
            return HLSProxyLive(
                session=self._session, url=stream.url, force_restart=True
            )

        raise RuntimeError(f"Cannot handle protocol {protocol}")

    def _relay_args(self, stream: Stream) -> dict:
        """What a wrapper that goes to the host for itself is built with.

        The rest are handed a stream and serve a playlist out of what is
        already known about it, so they need no session to fetch with.
        """

        return {
            "server": self._server,
            "session_opts": self._stream_session,
            "session_": self._session,
            "url": stream.url,
        }
