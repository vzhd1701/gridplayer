import pytest

from gridplayer.models.stream import StreamFragment
from gridplayer.utils.url_resolve.resolver_yt_dlp import YoutubeDLResolver

MANIFEST = "http://host/manifest.mpd"


@pytest.fixture(autouse=True)
def is_fragmented_stream(mocker):
    """Nothing in here is allowed to reach out to the network."""

    return mocker.patch(
        "gridplayer.utils.url_resolve.resolver_yt_dlp.is_fragmented_stream",
        return_value=False,
    )


@pytest.fixture(autouse=True)
def settings(mocker):
    """Keep the resolver away from the app-wide settings singleton."""

    settings = mocker.patch(
        "gridplayer.utils.url_resolve.resolver_yt_dlp.Settings"
    ).return_value
    settings.get.return_value = True

    return settings


def _resolver(video_info):
    resolver = YoutubeDLResolver(MANIFEST)
    resolver.__dict__["_video_info"] = {
        "extractor": "generic",
        "title": "test",
        **video_info,
    }
    return resolver


def _dash_fmt(format_id, **kwargs):
    fmt = {
        "format_id": format_id,
        "url": MANIFEST,
        "protocol": "http_dash_segments",
        "ext": "mp4",
        "container": "mp4_dash",
        "fragment_base_url": "http://host/dash/",
        "fragments": [
            {"path": f"{format_id}-init.m4s"},
            {"path": f"{format_id}-0.m4s", "duration": 4.0},
            {"path": f"{format_id}-1.m4s", "duration": 2.0},
        ],
        "vcodec": "avc1.64",
        "acodec": "none",
        "height": 720,
        "width": 1280,
        "resolution": "1280x720",
        "video_ext": "mp4",
    }
    fmt.update(kwargs)
    return fmt


def _audio_fmt(format_id="audio", **kwargs):
    defaults = {
        "ext": "m4a",
        "container": "m4a_dash",
        "vcodec": "none",
        "acodec": "mp4a.40.2",
        "height": None,
        "width": None,
        "resolution": "audio only",
        "video_ext": "none",
        "format_note": "DASH audio",
    }

    return _dash_fmt(format_id, **{**defaults, **kwargs})


def test_dash_video_is_paired_with_audio():
    resolver = _resolver(
        {"is_live": False, "formats": [_audio_fmt(), _dash_fmt("video")]}
    )

    streams = resolver.streams

    video_name, video = next(iter(streams.video_streams.items()))

    assert video.protocol == "dash"
    assert video.audio_tracks is not None
    assert "video only" not in video_name


def test_dash_fragments_are_expanded_to_absolute_urls():
    resolver = _resolver(
        {"is_live": False, "formats": [_audio_fmt(), _dash_fmt("video")]}
    )

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.init_fragment == StreamFragment(url="http://host/dash/video-init.m4s")
    assert video.fragments == (
        StreamFragment(url="http://host/dash/video-0.m4s", duration=4.0),
        StreamFragment(url="http://host/dash/video-1.m4s", duration=2.0),
    )


def test_dash_fragments_keep_absolute_urls_as_they_are():
    fmt = _dash_fmt("video")
    fmt["fragments"] = [{"url": "http://cdn/init.m4s"}, {"url": "http://cdn/0.m4s"}]

    resolver = _resolver({"is_live": False, "formats": [_audio_fmt(), fmt]})

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.init_fragment.url == "http://cdn/init.m4s"
    assert video.fragments[0].url == "http://cdn/0.m4s"


def test_live_dash_is_left_to_vlc():
    resolver = _resolver(
        {"is_live": True, "formats": [_audio_fmt(), _dash_fmt("video")]}
    )

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.protocol == "direct"
    assert video.url == MANIFEST


def test_webm_dash_video_is_not_offered_without_sound():
    """VLC cannot demux WebM out of a playlist, so it cannot get audio."""

    resolver = _resolver(
        {
            "is_live": False,
            "formats": [
                _audio_fmt(),
                _dash_fmt("video_mp4"),
                _dash_fmt("video_webm", ext="webm", container="webm_dash"),
            ],
        }
    )

    video_streams = resolver.streams.video_streams

    assert [s.protocol for s in video_streams.values()] == ["dash"]


