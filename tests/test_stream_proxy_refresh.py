"""The proxy renewing stream URLs that the service stopped honouring."""

import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

import pytest
import requests

from gridplayer.models.stream import (
    HashableDict,
    Stream,
    StreamFragment,
    StreamOrigin,
    Streams,
    StreamSessionOpts,
)
from gridplayer.utils.stream_proxy.fragments import fragment_url
from gridplayer.utils.stream_proxy.server import (
    ProxyRequestHandler,
    StreamProxyServer,
    _pick_stream,
)
from gridplayer.utils.url_resolve.static import ResolvedVideo

SESSION = StreamSessionOpts(service="test", session_headers=HashableDict({}))

PAGE_URL = "http://source/page"


class UpstreamHandler(BaseHTTPRequestHandler):
    """Stands in for the CDN, which answers some URLs and refuses others."""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requested.append(self.path)

        status, body = self.server.replies.get(self.path, (404, b"missing"))

        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "video/mp4")
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


@pytest.fixture
def proxy(serving):
    def make_proxy(resolve_source=None):
        return serving(
            StreamProxyServer(
                ("127.0.0.1", 0), ProxyRequestHandler, resolve_source=resolve_source
            )
        )

    return make_proxy


def _upstream_url(server, path):
    address, port = server.server_address
    return f"http://{address}:{port}{path}"


def _query(url):
    return dict(parse_qsl(urlparse(url).query))


def _dash_stream(url, quality="best", origin=True):
    return Stream(
        url="http://source/manifest.mpd",
        protocol="dash",
        session=SESSION,
        fragments=(StreamFragment(url=url, duration=4),),
        origin=StreamOrigin(url=PAGE_URL, quality=quality) if origin else None,
    )


def _resolver(upstream, path, calls=None):
    """Stands in for the URL resolver, handing back a stream on ``path``."""

    def resolve_source(url):
        if calls is not None:
            calls.append(url)

        fresh = _dash_stream(_upstream_url(upstream, path))

        return ResolvedVideo(title="t", is_live=False, streams=Streams({"best": fresh}))

    return resolve_source


def test_a_fragment_that_expired_is_served_from_a_renewed_url(upstream, proxy):
    upstream.replies = {
        "/old/0.m4s": (403, b"expired"),
        "/new/0.m4s": (200, b"fresh segment"),
    }

    resolved = []

    server = proxy(_resolver(upstream, "/new/0.m4s", resolved))
    stream = _dash_stream(_upstream_url(upstream, "/old/0.m4s"))

    response = requests.get(server.add_stream(stream, fragment="0"), timeout=10)

    assert response.status_code == 200
    assert response.content == b"fresh segment"
    assert resolved == [PAGE_URL]
    assert upstream.requested == ["/old/0.m4s", "/new/0.m4s"]


def test_a_renewed_stream_keeps_the_id_its_playlist_points_at(upstream, proxy):
    upstream.replies = {
        "/old/0.m4s": (403, b"expired"),
        "/new/0.m4s": (200, b"fresh segment"),
    }

    server = proxy(_resolver(upstream, "/new/0.m4s"))
    stream = _dash_stream(_upstream_url(upstream, "/old/0.m4s"))

    proxy_url = server.add_stream(stream, fragment="0")
    stream_id = _query(proxy_url)["stream_id"]

    requests.get(proxy_url, timeout=10)

    assert server.get_stream(stream_id).fragments[0].url.endswith("/new/0.m4s")


def test_one_burst_of_expired_fragments_resolves_the_source_once(upstream, proxy):
    upstream.replies = {
        "/old/0.m4s": (403, b"expired"),
        "/new/0.m4s": (200, b"fresh segment"),
    }

    resolved = []

    server = proxy(_resolver(upstream, "/new/0.m4s", resolved))

    for _ in range(3):
        stream = _dash_stream(_upstream_url(upstream, "/old/0.m4s"))
        response = requests.get(server.add_stream(stream, fragment="0"), timeout=10)
        assert response.status_code == 200

    assert resolved == [PAGE_URL]


def test_a_stream_nobody_can_renew_relays_the_refusal(upstream, proxy):
    upstream.replies = {"/old/0.m4s": (403, b"expired")}

    server = proxy(None)
    stream = _dash_stream(_upstream_url(upstream, "/old/0.m4s"))

    response = requests.get(server.add_stream(stream, fragment="0"), timeout=10)

    assert response.status_code == 403
    assert upstream.requested == ["/old/0.m4s"]


def test_a_source_that_cannot_be_resolved_again_relays_the_refusal(upstream, proxy):
    upstream.replies = {"/old/0.m4s": (403, b"expired")}

    def resolve_source(url):
        raise RuntimeError("no network")

    server = proxy(resolve_source)
    stream = _dash_stream(_upstream_url(upstream, "/old/0.m4s"))

    response = requests.get(server.add_stream(stream, fragment="0"), timeout=10)

    assert response.status_code == 403


