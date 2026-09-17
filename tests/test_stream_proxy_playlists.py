import struct
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from gridplayer.models.stream import (
    HashableDict,
    Stream,
    StreamFragment,
    Streams,
    StreamSessionOpts,
)
from gridplayer.utils.stream_proxy.m3u8 import (
    build_master_playlist,
    build_media_playlist,
)
from gridplayer.utils.stream_proxy.mp4 import is_fragmented, parse_segment_index
from gridplayer.utils.stream_proxy.server import (
    ProxyRequestHandler,
    StreamProxyServer,
)
from gridplayer.utils.stream_proxy.wrappers import (
    M3U8_CONTENT_TYPE,
    DASHPlaylistStream,
    HLSMuxedStream,
    HTTPPlaylistStream,
)

SESSION = StreamSessionOpts(service="test", session_headers=HashableDict({}))


class FakeServer:
    """Hands out a stable fake proxy URL for every stream it is given."""

    def __init__(self):
        self.streams = []
        self.fragments = []

    def add_stream(self, stream: Stream, fragment: str | None = None) -> str:
        self.streams.append(stream)

        if fragment is None:
            return f"http://proxy/{len(self.streams)}"

        self.fragments.append(fragment)
        return f"http://proxy/fragment/{fragment}"


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def _sidx(segments, timescale=1000, first_offset=0) -> bytes:
    payload = struct.pack(">BBBB", 0, 0, 0, 0)
    payload += struct.pack(">II", 1, timescale)
    payload += struct.pack(">II", 0, first_offset)
    payload += struct.pack(">HH", 0, len(segments))

    for size, duration_ms in segments:
        payload += struct.pack(">III", size, duration_ms, 0)

    return _box(b"sidx", payload)


def test_media_playlist_lists_every_segment():
    playlist = build_media_playlist(
        segments=[
            StreamFragment(url="http://seg/1", duration=4),
            StreamFragment(url="http://seg/2", duration=2.5),
        ],
        init_segment=StreamFragment(url="http://init"),
    )

    assert playlist.splitlines() == [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-TARGETDURATION:4",
        "#EXT-X-MEDIA-SEQUENCE:0",
        '#EXT-X-MAP:URI="http://init"',
        "#EXTINF:4.000,",
        "http://seg/1",
        "#EXTINF:2.500,",
        "http://seg/2",
        "#EXT-X-ENDLIST",
    ]


def test_media_playlist_keeps_byte_ranges():
    playlist = build_media_playlist(
        segments=[StreamFragment(url="http://file", duration=2, byterange="100@200")],
        init_segment=StreamFragment(url="http://file", byterange="50@0"),
    )

    assert '#EXT-X-MAP:URI="http://file",BYTERANGE="50@0"' in playlist
    assert "#EXT-X-BYTERANGE:100@200" in playlist


def test_media_playlist_without_init_segment():
    playlist = build_media_playlist(
        segments=[StreamFragment(url="http://file", duration=30)]
    )

    assert "#EXT-X-MAP" not in playlist
    assert "#EXT-X-TARGETDURATION:30" in playlist


def test_master_playlist_pairs_audio_with_video():
    playlist = build_master_playlist(
        video_url="http://video", audio_url="http://audio", audio_name="1080p"
    )

    assert 'URI="http://audio"' in playlist
    assert playlist.endswith("http://video")


def test_master_playlist_escapes_quotes_in_track_name():
    playlist = build_master_playlist(
        video_url="http://video", audio_url="http://audio", audio_name='he said "hi"'
    )

    assert "NAME=\"he said 'hi'\"" in playlist


def test_segment_index_maps_segments_to_byte_ranges():
    head = (
        _box(b"ftyp", b"x" * 8)
        + _box(b"moov", b"y" * 8)
        + _sidx([(100, 2000), (150, 1500)])
    )

    index = parse_segment_index(head)

    assert index.init_size == 32
    assert index.segments == [(88, 100, 2.0), (188, 150, 1.5)]


def test_segment_index_fragments_carry_byte_ranges():
    head = _box(b"ftyp", b"x" * 8) + _sidx([(100, 2000)])

    index = parse_segment_index(head)

    assert index.as_init_fragment("http://file") == StreamFragment(
        url="http://file", byterange="16@0"
    )
    assert index.as_fragments("http://file") == (
        StreamFragment(url="http://file", duration=2.0, byterange="100@60"),
    )


@pytest.mark.parametrize(
    "head",
    [
        pytest.param(b"", id="empty"),
        pytest.param(_box(b"ftyp", b"x" * 8), id="no_index"),
        pytest.param(_box(b"ftyp", b"x" * 8) + _sidx([]), id="empty_index"),
        pytest.param(b"not an mp4 file at all", id="garbage"),
    ],
)
def test_segment_index_gives_up_on_unusable_header(head):
    assert parse_segment_index(head) is None


def test_segment_index_ignores_truncated_index():
    head = (_box(b"ftyp", b"x" * 8) + _sidx([(100, 2000)]))[:-4]

    assert parse_segment_index(head) is None


