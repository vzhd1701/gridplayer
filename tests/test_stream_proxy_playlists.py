import struct

import pytest

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
from gridplayer.utils.stream_proxy.wrappers import (
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
