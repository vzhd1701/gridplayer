import dataclasses
import logging
import time
from bisect import bisect_right
from collections.abc import Iterable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import accumulate
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
from uuid import uuid3, uuid4

from requests import HTTPError, Response
from streamlink import StreamError

from gridplayer.models.stream import Stream, StreamFragment, StreamOrigin, Streams
from gridplayer.utils.stream_proxy.fragments import fragment_stream
from gridplayer.utils.stream_proxy.session import StreamSession
from gridplayer.utils.stream_proxy.wrappers import HTTPStreamProxy, StreamReader

# a signed URL that has run out answers like this, on every request, forever
EXPIRED_STATUSES = frozenset(
    {
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.GONE,
    }
)

# where a DASH segment lands, once the manifest has been pointed here. It
# cannot go through the query string the rest of the proxy uses: a player
# resolves a segment against the base it was given, and resolving a
# relative URL against one with a query throws the query away
DASH_RELAY_PREFIX = "/dash/"

# a source is only worth resolving again once per burst: every fragment in
# flight fails at the same moment, and they all want the same fresh URLs
REFRESH_COOLDOWN = 10.0

# dropped connections and hiccups on the way to the CDN are common enough
# that giving up on the first one drops frames for no reason
TRANSIENT_RETRIES = 2
TRANSIENT_RETRY_DELAY = 0.5


@dataclasses.dataclass
class RelayFailure:
    """Why a stream could not be relayed.

    A response means the host answered and turned us away. No response means
    the stream broke on the way there, which is the kind of thing that passes.
    """

    response: Response | None = None

    @property
    def is_transient(self) -> bool:
        return self.response is None

    @property
    def is_expired(self) -> bool:
        return (
            self.response is not None and self.response.status_code in EXPIRED_STATUSES
        )


