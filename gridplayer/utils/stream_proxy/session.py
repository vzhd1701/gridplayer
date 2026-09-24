import logging
from types import MappingProxyType

from streamlink import Streamlink

from gridplayer.models.stream import Stream, StreamFragment, StreamSessionOpts
from gridplayer.utils.network import configure_session, session_stamp
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
        "dash_proxy": DASHManifestProxy,
    }
)


class StreamSession:
    def __init__(self, stream_session: StreamSessionOpts, server):
        self._log = logging.getLogger(self.__class__.__name__)

        self._stream_session = stream_session
        self._server = server

        self._session = Streamlink()

        self._settings_stamp = session_stamp()

        self._apply_settings()

    def get_stream(self, stream: Stream):
        self._sync_settings()

        if stream.audio_tracks:
            self._log.debug("Stream has separate audio, using HLSMuxedStream")
            return HLSMuxedStream(server=self._server, stream=stream)

        return self._get_solo_stream(stream)

    def playlist_segments(
        self, stream: Stream
    ) -> tuple[StreamFragment | None, tuple[StreamFragment, ...]]:
        """The init segment and segments of an HLS playlist the host serves."""

        self._sync_settings()

        return HLSProxy(**self._relay_args(stream), stream=stream).fetch_segments()

    def _sync_settings(self) -> None:
        """Pick up settings that were edited since this session was made.

        A session is kept for as long as the proxy runs and shared by every
        stream from the same service, so a login added or taken away, or a
        proxy switched on, would otherwise not be noticed until a restart.
        """

        stamp = session_stamp()

        if stamp == self._settings_stamp:
            return

        self._log.debug("Settings were edited, applying them to the session")

        self._settings_stamp = stamp

        self._apply_settings()

    def _apply_settings(self) -> None:
        """The settings, and then what the resolver said on top of them.

        The headers a format came with go on last and stay the last word.
        A site signs an address for the user agent that asked it for one,
        so a shared default laid over that would be asking for the bytes
        as somebody else.
        """

        configure_session(self._session)

        self._session.http.headers.update(self._stream_session.session_headers)

    def _get_solo_stream(self, stream: Stream):
        wrapper = self._solo_wrapper(stream)

        self._log.debug(f"Stream is {stream.protocol}, using {type(wrapper).__name__}")

        return wrapper

    def _solo_wrapper(self, stream: Stream):
        protocol = stream.protocol

        if protocol == "hls_proxy":
            # relayed like the rest, and handed the stream as well, so that
            # its segments can be pointed back at it
            return HLSProxy(**self._relay_args(stream), stream=stream)

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
