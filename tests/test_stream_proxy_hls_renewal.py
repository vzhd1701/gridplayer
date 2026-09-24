"""The proxy renewing segments of an HLS playlist the host wrote.

The segments of such a playlist are signed URLs, like everything else a
service hands out, and a host may stop honouring them partway through a
video, or refuse the ones it signed this time from the very start. VLC
holds on to the playlist it was given, so the only thing to renew is what
a place in that playlist stands for.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

import pytest
import requests

from gridplayer.models.stream import (
    HashableDict,
    Stream,
    StreamOrigin,
    Streams,
    StreamSessionOpts,
)
from gridplayer.utils.stream_proxy.server import ProxyRequestHandler, StreamProxyServer
from gridplayer.utils.url_resolve.static import ResolvedVideo

SESSION = StreamSessionOpts(service="test", session_headers=HashableDict({}))

PAGE_URL = "http://source/page"


def _playlist(*segments, durations=None, init=None, is_finished=True) -> bytes:
    durations = durations or [4.0] * len(segments)

    lines = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-TARGETDURATION:4"]

    if is_finished:
        lines += ["#EXT-X-PLAYLIST-TYPE:VOD"]

    if init:
        lines += [f'#EXT-X-MAP:URI="{init}"']

    for segment, duration in zip(segments, durations, strict=True):
        lines += [f"#EXTINF:{duration},", segment]

    if is_finished:
        lines += ["#EXT-X-ENDLIST"]

    return "\n".join(lines).encode()


class UpstreamHandler(BaseHTTPRequestHandler):
    """Stands in for the CDN, which answers some URLs and refuses others."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requested.append(self.path)

        status, body = self.server.replies.get(self.path, (404, b"missing"))

        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet, the test is not interested"""


@pytest.fixture
def upstream(serving):
    server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    server.replies = {}
    server.requested = []

    return serving(server)


def _url(server, path):
    address, port = server.server_address
    return f"http://{address}:{port}{path}"


def _playlist_stream(upstream, path, origin=True):
    return Stream(
        url=_url(upstream, path),
        protocol="hls_proxy",
        session=SESSION,
        origin=StreamOrigin(url=PAGE_URL, quality="best") if origin else None,
    )


@pytest.fixture
def resolved():
    return []


@pytest.fixture
def proxy(serving, upstream, resolved):
    """A proxy whose source resolves anew to the playlist at /new/."""

    def resolve_source(url):
        resolved.append(url)

        fresh = _playlist_stream(upstream, "/new/index.m3u8")

        return ResolvedVideo(title="t", is_live=False, streams=Streams({"best": fresh}))

    return serving(
        StreamProxyServer(
            ("127.0.0.1", 0), ProxyRequestHandler, resolve_source=resolve_source
        )
    )


def _served_playlist(proxy, stream) -> list[str]:
    """What VLC is handed: the playlist, and its segment and init URLs."""

    text = requests.get(proxy.add_stream(stream), timeout=10).text

    urls = [line for line in text.splitlines() if not line.startswith("#")]

    urls += [
        line.split('URI="')[1].split('"')[0]
        for line in text.splitlines()
        if line.startswith("#EXT-X-MAP")
    ]

    return urls


def _query(url):
    return dict(parse_qsl(urlparse(url).query))


def test_a_finished_playlist_points_at_its_segments_by_place(upstream, proxy):
    upstream.replies = {"/old/index.m3u8": (200, _playlist("0.ts", "1.ts"))}

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))

    assert [_query(url).get("fragment") for url in segments] == ["0", "1"]
    assert not any("url" in _query(url) for url in segments)


def test_a_refused_segment_is_served_from_the_renewed_playlist(
    upstream, proxy, resolved
):
    """The case that left a YouTube video on "Buffering": refused at once."""

    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.ts", "1.ts")),
        "/old/0.ts": (403, b""),
        "/new/index.m3u8": (200, _playlist("0.ts", "1.ts")),
        "/new/0.ts": (200, b"fresh zero"),
    }

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))

    response = requests.get(segments[0], timeout=10)

    assert response.status_code == 200
    assert response.content == b"fresh zero"
    assert resolved == [PAGE_URL]
    assert upstream.requested == [
        "/old/index.m3u8",
        "/old/0.ts",
        "/new/index.m3u8",
        "/new/0.ts",
    ]


def test_the_segments_after_it_come_from_the_renewed_playlist_too(upstream, proxy):
    """Renewed once, not once per segment: the old URLs are not tried again."""

    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.ts", "1.ts")),
        "/old/0.ts": (403, b""),
        "/new/index.m3u8": (200, _playlist("0.ts", "1.ts")),
        "/new/0.ts": (200, b"fresh zero"),
        "/new/1.ts": (200, b"fresh one"),
    }

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))

    requests.get(segments[0], timeout=10)

    assert requests.get(segments[1], timeout=10).content == b"fresh one"
    assert "/old/1.ts" not in upstream.requested


def test_a_renewed_playlist_cut_up_differently_is_lined_up_by_time(upstream, proxy):
    """The same place in it would be another moment of the video."""

    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.ts", "1.ts")),
        "/old/1.ts": (403, b""),
        "/new/index.m3u8": (
            200,
            _playlist("a.ts", "b.ts", "c.ts", "d.ts", durations=[2.0] * 4),
        ),
        "/new/c.ts": (200, b"from four seconds in"),
    }

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))

    assert requests.get(segments[1], timeout=10).content == b"from four seconds in"


def test_the_init_segment_is_renewed_with_the_rest(upstream, proxy):
    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.m4s", init="init.mp4")),
        "/old/init.mp4": (403, b""),
        "/new/index.m3u8": (200, _playlist("0.m4s", init="init.mp4")),
        "/new/init.mp4": (200, b"fresh init"),
    }

    *_, init_url = _served_playlist(
        proxy, _playlist_stream(upstream, "/old/index.m3u8")
    )

    assert _query(init_url)["fragment"] == "init"
    assert requests.get(init_url, timeout=10).content == b"fresh init"


def test_a_live_playlist_keeps_pointing_at_urls(upstream, proxy):
    """A live window slides, so a place in it does not stay put.

    VLC fetches it again every few seconds instead, and each of those
    fetches is renewed as a whole.
    """

    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.ts", "1.ts", is_finished=False))
    }

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))

    assert all("url" in _query(url) for url in segments)


def test_a_playlist_that_cannot_be_resolved_again_keeps_pointing_at_urls(
    upstream, proxy
):
    upstream.replies = {"/old/index.m3u8": (200, _playlist("0.ts"))}

    segments = _served_playlist(
        proxy, _playlist_stream(upstream, "/old/index.m3u8", origin=False)
    )

    assert all("url" in _query(url) for url in segments)


def test_a_renewed_playlist_that_is_refused_too_relays_the_refusal(upstream, proxy):
    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.ts")),
        "/old/0.ts": (403, b""),
        "/new/index.m3u8": (403, b""),
    }

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))

    assert requests.get(segments[0], timeout=10).status_code == 403


def test_a_stream_renewed_meanwhile_is_not_resolved_again(upstream, proxy, resolved):
    """VLC asks for more than one segment at a time, and they fail together.

    The first to be refused renews the stream; the rest were refused the
    old URLs and only have to ask for the new ones.
    """

    upstream.replies = {
        "/old/index.m3u8": (200, _playlist("0.ts")),
        "/old/0.ts": (403, b""),
        "/new/index.m3u8": (200, _playlist("0.ts")),
        "/new/0.ts": (200, b"fresh zero"),
    }

    segments = _served_playlist(proxy, _playlist_stream(upstream, "/old/index.m3u8"))
    stream_id = _query(segments[0])["stream_id"]
    stale = proxy.get_stream(stream_id)

    requests.get(segments[0], timeout=10)

    renewed = proxy.refresh_stream(stream_id, stale=stale)

    assert renewed is proxy.get_stream(stream_id)
    assert renewed.fragments[0].url.endswith("/new/0.ts")
    assert resolved == [PAGE_URL]
