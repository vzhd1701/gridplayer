"""A file the host gives slowly asked for to its end (Stream.piece_size).

YouTube gave an AV1 file asked for to its end at about its bit rate, and in
pieces of 10 MB at full speed. mpv asks for a file to its end, so the proxy
asks the host a piece at a time and answers mpv as if it were one.
"""

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from gridplayer.models.stream import HashableDict, Stream, StreamSessionOpts
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler, StreamProxyServer

BODY = bytes(range(256)) * 40
PIECE = 1000


class HostHandler(BaseHTTPRequestHandler):
    """Gives a piece asked for, or all from where it's asked for."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        asked = self.headers.get("Range")
        self.server.asked.append(asked)

        if len(self.server.asked) > self.server.refuses_after:
            self._send(HTTPStatus.FORBIDDEN, b"")
            return

        if not asked or self.server.ignores_ranges:
            self._send(HTTPStatus.OK, BODY)
            return

        start, _, end = asked.removeprefix("bytes=").partition("-")
        start = int(start)
        end = min(int(end), len(BODY) - 1) if end else len(BODY) - 1

        self._send(
            HTTPStatus.PARTIAL_CONTENT,
            BODY[start : end + 1],
            {"Content-Range": f"bytes {start}-{end}/{len(BODY)}"},
        )

    def _send(self, status, body, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")

        for name, value in (headers or {}).items():
            self.send_header(name, value)

        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


@pytest.fixture
def host(serving):
    server = ThreadingHTTPServer(("127.0.0.1", 0), HostHandler)
    server.asked = []
    server.ignores_ranges = False
    server.refuses_after = len(BODY)

    return serving(server)


@pytest.fixture
def proxy(serving):
    return serving(StreamProxyServer(("127.0.0.1", 0), ProxyRequestHandler))


def _relayed(host, proxy, piece_size=PIECE):
    address, port = host.server_address

    # as yt-dlp's come, with what to fetch them with
    stream = Stream(
        url=f"http://{address}:{port}/v.mp4",
        protocol="http",
        piece_size=piece_size,
        session=StreamSessionOpts(service="test", session_headers=HashableDict()),
    )

    return proxy.add_stream(stream)


def _get(url, asked=None):
    headers = {"Range": asked} if asked else {}

    return requests.get(url, headers=headers, timeout=5)


def test_to_its_end_it_is_asked_of_the_host_in_pieces(host, proxy):
    response = _get(_relayed(host, proxy), "bytes=100-")

    assert response.status_code == 206
    assert response.headers["Content-Range"] == f"bytes 100-{len(BODY) - 1}/{len(BODY)}"
    assert response.headers["Content-Length"] == str(len(BODY) - 100)
    assert response.content == BODY[100:]

    starts = range(100, len(BODY), PIECE)
    assert host.asked == [f"bytes={at}-{at + PIECE - 1}" for at in starts]


def test_asked_for_with_no_range_it_is_the_whole_file(host, proxy):
    response = _get(_relayed(host, proxy))

    assert response.status_code == 200
    assert "Content-Range" not in response.headers
    assert response.content == BODY
    assert len(host.asked) == -(-len(BODY) // PIECE)


def test_a_piece_asked_for_is_asked_for_as_it_is(host, proxy):
    response = _get(_relayed(host, proxy), "bytes=10-5009")

    assert response.content == BODY[10:5010]
    assert host.asked == ["bytes=10-5009"]


def test_a_file_the_host_gives_whole_is_asked_for_as_it_is(host, proxy):
    response = _get(_relayed(host, proxy, piece_size=None), "bytes=100-")

    assert response.content == BODY[100:]
    assert host.asked == ["bytes=100-"]


def test_a_host_that_gives_no_pieces_is_relayed_as_it_answers(host, proxy):
    host.ignores_ranges = True

    response = _get(_relayed(host, proxy), "bytes=0-")

    assert response.status_code == 200
    assert response.content == BODY
    assert len(host.asked) == 1


def test_a_piece_refused_part_way_cuts_the_answer_short(host, proxy):
    # the player sees it end early, and asks again from where it got to
    host.refuses_after = 2

    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        _get(_relayed(host, proxy), "bytes=0-")

    assert host.asked == ["bytes=0-999", "bytes=1000-1999", "bytes=2000-2999"]