def test_progressive_dash_video_is_served_as_a_playlist():
    audio = _audio_fmt(protocol="https", fragments=None, url="http://host/audio.m4a")
    video = _dash_fmt(
        "video", protocol="https", fragments=None, url="http://host/v.mp4"
    )

    resolver = _resolver(
        {"is_live": False, "duration": 61.5, "formats": [audio, video]}
    )

    _, stream = next(iter(resolver.streams.video_streams.items()))

    assert stream.protocol == "http_hls"
    assert stream.duration == 61.5
    assert stream.audio_tracks is not None
    assert next(iter(stream.audio_tracks.streams.values())).protocol == "http_hls"


def test_plain_progressive_video_is_not_paired():
    """A file that is not fragmented cannot be cut into segments."""

    audio = _audio_fmt(protocol="https", fragments=None, container=None)
    muxed = _dash_fmt(
        "muxed", protocol="https", fragments=None, container=None, acodec="mp4a.40.2"
    )
    video = _dash_fmt("video", protocol="https", fragments=None, container=None)

    resolver = _resolver({"is_live": False, "formats": [audio, muxed, video]})

    video_streams = resolver.streams.video_streams

    assert [s.protocol for s in video_streams.values()] == ["http"]
    assert all(s.audio_tracks is None for s in video_streams.values())


def test_fragmented_progressive_video_is_paired_without_a_container_hint(
    is_fragmented_stream,
):
    """Not every site fills in the container, so the file itself is probed."""

    is_fragmented_stream.return_value = True

    audio = _audio_fmt(protocol="https", fragments=None, container=None)
    video = _dash_fmt("video", protocol="https", fragments=None, container=None)

    resolver = _resolver({"is_live": False, "formats": [audio, video]})

    _, stream = next(iter(resolver.streams.video_streams.items()))

    assert stream.protocol == "http_hls"
    assert stream.audio_tracks is not None


