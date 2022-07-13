import logging
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Dict, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlparse
from uuid import uuid3, uuid4

from requests import HTTPError, Response
from streamlink import StreamError

from gridplayer.models.stream import Stream
from gridplayer.utils.stream_proxy.session import StreamSession
from gridplayer.utils.stream_proxy.wrappers import HTTPStreamProxy, StreamReader


class StreamProxyServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._sessions_lock = Lock()
        self._sessions: Dict[str, StreamSession] = {}

        self._muxed_streams_lock = Lock()
        self._muxed_streams: Dict[str, Stream] = {}

        self._ns_uuid = uuid4()

    @property
    def base_url(self):
        address, port = self.server_address
        return f"http://{address}:{port}"

    def generate_id(self, token):
        return str(uuid3(self._ns_uuid, str(hash(token))))

    def add_stream(self, stream: Stream) -> str:
        session_id = self.generate_id(stream.session)

        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                self._sessions[session_id] = StreamSession(
                    stream_session=stream.session, server=self
                )

        if stream.audio_tracks:
            stream_id = self.generate_id(stream)
            with self._muxed_streams_lock:
                existing_stream = self._muxed_streams.get(stream_id)
                if existing_stream is None:
                    self._muxed_streams[stream_id] = stream

            params = {
                "stream_id": stream_id,
                "session_id": session_id,
            }
        else:
            params = {
                "url": stream.url,
                "protocol": stream.protocol,
                "session_id": session_id,
            }

        return "{0}/?{1}".format(self.base_url, urlencode(params))

    def get_session(self, session_id: str) -> StreamSession:
        with self._sessions_lock:
            return self._sessions.get(session_id)

    def get_stream(self, stream_id: str) -> Stream:
        with self._muxed_streams_lock:
            return self._muxed_streams.get(stream_id)

    def serve_forever(self, *args, **kwargs):
        self._log.info("Starting stream proxy server")

        super().serve_forever(*args, **kwargs)

    def shutdown(self):
        self._log.info("Shutting down stream proxy server")

        super().shutdown()


class ProxyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        self._log = logging.getLogger(self.__class__.__name__)

        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):  # noqa: WPS125
        message = "{0} - {1}".format(self.address_string(), format % args)
        self._log.debug(message)

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def do_GET(self):  # noqa: WPS210
        req = self

        request_headers = _filter_request_headers(dict(req.headers))

        self._log.debug(f"Received request: {req.path}\n{request_headers}")

        try:
            query = _parse_request(req.path)
        except ValueError as err:
            self._log.error(f"Invalid request: {err}")
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid request")
            return

        session_id = query.get("session_id", "")

        stream_session = self.server.get_session(session_id)

        if stream_session is None:
            self._log.error(f"Session {session_id} not found")
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        stream_id = query.get("stream_id", "")

        muxed_stream = self.server.get_stream(stream_id)

        if muxed_stream:
            stream = stream_session.get_muxed_stream(muxed_stream)
        else:
            stream = stream_session.get_stream(query["url"], query["protocol"])

        self._relay_stream(stream, request_headers)

    def _relay_stream(self, stream: HTTPStreamProxy, request_headers: Dict[str, str]):
        try:
            with StreamReader(stream, request_headers) as (response, chunks):
                self._safe_relay_response(response, chunks)

        except StreamError as e:
            if isinstance(e.err, HTTPError):
                self._safe_relay_response(e.err.response)
            else:
                self._log.error(f"Error when streaming: {e}")
                self._log.debug("Traceback", exc_info=e)
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def _safe_relay_response(
        self, response: Response, chunks: Optional[Iterable[bytes]] = None
    ):
        try:
            self._relay_response(response, chunks)
        except socket.error:
            self._log.debug("Connection closed by client")

    def _relay_response(
        self, response: Response, chunks: Optional[Iterable[bytes]] = None
    ):
        self.send_response(response.status_code, response.reason)

        for h_key, h_value in response.headers.items():
            self.send_header(h_key, h_value)

        self.end_headers()

        chunks = chunks or [response.content]

        for chunk in chunks:
            self.wfile.write(chunk)
        self.wfile.flush()


def _parse_request(path: str):
    url = urlparse(path)
    return dict(parse_qsl(url.query))


def _filter_request_headers(headers: Dict[str, str]):
    filtered_headers = {
        "host",
        "accept",
        "accept-encoding",
        "accept-language",
        "user-agent",
    }

    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in filtered_headers  # noqa: WPS221
    }