def test_dash_stream_serves_every_fragment_through_the_proxy():
    server = FakeServer()
    stream = Stream(
        url="http://host/manifest.mpd",
        protocol="dash",
        session=SESSION,
        init_fragment=StreamFragment(url="http://host/init.m4s"),
        fragments=(
            StreamFragment(url="http://host/1.m4s", duration=4),
            StreamFragment(url="http://host/2.m4s", duration=4),
        ),
    )

    dash_stream = DASHPlaylistStream(server=server, stream=stream)
    dash_stream.open()

    playlist = dash_stream.response.content.decode()

    # the playlist points back at the stream itself, by fragment position,
    # so that renewing the stream renews every link in it
    assert server.fragments == ["0", "1", "init"]
    assert {s.url for s in server.streams} == {"http://host/manifest.mpd"}
    assert "http://host/1.m4s" not in playlist
    assert "http://proxy/fragment/1" in playlist
    assert '#EXT-X-MAP:URI="http://proxy/fragment/init"' in playlist


def test_muxed_stream_points_at_video_and_best_audio():
    server = FakeServer()
    audio_tracks = Streams(
        {
            "low": Stream(url="http://audio/low", protocol="dash", session=SESSION),
            "high": Stream(url="http://audio/high", protocol="dash", session=SESSION),
        }
    )
    stream = Stream(
        url="http://video",
        protocol="dash",
        session=SESSION,
        audio_tracks=audio_tracks,
    )

    muxed = HLSMuxedStream(server=server, stream=stream)
    muxed.open()

    playlist = muxed.response.content.decode()

    assert [s.url for s in server.streams] == ["http://video", "http://audio/high"]
    assert server.streams[0].audio_tracks is None
    assert 'NAME="high"' in playlist


def test_muxed_stream_serves_the_language_it_was_narrowed_to():
    """The block hands over one language; the proxy picks the best of it."""

    server = FakeServer()
    audio_tracks = Streams(
        {
            "Audio (ja) [50kbps]": Stream(
                url="http://audio/ja-low",
                protocol="dash",
                session=SESSION,
                is_audio_only=True,
                language="ja",
            ),
            "Audio (ja) [128kbps]": Stream(
                url="http://audio/ja-high",
                protocol="dash",
                session=SESSION,
                is_audio_only=True,
                language="ja",
            ),
        }
    )
    stream = Stream(
        url="http://video",
        protocol="dash",
        session=SESSION,
        audio_tracks=audio_tracks,
    )

    muxed = HLSMuxedStream(server=server, stream=stream)
    muxed.open()

    playlist = muxed.response.content.decode()

    assert [s.url for s in server.streams] == ["http://video", "http://audio/ja-high"]
    assert 'NAME="Audio (ja) [128kbps]"' in playlist
    # without this VLC reports the track with no language, and a preferred
    # language has nothing left to match against
    assert 'LANGUAGE="ja"' in playlist


def test_a_master_playlist_says_nothing_about_a_language_it_does_not_know():
    playlist = build_master_playlist(
        video_url="http://video", audio_url="http://audio", audio_name="Audio"
    )

    assert "LANGUAGE=" not in playlist
    assert 'NAME="Audio",DEFAULT=YES' in playlist


class FakeHTTPSession:
    def __init__(self, content: bytes | None):
        self.content = content
        self.requests = []

    @property
    def http(self):
        return self

    def get(self, url, headers=None, **kwargs):
        self.requests.append((url, headers))

        if self.content is None:
            raise OSError("cannot read stream head")

        return FakeResponse(self.content)


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start : start + chunk_size]


def test_http_stream_is_cut_up_along_its_segment_index():
    server = FakeServer()
    head = _box(b"ftyp", b"x" * 8) + _sidx([(100, 2000), (100, 2000)])
    stream = Stream(
        url="http://host/video.mp4", protocol="http_hls", session=SESSION, duration=4
    )

    http_stream = HTTPPlaylistStream(
        server=server,
        session_=FakeHTTPSession(head),
        stream=stream,
    )
    http_stream.open()

    playlist = http_stream.response.content.decode()

    assert playlist.count("#EXT-X-BYTERANGE") == 2
    assert "#EXT-X-MAP" in playlist


def test_http_stream_probes_only_the_head_of_the_file():
    server = FakeServer()
    session = FakeHTTPSession(_box(b"ftyp", b"x" * 8) + _sidx([(100, 2000)]))
    stream = Stream(url="http://host/video.mp4", protocol="http_hls", session=SESSION)

    http_stream = HTTPPlaylistStream(server=server, session_=session, stream=stream)
    http_stream.open()

    assert session.requests == [("http://host/video.mp4", {"Range": "bytes=0-262143"})]


def test_http_stream_survives_a_failed_probe():
    server = FakeServer()
    stream = Stream(
        url="http://host/video.mp4", protocol="http_hls", session=SESSION, duration=10
    )

    http_stream = HTTPPlaylistStream(
        server=server,
        session_=FakeHTTPSession(None),
        stream=stream,
    )
    http_stream.open()

    assert "#EXTINF:10.000," in http_stream.response.content.decode()


