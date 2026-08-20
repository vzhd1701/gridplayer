import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from gridplayer.vlc_player import vlc
from gridplayer.vlc_player.player_tracks_manager import (
    TracksManager,
    _convert_audio_track,
    _convert_video_track,
    _decode_track_field,
)

INVALID_UTF8 = b"\x80"
VALID_ASCII = b"eng"
VALID_UNICODE = "日本語トラック".encode()


class FakeVideoContent:
    def __init__(self, width=1920, height=1080, frame_rate_num=30, frame_rate_den=1):
        self.width = width
        self.height = height
        self.frame_rate_num = frame_rate_num
        self.frame_rate_den = frame_rate_den


class FakeAudioContent:
    def __init__(self, channels=2, rate=48000):
        self.channels = channels
        self.rate = rate


class FakePointer:
    def __init__(self, contents):
        self.contents = contents


class FakeUnion:
    def __init__(self, video=None, audio=None):
        self.video = video
        self.audio = audio


class FakeMediaTrack:
    def __init__(
        self,
        *,
        track_id,
        track_type,
        language=None,
        description=None,
        bitrate=0,
        codec=0,
        video_content=None,
        audio_content=None,
    ):
        self.id = track_id
        self.type = track_type
        self.language = language
        self.description = description
        self.bitrate = bitrate
        self.codec = codec
        self.u = FakeUnion(
            video=FakePointer(video_content) if video_content else None,
            audio=FakePointer(audio_content) if audio_content else None,
        )


def make_video_track(**kwargs):
    kwargs.setdefault("track_id", 0)
    kwargs.setdefault("track_type", vlc.TrackType.video)
    kwargs.setdefault("video_content", FakeVideoContent())
    return FakeMediaTrack(**kwargs)


def make_audio_track(**kwargs):
    kwargs.setdefault("track_id", 0)
    kwargs.setdefault("track_type", vlc.TrackType.audio)
    kwargs.setdefault("audio_content", FakeAudioContent())
    return FakeMediaTrack(**kwargs)


@pytest.fixture(autouse=True)
def fake_codec_description(monkeypatch):
    monkeypatch.setattr(
        "gridplayer.vlc_player.player_tracks_manager.vlc.libvlc_media_get_codec_description",
        lambda *_args: b"H264",
    )


class TestDecodeTrackField:
    def test_none_returns_default(self):
        assert (
            _decode_track_field(
                None,
                media_uri="x.mkv",
                track_type="video",
                track_id=0,
                field_name="language",
            )
            is None
        )

    def test_none_returns_custom_default(self):
        assert (
            _decode_track_field(
                None,
                media_uri="x.mkv",
                track_type="video",
                track_id=0,
                field_name="codec",
                default="",
            )
            == ""
        )

    def test_str_passthrough(self):
        assert (
            _decode_track_field(
                "eng",
                media_uri="x.mkv",
                track_type="video",
                track_id=0,
                field_name="language",
            )
            == "eng"
        )

    def test_valid_ascii_bytes(self):
        assert (
            _decode_track_field(
                VALID_ASCII,
                media_uri="x.mkv",
                track_type="video",
                track_id=0,
                field_name="language",
            )
            == "eng"
        )

    def test_valid_unicode_bytes(self):
        assert (
            _decode_track_field(
                VALID_UNICODE,
                media_uri="x.mkv",
                track_type="video",
                track_id=0,
                field_name="description",
            )
            == "日本語トラック"
        )

    def test_invalid_utf8_bytes_falls_back_without_raising(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _decode_track_field(
                INVALID_UTF8,
                media_uri="bad_metadata.mkv",
                track_type="video",
                track_id=3,
                field_name="language",
            )

        assert result == "�"
        assert "bad_metadata.mkv" in caplog.text
        assert "language" in caplog.text
        assert "video" in caplog.text
        assert "3" in caplog.text

    def test_unexpected_type_logs_and_returns_default(self, caplog):
        with caplog.at_level(logging.ERROR):
            result = _decode_track_field(
                12345,
                media_uri="x.mkv",
                track_type="audio",
                track_id=1,
                field_name="language",
            )

        assert result is None
        assert "int" in caplog.text


class TestConvertVideoTrack:
    def test_normal_track(self):
        track = make_video_track(language=b"eng", description=b"Main")

        result = _convert_video_track(track, media_uri="ok.mp4")

        assert result.language == "eng"
        assert result.description == "Main"
        assert result.codec == "H264"
        assert result.video_dimensions == (1920, 1080)
        assert result.fps == 30.0

    def test_none_language_and_description(self):
        track = make_video_track(language=None, description=None)

        result = _convert_video_track(track, media_uri="ok.mp4")

        assert result.language is None
        assert result.description is None

    def test_invalid_language_does_not_raise_and_does_not_corrupt_description(self):
        track = make_video_track(
            language=INVALID_UTF8, description=b"Valid description"
        )

        result = _convert_video_track(track, media_uri="broken.mkv")

        assert result.language == "�"
        assert result.description == "Valid description"

    def test_invalid_description_does_not_raise_and_does_not_corrupt_language(self):
        track = make_video_track(language=b"eng", description=INVALID_UTF8)

        result = _convert_video_track(track, media_uri="broken.mkv")

        assert result.language == "eng"
        assert result.description == "�"

    def test_fps_none_when_frame_rate_missing(self):
        track = make_video_track(video_content=FakeVideoContent(frame_rate_num=0))

        result = _convert_video_track(track, media_uri="ok.mp4")

        assert result.fps is None


class TestConvertAudioTrack:
    def test_normal_track(self):
        track = make_audio_track(language=b"spa", description=b"Commentary")

        result = _convert_audio_track(track, media_uri="ok.mp4")

        assert result.language == "spa"
        assert result.description == "Commentary"
        assert result.channels == 2
        assert result.rate == 48000

    def test_invalid_language_falls_back(self):
        track = make_audio_track(language=INVALID_UTF8)

        result = _convert_audio_track(track, media_uri="broken.mkv")

        assert result.language == "�"


class TestTracksManagerDoesNotCrashOnBadMetadata:
    def test_mixed_good_and_bad_tracks_all_convert(self):
        tracks = [
            make_video_track(track_id=0, language=b"eng", description=b"Good"),
            make_video_track(
                track_id=1, language=INVALID_UTF8, description=b"Bad lang"
            ),
            make_audio_track(track_id=0, language=b"eng"),
            make_audio_track(track_id=1, language=INVALID_UTF8),
        ]

        manager = TracksManager(
            media_player=None,
            media_tracks=tracks,
            is_audio_only=False,
            media_uri="mixed.mkv",
        )

        video_tracks = manager.video_tracks
        audio_tracks = manager.audio_tracks

        assert len(video_tracks) == 2
        assert len(audio_tracks) == 2
        assert video_tracks[0].language == "eng"
        assert video_tracks[1].language == "�"
        assert audio_tracks[1].language == "�"

    def test_many_tracks_converted_concurrently(self):
        tracks = [
            make_video_track(
                track_id=i,
                language=INVALID_UTF8 if i % 2 == 0 else b"eng",
                description=b"desc",
            )
            for i in range(20)
        ]

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda t: _convert_video_track(t, media_uri="concurrent.mkv"),
                    tracks,
                )
            )

        assert len(results) == 20
        for i, result in enumerate(results):
            expected = "�" if i % 2 == 0 else "eng"
            assert result.language == expected
