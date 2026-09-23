from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from streamlink import Streamlink

from gridplayer.utils.url_resolve.stream_detect import is_hls_live_stream


def _playlist(header: str = "", count: int = 40, end: str = "") -> str:
    """More segments than the header check reads, unless told otherwise."""

    segments = "".join(f"#EXTINF:4.0,\nseg{n}.ts\n" for n in range(count))

    return f"#EXTM3U\n#EXT-X-TARGETDURATION:4\n{header}{segments}{end}"


@pytest.fixture
def playlist_url(serving):
    served = {}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            body = served["playlist"].encode("utf-8")

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            """Quiet, the test is not interested"""

    server = serving(ThreadingHTTPServer(("127.0.0.1", 0), Handler))
    address, port = server.server_address

    def _serve(playlist: str) -> str:
        served["playlist"] = playlist
        return f"http://{address}:{port}/index.m3u8"

    return _serve


def _is_live(playlist_url, playlist: str) -> bool:
    return is_hls_live_stream(playlist_url(playlist), session=Streamlink())


def test_a_window_numbered_past_zero_is_live(playlist_url):
    assert _is_live(playlist_url, _playlist("#EXT-X-MEDIA-SEQUENCE:1000\n"))


def test_a_finished_playlist_numbered_from_one_is_not_live(playlist_url):
    """Its end is the only thing that gives it away.

    Some hosts number a finished video from one and leave out the
    playlist type, so the header reads exactly like a live window.
    """

    playlist = _playlist("#EXT-X-MEDIA-SEQUENCE:1\n", end="#EXT-X-ENDLIST\n")

    assert not _is_live(playlist_url, playlist)


def test_a_short_finished_playlist_is_not_live(playlist_url):
    playlist = _playlist("#EXT-X-MEDIA-SEQUENCE:7\n", count=2, end="#EXT-X-ENDLIST\n")

    assert not _is_live(playlist_url, playlist)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("#EXT-X-TWITCH-LIVE-SEQUENCE:5\n#EXT-X-MEDIA-SEQUENCE:0\n", True),
        ("#EXT-X-PLAYLIST-TYPE:VOD\n#EXT-X-MEDIA-SEQUENCE:1\n", False),
        ("#EXT-X-MEDIA-SEQUENCE:0\n", False),
        ("", False),
    ],
)
def test_what_the_header_settles_on_its_own(playlist_url, header, expected):
    assert _is_live(playlist_url, _playlist(header)) is expected