def test_http_stream_falls_back_to_a_single_segment():
    server = FakeServer()
    stream = Stream(
        url="http://host/video.mp4", protocol="http_hls", session=SESSION, duration=12.5
    )

    http_stream = HTTPPlaylistStream(
        server=server,
        session_=FakeHTTPSession(b"no index here"),
        stream=stream,
    )
    http_stream.open()

    playlist = http_stream.response.content.decode()

    assert "#EXT-X-BYTERANGE" not in playlist
    assert "#EXT-X-MAP" not in playlist
    assert "#EXTINF:12.500," in playlist


@pytest.mark.parametrize(
    "head,expected",
    [
        pytest.param(
            _box(b"ftyp", b"") + _box(b"moov", b"") + _box(b"mdat", b"x"),
            False,
            id="plain",
        ),
        pytest.param(
            _box(b"ftyp", b"") + _box(b"moov", b"") + _sidx([(1, 1)]),
            True,
            id="indexed",
        ),
        pytest.param(
            _box(b"ftyp", b"") + _box(b"moov", b"") + _box(b"moof", b""),
            True,
            id="fragmented",
        ),
        pytest.param(_box(b"styp", b""), True, id="segment"),
        pytest.param(b"", False, id="empty"),
        pytest.param(b"junk", False, id="garbage"),
    ],
)
def test_fragmented_files_are_told_apart_from_plain_ones(head, expected):
    assert is_fragmented(head) is expected


def test_a_truncated_header_reads_as_plain():
    """A moov bigger than the probe hides whatever follows it."""

    head = _box(b"ftyp", b"") + _box(b"moov", b"x" * 64)[:32]

    assert is_fragmented(head) is False


class TestRelativeSegmentURIs:
    """A playlist whose segments are named relative to where it came from."""

    PLAYLIST = "\n".join(
        [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-TARGETDURATION:4",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            "#EXTINF:3.0,",
            "seg0.ts",
            "#EXTINF:3.0,",
            "seg1.ts",
            "#EXT-X-ENDLIST",
            "",
        ]
    )

    def test_they_are_resolved_against_the_playlist_url(self):
        r"""A URL is not a path.

        Path() eats one of the slashes after the scheme, and on Windows
        turns what is left into a backslash, so every relative segment
        came out as an unopenable "http:\host/seg0.ts".
        """

        from streamlink.stream.hls import parse_m3u8

        from gridplayer.utils.stream_proxy.wrappers import HLSProxy

        playlist_url = "http://127.0.0.1:8777/live/index.m3u8"

        proxy = HLSProxy.__new__(HLSProxy)
        proxy.args = {"url": playlist_url}

        parsed = parse_m3u8(self.PLAYLIST, proxy._playlist_base_url)

        assert [segment.uri for segment in parsed.segments] == [
            "http://127.0.0.1:8777/live/seg0.ts",
            "http://127.0.0.1:8777/live/seg1.ts",
        ]


class TestServingAPlaylistTheHostWrote:
    """The one kind of playlist that is fetched rather than generated.

    Everything else here is built from a segment list the resolver
    already had; an HLS playlist is fetched, rewritten and handed on, so
    it is the only one with a request behind it.
    """

    PLAYLIST = (
        "#EXTM3U\n"
        "#EXT-X-TARGETDURATION:4\n"
        "#EXTINF:4.0,\n"
        "seg0.ts\n"
        "#EXTINF:4.0,\n"
        "seg1.ts\n"
        "#EXT-X-ENDLIST\n"
    )

    SEGMENT = b"segment bytes"

    @pytest.fixture
    def upstream(self, serving):
        playlist = self.PLAYLIST
        segment = self.SEGMENT

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                self.server.requested.append(self.path)

                is_playlist = self.path.endswith(".m3u8")
                body = playlist.encode("utf-8") if is_playlist else segment

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                """Quiet, the test is not interested"""

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.requested = []

        return serving(server)

    @pytest.fixture
    def playlist_url(self, upstream, serving):
        proxy = serving(StreamProxyServer(("127.0.0.1", 0), ProxyRequestHandler))

        address, port = upstream.server_address

        return proxy.add_stream(
            Stream(
                url=f"http://{address}:{port}/live/index.m3u8",
                protocol="hls_proxy",
                session=SESSION,
            )
        )

    def test_its_segments_are_pointed_back_at_the_proxy(self, playlist_url):
        response = requests.get(playlist_url, timeout=5)

        segments = [
            line for line in response.text.splitlines() if not line.startswith("#")
        ]

        assert response.headers["Content-Type"] == M3U8_CONTENT_TYPE
        assert len(segments) == 2
        assert all(segment.startswith("http://127.0.0.1:") for segment in segments)
        assert not any("/live/" in segment for segment in segments)

    def test_a_segment_it_points_at_is_served(self, upstream, playlist_url):
        response = requests.get(playlist_url, timeout=5)

        segment = next(
            line for line in response.text.splitlines() if not line.startswith("#")
        )

        assert requests.get(segment, timeout=5).content == self.SEGMENT
        assert upstream.requested == ["/live/index.m3u8", "/live/seg0.ts"]
