"""A plain file behind a login, relayed by the proxy.

libVLC has no option for a cookie -- its http access offers a referrer and
a user agent and nothing else -- so a URL that needs one cannot be handed
over. It is still a file once the proxy is in the way, so the byte ranges
a seek asks for have to survive the trip.
"""

import time
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests

from gridplayer.utils import cookies as cookies_module
from gridplayer.utils.cookies import CookieStore
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler, StreamProxyServer
from gridplayer.utils.url_resolve.resolver_base import DirectResolver

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"

LOGIN = "SID=abc"

BODY = bytes(range(256)) * 64


class VaultHandler(BaseHTTPRequestHandler):
    """Stands in for a host that serves nobody who is not logged in."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.seen.append(dict(self.headers))

        if self.headers.get("Cookie") != LOGIN:
            self.send_response(HTTPStatus.FORBIDDEN)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        wanted = _wanted_range(self.headers.get("Range"))

        if wanted is None:
            self._send(HTTPStatus.OK, BODY)
            return

        start, end = wanted

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


def _wanted_range(header):
    if not header:
        return None

    start, _, end = header.removeprefix("bytes=").partition("-")

    return int(start), int(end) if end else len(BODY) - 1


class _FakeSettings:
    def __init__(self, values):
        self._values = values

    def get(self, key):
        return self._values[key]


@contextmanager
def _serving(server):
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def settings(monkeypatch):
    values = {"cookies/enabled": True, "cookies/allow_update": False}

    monkeypatch.setattr(cookies_module, "Settings", lambda: _FakeSettings(values))

    return values


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A jar holding a login for the host the test stands up."""

    forever = int(time.time()) + 10000

    path = tmp_path / "cookies.txt"
    path.write_text(
        f"{NETSCAPE_HEADER}127.0.0.1\tFALSE\t/\tFALSE\t{forever}\tSID\tabc\n",
        encoding="utf-8",
    )

    store = CookieStore(path)
    monkeypatch.setattr(cookies_module, "cookie_store", lambda: store)

    return store


@pytest.fixture
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), VaultHandler)
    server.seen = []

    with _serving(server):
        yield server


@pytest.fixture
def proxy():
    server = StreamProxyServer(("127.0.0.1", 0), ProxyRequestHandler)

    with _serving(server):
        yield server


def _relayed(upstream, proxy):
    """The URL VLC would be given for a file on the upstream host."""

    address, port = upstream.server_address

    stream = DirectResolver(f"http://{address}:{port}/vault/video.mp4").streams[
        "generic"
    ]

    assert stream.protocol == "http"

    return proxy.add_stream(stream)


class TestTheRelay:
    def test_the_login_is_attached_on_the_way_out(
        self, settings, store, upstream, proxy
    ):
        """Without it the host answers 403, which is the whole problem."""

        response = requests.get(_relayed(upstream, proxy), timeout=5)

        assert response.status_code == 200
        assert response.content == BODY

    def test_a_seek_gets_the_bytes_it_asked_for(self, settings, store, upstream, proxy):
        """VLC seeks with a Range, and gets nowhere if the relay eats it."""

        response = requests.get(
            _relayed(upstream, proxy), headers={"Range": "bytes=100-199"}, timeout=5
        )

        assert response.status_code == 206
        assert response.content == BODY[100:200]
        assert response.headers["Content-Range"] == f"bytes 100-199/{len(BODY)}"

    def test_what_vlc_sends_is_not_overwritten_by_the_login(
        self, settings, store, upstream, proxy
    ):
        """One request, carrying both the cookie and what was asked for."""

        requests.get(
            _relayed(upstream, proxy), headers={"Range": "bytes=0-9"}, timeout=5
        )

        sent = upstream.seen[-1]

        assert sent["Cookie"] == LOGIN
        assert sent["Range"] == "bytes=0-9"