def test_source_is_probed_for_fragments_only_once(is_fragmented_stream):
    is_fragmented_stream.return_value = True

    formats = [
        _audio_fmt(protocol="https", fragments=None, container=None),
        _dash_fmt("360p", protocol="https", fragments=None, container=None),
        _dash_fmt("720p", protocol="https", fragments=None, container=None),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert len(resolver.streams.video_streams) == 2
    assert is_fragmented_stream.call_count == 1


def test_a_failed_probe_leaves_the_stream_alone(is_fragmented_stream):
    is_fragmented_stream.side_effect = OSError("connection reset")

    audio = _audio_fmt(protocol="https", fragments=None, container=None)
    video = _dash_fmt("video", protocol="https", fragments=None, container=None)

    resolver = _resolver({"is_live": False, "formats": [audio, video]})

    _, stream = next(iter(resolver.streams.video_streams.items()))

    assert stream.audio_tracks is None


def test_dash_source_is_not_probed(is_fragmented_stream):
    _resolver({"is_live": False, "formats": [_audio_fmt(), _dash_fmt("video")]}).streams

    is_fragmented_stream.assert_not_called()


def test_silent_streams_are_still_offered_when_nothing_else_is_left():
    resolver = _resolver({"is_live": False, "formats": [_dash_fmt("video")]})

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.audio_tracks is None


@pytest.mark.parametrize(
    "hls_via_streamlink,expected",
    [(True, "hls"), (False, "hls_proxy")],
)
def test_live_hls_still_honours_the_streamlink_setting(
    settings, hls_via_streamlink, expected
):
    settings.get.return_value = hls_via_streamlink

    fmt = _dash_fmt("video", protocol="m3u8_native", acodec="mp4a.40.2", fragments=None)

    resolver = _resolver({"is_live": True, "formats": [fmt]})

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.protocol == expected


def test_audio_only_names_drop_the_internal_format_id():
    resolver = _resolver(
        {
            "is_live": False,
            "formats": [_audio_fmt("30280", tbr=180.0), _dash_fmt("video")],
        }
    )

    assert list(resolver.streams.audio_only_streams) == ["Audio [mp4a 180kbps]"]


def test_audio_only_names_tell_languages_apart():
    formats = [
        _audio_fmt("30280", tbr=128.0, language="en"),
        _audio_fmt("30281", tbr=128.0, language="ja"),
        _dash_fmt("video"),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert list(resolver.streams.audio_only_streams) == [
        "Audio (en) [mp4a 128kbps]",
        "Audio (ja) [mp4a 128kbps]",
    ]


def test_audio_only_name_falls_back_to_a_bare_label():
    resolver = _resolver(
        {
            "is_live": False,
            "formats": [_audio_fmt("30280", acodec=None, tbr=None), _dash_fmt("video")],
        }
    )

    assert list(resolver.streams.audio_only_streams) == ["Audio"]


def test_formats_that_render_to_one_name_all_keep_their_place():
    formats = [
        _audio_fmt("30280", tbr=128.0),
        _audio_fmt("30281", tbr=128.0),
        _audio_fmt("30282", tbr=128.0),
        _dash_fmt("video"),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    streams = resolver.streams

    assert list(streams.audio_only_streams) == [
        "Audio [mp4a 128kbps]",
        "Audio [mp4a 128kbps] #2",
        "Audio [mp4a 128kbps] #3",
    ]
    assert [s.init_fragment.url for s in streams.audio_only_streams.values()] == [
        "http://host/dash/30280-init.m4s",
        "http://host/dash/30281-init.m4s",
        "http://host/dash/30282-init.m4s",
    ]


def test_paired_audio_tracks_keep_their_place_too():
    formats = [
        _audio_fmt("30280", tbr=128.0),
        _audio_fmt("30281", tbr=128.0),
        _dash_fmt("video"),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert list(video.audio_tracks) == [
        "Audio [mp4a 128kbps]",
        "Audio [mp4a 128kbps] #2",
    ]


def test_bitrates_reported_in_bits_are_brought_back_to_kbits():
    """Some extractors hand over raw bits/s, inflating every number by 1000."""

    # 70 seconds of video, as the file sizes and bitrates agree
    formats = [
        _audio_fmt("audio", tbr=51844, abr=51844, filesize=453735),
        _dash_fmt("video", tbr=244052, vbr=244052, filesize=2131374),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert list(resolver.streams) == ["720p [avc1 244kbps]", "Audio [mp4a 51kbps]"]


def test_plausible_bitrates_are_left_alone():
    # 128kbps over 70 seconds really is about 1.1MB
    formats = [
        _audio_fmt("audio", tbr=128.0, filesize=1120000),
        _dash_fmt("video", tbr=2200.0, filesize=19250000),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert list(resolver.streams) == ["720p [avc1 2200kbps]", "Audio [mp4a 128kbps]"]


def test_bitrates_are_left_alone_when_no_file_size_says_otherwise():
    """Without a file size there is nothing to pin the bitrate against."""

    formats = [
        _audio_fmt("audio", tbr=51844),
        _dash_fmt("video", tbr=244052),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert list(resolver.streams) == [
        "720p [avc1 244052kbps]",
        "Audio [mp4a 51844kbps]",
    ]


def test_resolution_shaped_notes_still_say_which_codec_they_are():
    """A site naming its formats "1080p" leaves them indistinguishable."""

    formats = [
        _audio_fmt(),
        _dash_fmt("137", format_note="1080p", vcodec="avc1.64", tbr=2869.0),
        _dash_fmt("399", format_note="1080p", vcodec="av01.0.08M.0", tbr=1569.0),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert list(resolver.streams.video_streams) == [
        "1080p [avc1 2869kbps]",
        "1080p [av01 1569kbps]",
    ]


def test_a_format_with_nothing_to_show_falls_back_to_its_id():
    formats = [
        _audio_fmt(),
        _dash_fmt("ld", format_note="1080p", vcodec=None, tbr=None),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    assert list(resolver.streams.video_streams) == ["1080p [ld]"]