class StreamProxyServer(ThreadingHTTPServer):
    def __init__(self, *args, resolve_source=None, **kwargs):
        super().__init__(*args, **kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._sessions_lock = Lock()
        self._sessions: dict[str, StreamSession] = {}

        self._streams_lock = Lock()
        self._streams: dict[str, Stream] = {}

        self._bases_lock = Lock()
        self._bases: dict[str, tuple[str, str]] = {}

        # resolving a source again is slow, so one thread does it while the
        # rest of the burst waits and then reuses the result
        self._resolve_source = resolve_source
        self._refresh_lock = Lock()
        self._refresh_locks: dict[str, Lock] = {}
        self._refreshed: dict[str, tuple[float, Streams | None]] = {}

        self._ns_uuid = uuid4()

    @property
    def base_url(self):
        address, port = self.server_address
        return f"http://{address}:{port}"

    def generate_id(self, token):
        return str(uuid3(self._ns_uuid, str(hash(token))))

    def add_stream(self, stream: Stream, fragment: str | None = None) -> str:
        session_id = self._add_session(stream.session)

        is_by_id = fragment is not None or stream.is_complex or stream.is_refreshable

        if is_by_id:
            # audio tracks and fragment lists do not fit into a query string,
            # and a stream that may be resolved again has to stay reachable
            # under the same id once its URLs have been replaced
            params = {
                "stream_id": self._add_stream(stream),
                "session_id": session_id,
            }

            if fragment is not None:
                params["fragment"] = fragment
        else:
            params = {
                "url": stream.url,
                "protocol": stream.protocol,
                "session_id": session_id,
            }

        return f"{self.base_url}/?{urlencode(params)}"

    def add_fragments(self, stream: Stream, fragments: Iterable[str]) -> list[str]:
        """URLs of ours for many fragments of one stream.

        The same as asking add_stream for each, but the stream is looked up
        once: a long video has thousands of segments, and hashing a list of
        them once per segment takes seconds.
        """

        params = {
            "stream_id": self._add_stream(stream),
            "session_id": self._add_session(stream.session),
        }

        return [
            f"{self.base_url}/?{urlencode({**params, 'fragment': fragment})}"
            for fragment in fragments
        ]

    def add_base(self, base_url: str, stream_session) -> str:
        """A URL of ours that anything under `base_url` can be asked for.

        DASH names its segments with a template that only the player can
        fill in, so there is no list of them to register the way a
        playlist's segments are. What gets registered is where they will
        be, and the player builds the rest of the name itself.
        """

        session_id = self._add_session(stream_session)

        base_id = self.generate_id((base_url, session_id))

        with self._bases_lock:
            self._bases[base_id] = (base_url, session_id)

        return f"{self.base_url}{DASH_RELAY_PREFIX}{base_id}/"

    def get_base(self, base_id: str) -> tuple[str, str] | None:
        with self._bases_lock:
            return self._bases.get(base_id)

    def dash_query(self, path: str) -> dict[str, str] | None:
        """What a relayed DASH segment asks for, put the way the rest is put.

        The player builds these out of the manifest's own templates, so
        what arrives is a base handed out earlier with whatever a
        template came to underneath it.
        """

        if not path.startswith(DASH_RELAY_PREFIX):
            return None

        base_id, _, tail = path.removeprefix(DASH_RELAY_PREFIX).partition("/")

        base = self.get_base(base_id)

        if base is None:
            raise LookupError(f"Base {base_id} not found")

        base_url, session_id = base

        return {
            "url": urljoin(base_url, tail),
            "protocol": "http",
            "session_id": session_id,
        }

    def get_session(self, session_id: str) -> StreamSession:
        with self._sessions_lock:
            return self._sessions.get(session_id)

    def get_stream(self, stream_id: str) -> Stream | None:
        with self._streams_lock:
            return self._streams.get(stream_id)

    def refresh_stream(
        self, stream_id: str, stale: Stream | None = None
    ) -> Stream | None:
        """Replace a stream's expired URLs with freshly resolved ones.

        The stream keeps its id, because the playlist VLC is playing points
        at that id and there is no way to hand it a different one.

        `stale` is the stream as the caller found it before its request was
        refused. VLC asks for more than one segment at a time, and they all
        fail together; once one of them has renewed the stream, the rest
        only have to ask again.
        """

        stream = self.get_stream(stream_id)

        if stream is None or stream.origin is None or self._resolve_source is None:
            return None

        if stale is not None and stream != stale:
            self._log.debug("Stream was renewed in the meantime")
            return stream

        streams = self._refresh_source(stream.origin)

        if streams is None:
            return None

        fresh_stream = _pick_stream(streams, stream)

        if fresh_stream is None:
            self._log.warning(f"Resolved source has no {stream.origin.quality} stream")
            return None

        fresh_stream = dataclasses.replace(fresh_stream, origin=stream.origin)

        if _is_playlist_segments(stream):
            fresh_stream = self._with_playlist_segments(stream, fresh_stream)

            if fresh_stream is None:
                return None

        if fresh_stream == stream:
            # a fragmented stream keeps its manifest URL and renews only the
            # fragment list, so there is no one field to judge this by
            self._log.debug("Resolved source gave back the stream unchanged")
            return None

        with self._streams_lock:
            self._streams[stream_id] = fresh_stream

        return fresh_stream

    def serve_forever(self, *args, **kwargs):
        self._log.info("Starting stream proxy server")

        super().serve_forever(*args, **kwargs)

    def shutdown(self):
        self._log.info("Shutting down stream proxy server")

        super().shutdown()

    def _add_session(self, stream_session) -> str:
        session_id = self.generate_id(stream_session)

        with self._sessions_lock:
            if self._sessions.get(session_id) is None:
                self._sessions[session_id] = StreamSession(
                    stream_session=stream_session, server=self
                )

        return session_id

    def _add_stream(self, stream: Stream) -> str:
        stream_id = self.generate_id(stream)

        with self._streams_lock:
            if self._streams.get(stream_id) is None:
                self._streams[stream_id] = stream

        return stream_id

    def _refresh_source(self, origin: StreamOrigin) -> Streams | None:
        with self._refresh_lock:
            source_lock = self._refresh_locks.setdefault(origin.url, Lock())

        with source_lock:
            refreshed_at, streams = self._refreshed.get(origin.url, (0.0, None))

            if time.monotonic() - refreshed_at < REFRESH_COOLDOWN:
                self._log.debug("Reusing the source resolved a moment ago")
                return streams

            streams = self._resolve_streams(origin.url)

            self._refreshed[origin.url] = (time.monotonic(), streams)

            return streams

    def _resolve_streams(self, url: str) -> Streams | None:
        self._log.debug(f"Resolving {url} again to renew expired stream URLs")

        try:
            resolved = self._resolve_source(url)
        except Exception:
            self._log.exception("Failed to resolve source again")
            return None

        if resolved is None:
            self._log.warning("Nothing was able to resolve the source again")
            return None

        return resolved.streams

    def _with_playlist_segments(self, stream: Stream, fresh: Stream) -> Stream | None:
        """The renewed stream with the segments of its own playlist.

        Resolving the source again only gives the playlist's new URL. The
        segments VLC is asking for are listed in that playlist, so it has
        to be fetched, with the renewed stream's own cookies and headers.
        """

        if fresh.session is None:
            return None

        session = self.get_session(self._add_session(fresh.session))

        try:
            init_fragment, fragments = session.playlist_segments(fresh)
        except Exception:
            self._log.exception("Failed to fetch the renewed playlist")
            return None

        if not fragments:
            self._log.warning("Renewed playlist has no segments")
            return None

        return dataclasses.replace(
            fresh,
            fragments=_realign(stream.fragments, fragments),
            init_fragment=init_fragment,
        )


def _is_playlist_segments(stream: Stream) -> bool:
    """A host's HLS playlist, served to VLC segment by segment by position."""

    return stream.protocol == "hls_proxy" and stream.fragments is not None


def _realign(
    old: tuple[StreamFragment, ...], new: tuple[StreamFragment, ...]
) -> tuple[StreamFragment, ...]:
    """Line renewed segments up with the positions VLC already has.

    VLC holds on to the playlist it was given and asks for its segments
    by their place in it. A source resolved again can hand out a playlist
    cut up differently, and then the same place is a different moment in
    the video, so each old segment is matched to the new one that plays
    where it started.
    """

    if len(old) == len(new):
        return new

    starts = list(accumulate((fragment.duration for fragment in new), initial=0.0))

    aligned = []
    start = 0.0

    for fragment in old:
        # a hair past the start, so that one landing on a boundary is not
        # taken for the end of the segment before it
        idx = bisect_right(starts, start + 1e-3) - 1
        aligned.append(new[min(max(idx, 0), len(new) - 1)])
        start += fragment.duration

    return tuple(aligned)


def _pick_stream(streams: Streams, stream: Stream) -> Stream | None:
    """Find the freshly resolved counterpart of a stream we already serve.

    The shape has to survive the trip: the video half of a muxed stream was
    handed over without its audio tracks, and serving it with them again
    would turn a plain representation back into a playlist of playlists.
    """

    origin = stream.origin

    quality = streams.by_quality(origin.quality)

    if quality is None:
        return None

    _, fresh_stream = quality

    if origin.audio_track is not None:
        return _pick_audio_track(fresh_stream, origin.audio_track)

    if stream.audio_tracks is None and fresh_stream.audio_tracks is not None:
        return dataclasses.replace(fresh_stream, audio_tracks=None)

    if stream.audio_tracks and fresh_stream.audio_tracks:
        return dataclasses.replace(
            fresh_stream,
            audio_tracks=_same_audio_languages(stream, fresh_stream),
        )

    return fresh_stream


def _same_audio_languages(stream: Stream, fresh_stream: Stream) -> Streams:
    """Keep serving the languages we were serving before the renewal.

    What we were handed had already been narrowed to the one the viewer
    is listening to, where resolving the source again offers every one of
    them over.
    """

    languages = {track.language for _, track in stream.audio_tracks.items()}

    kept = {
        name: track
        for name, track in fresh_stream.audio_tracks.items()
        if track.language in languages
    }

    return Streams(kept) if kept else fresh_stream.audio_tracks


def _pick_audio_track(stream: Stream, name: str) -> Stream | None:
    if not stream.audio_tracks:
        return None

    if name in stream.audio_tracks:
        return stream.audio_tracks[name]

    best_audio = stream.audio_tracks.best

    return best_audio[1] if best_audio else None


class ProxyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        self._log = logging.getLogger(self.__class__.__name__)

        self._is_response_started = False
        self._transient_retries = TRANSIENT_RETRIES
        self._is_refresh_allowed = True

        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        message = f"{self.address_string()} - {format % args}"
        self._log.debug(message)

    def handle_one_request(self):
        self._is_response_started = False
        self._transient_retries = TRANSIENT_RETRIES
        self._is_refresh_allowed = True

        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def do_GET(self):
        req = self

        request_headers = _filter_request_headers(dict(req.headers))

        self._log.debug(f"Received request: {req.path}\n{request_headers}")

        try:
            query = self.server.dash_query(req.path) or _parse_request(req.path)
        except ValueError as err:
            self._log.error(f"Invalid request: {err}")
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request")
            return
        except LookupError as err:
            self._log.error(f"Cannot serve stream: {err}")
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        session_id = query.get("session_id", "")

        stream_session = self.server.get_session(session_id)

        if stream_session is None:
            self._log.error(f"Session {session_id} not found")
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        self._serve_stream(stream_session, query, request_headers)

    def _serve_stream(self, stream_session, query, request_headers):
        stream_id = query.get("stream_id", "")

        while True:
            # what was stored when this try began, to tell whether someone
            # else renewed it while this try was being refused
            stored = self.server.get_stream(stream_id) if stream_id else None

            try:
                stream_params = self._stream_params(stream_id, query)
            except ValueError as err:
                self._log.error(f"Invalid request: {err}")
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request")
                return
            except LookupError as err:
                self._log.error(f"Cannot serve stream: {err}")
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            try:
                stream = stream_session.get_stream(stream_params)
            except RuntimeError as err:
                self._log.error(f"Cannot handle stream: {err}")
                self.send_error(HTTPStatus.BAD_REQUEST)
                return

            failure = self._relay_stream(stream, request_headers)

            if failure is None:
                return

            if not self._wait_to_retry(failure, stream_id, stored):
                break

        self._relay_failure(failure)

    def _wait_to_retry(
        self, failure: RelayFailure, stream_id: str, stored: Stream | None
    ) -> bool:
        """Get ready to ask for the stream again, if that could go any better."""

        if self._is_response_started:
            # the client is already reading a body, so there is no starting
            # over without handing it two responses in a row
            return False

        if failure.is_expired and self._is_refresh_allowed:
            self._is_refresh_allowed = False

            if self.server.refresh_stream(stream_id, stale=stored) is not None:
                self._log.debug("Stream URLs renewed, retrying request")
                return True

        if failure.is_transient and self._transient_retries > 0:
            self._transient_retries -= 1

            self._log.debug("Transient stream error, retrying request")
            time.sleep(TRANSIENT_RETRY_DELAY)
            return True

        return False

    def _stream_params(self, stream_id: str, query: dict[str, str]) -> Stream:
        if not stream_id:
            if not query.get("url") or not query.get("protocol"):
                raise ValueError(f"Incomplete request: {self.path}")

            return Stream(url=query["url"], protocol=query["protocol"])

        stream = self.server.get_stream(stream_id)

        if stream is None:
            raise LookupError(f"Stream {stream_id} not found")

        fragment = query.get("fragment")

        if fragment is None:
            return stream

        return fragment_stream(stream, fragment)

    def _relay_failure(self, failure: RelayFailure) -> None:
        if self._is_response_started:
            # the client already has a response, or what there was of one
            self.close_connection = True
            return

        if failure.response is not None:
            self._safe_relay_response(failure.response)
            return

        self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def _relay_stream(
        self, stream: HTTPStreamProxy, request_headers: dict[str, str]
    ) -> RelayFailure | None:
        """Relay a stream, or report why it could not be relayed.

        Nothing is sent to the client on failure: what to do about it depends
        on whether the stream is worth asking for again.
        """

        try:
            with StreamReader(stream, request_headers) as (response, chunks):
                self._safe_relay_response(response, chunks)

        except StreamError as e:
            return self._failure_from_error(e)

        return None

    def _failure_from_error(self, err: StreamError) -> RelayFailure:
        if isinstance(err.err, HTTPError) and err.err.response is not None:
            self._log.debug(f"Stream answered with {err.err.response.status_code}")

            return RelayFailure(response=err.err.response)

        self._log.error(f"Error when streaming: {err}")
        self._log.debug("Traceback", exc_info=err)

        return RelayFailure()

    def _safe_relay_response(
        self, response: Response, chunks: Iterable[bytes] | None = None
    ):
        try:
            self._relay_response(response, chunks)
        except OSError:
            self._log.debug("Connection closed by client")

    def _relay_response(
        self, response: Response, chunks: Iterable[bytes] | None = None
    ):
        self.send_response(response.status_code, response.reason)

        self._is_response_started = True

        for h_key, h_value in _filter_response_headers(dict(response.headers)).items():
            self.send_header(h_key, h_value)

        self.end_headers()

        chunks = chunks or [response.content]

        if response.headers.get("transfer-encoding") == "chunked":
            for chunk in chunks:
                self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.write(b"0\r\n\r\n")
        else:
            for chunk in chunks:
                self.wfile.write(chunk)

        self.wfile.flush()


def _parse_request(path: str):
    url = urlparse(path)
    return dict(parse_qsl(url.query))


def _filter_request_headers(headers: dict[str, str]):
    filtered_headers = {
        "host",
        "accept",
        "accept-encoding",
        "accept-language",
        "user-agent",
    }

    return {k: v for k, v in headers.items() if k.lower() not in filtered_headers}


def _filter_response_headers(headers: dict[str, str]):
    filtered_headers = {
        "server",
        "date",
    }

    return {k: v for k, v in headers.items() if k.lower() not in filtered_headers}