def test_a_fragment_the_stream_does_not_have_is_not_found(upstream, proxy):
    server = proxy(None)
    stream = _dash_stream(_upstream_url(upstream, "/old/0.m4s"))

    response = requests.get(server.add_stream(stream, fragment="7"), timeout=10)

    assert response.status_code == 404


def test_a_dash_playlist_serves_the_fragments_it_points_at(upstream, proxy):
    """The whole chain, from the playlist VLC asks for to the segments in it."""

    upstream.replies = {
        "/init.m4s": (200, b"init"),
        "/0.m4s": (200, b"zero"),
        "/1.m4s": (200, b"one"),
    }

    server = proxy(None)
    stream = Stream(
        url="http://source/manifest.mpd",
        protocol="dash",
        session=SESSION,
        init_fragment=StreamFragment(url=_upstream_url(upstream, "/init.m4s")),
        fragments=(
            StreamFragment(url=_upstream_url(upstream, "/0.m4s"), duration=4),
            StreamFragment(url=_upstream_url(upstream, "/1.m4s"), duration=4),
        ),
    )

    playlist = requests.get(server.add_stream(stream), timeout=10).text

    init_url = re.search(r'#EXT-X-MAP:URI="([^"]+)"', playlist).group(1)
    segment_urls = [line for line in playlist.splitlines() if line.startswith("http")]

    assert requests.get(init_url, timeout=10).content == b"init"
    assert [requests.get(url, timeout=10).content for url in segment_urls] == [
        b"zero",
        b"one",
    ]


def test_a_request_that_names_no_stream_is_a_bad_request(proxy):
    server = proxy(None)

    plain = Stream(url="http://host/video", protocol="http", session=SESSION)
    session_id = _query(server.add_stream(plain))["session_id"]

    response = requests.get(f"{server.base_url}/?session_id={session_id}", timeout=10)

    assert response.status_code == 400


def test_a_request_for_a_stream_nobody_added_is_not_found(proxy):
    server = proxy(None)

    plain = Stream(url="http://host/video", protocol="http", session=SESSION)
    session_id = _query(server.add_stream(plain))["session_id"]

    response = requests.get(
        f"{server.base_url}/?session_id={session_id}&stream_id=nope", timeout=10
    )

    assert response.status_code == 404


def test_a_stream_that_can_be_renewed_is_addressed_by_id(proxy):
    server = proxy(None)

    plain = Stream(url="http://host/video", protocol="http", session=SESSION)
    refreshable = Stream(
        url="http://host/video",
        protocol="http",
        session=SESSION,
        origin=StreamOrigin(url=PAGE_URL, quality="best"),
    )

    assert "url=" in server.add_stream(plain)
    assert "stream_id=" in server.add_stream(refreshable)


def test_fragments_are_addressed_by_position():
    stream = Stream(
        url="http://host/video",
        protocol="dash",
        init_fragment=StreamFragment(url="http://host/init"),
        fragments=(
            StreamFragment(url="http://host/0"),
            StreamFragment(url="http://host/1"),
        ),
    )

    assert fragment_url(stream, "self") == "http://host/video"
    assert fragment_url(stream, "init") == "http://host/init"
    assert fragment_url(stream, "1") == "http://host/1"
    assert fragment_url(stream, "2") is None
    assert fragment_url(stream, "-1") is None
    assert fragment_url(stream, "nonsense") is None


def test_a_renewed_video_half_is_not_handed_its_audio_tracks_back():
    audio_tracks = Streams({"high": Stream(url="http://audio", protocol="dash")})
    fresh_streams = Streams(
        {"best": Stream(url="http://video", protocol="dash", audio_tracks=audio_tracks)}
    )

    # what the proxy serves is the video on its own, as the muxed playlist
    # split it out; giving it back its audio tracks would nest one playlist
    # inside another
    served = Stream(
        url="http://video/old",
        protocol="dash",
        origin=StreamOrigin(url=PAGE_URL, quality="best"),
    )

    assert _pick_stream(fresh_streams, served).audio_tracks is None


def test_a_renewed_audio_track_is_found_by_name():
    audio_tracks = Streams(
        {
            "low": Stream(url="http://audio/low", protocol="dash"),
            "high": Stream(url="http://audio/high", protocol="dash"),
        }
    )
    fresh_streams = Streams(
        {"best": Stream(url="http://video", protocol="dash", audio_tracks=audio_tracks)}
    )

    served = Stream(
        url="http://audio/old",
        protocol="dash",
        origin=StreamOrigin(url=PAGE_URL, quality="best", audio_track="low"),
    )

    assert _pick_stream(fresh_streams, served).url == "http://audio/low"


def test_a_renewed_audio_track_that_is_gone_falls_back_to_the_best_one():
    audio_tracks = Streams({"high": Stream(url="http://audio/high", protocol="dash")})
    fresh_streams = Streams(
        {"best": Stream(url="http://video", protocol="dash", audio_tracks=audio_tracks)}
    )

    served = Stream(
        url="http://audio/old",
        protocol="dash",
        origin=StreamOrigin(url=PAGE_URL, quality="best", audio_track="vanished"),
    )

    assert _pick_stream(fresh_streams, served).url == "http://audio/high"
