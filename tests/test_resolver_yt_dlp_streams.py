import pytest

from gridplayer.models.stream import Stream, StreamFragment, Streams
from gridplayer.utils.url_resolve.resolver_yt_dlp import (
    YoutubeDLResolver,
    _carries_its_own_sound,
)

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


def test_streams_carry_their_codec_family():
    """The player picks a software decoder for AV1, so it has to know."""

    formats = [
        _audio_fmt(),
        _dash_fmt("av1", vcodec="av01.0.08M.0"),
        _dash_fmt("h264", vcodec="avc1.640028"),
    ]

    resolver = _resolver({"is_live": False, "formats": formats})

    streams = resolver.streams

    assert [s.video_codec for s in streams.video_streams.values()] == ["av01", "avc1"]
    assert [s.video_codec for s in streams.audio_only_streams.values()] == [None]


@pytest.mark.parametrize(
    ("protocol", "is_adaptive"),
    [
        ("http", False),
        ("direct", False),
        ("http_hls", True),
        ("dash", True),
        ("hls_proxy", True),
        ("hls", True),
    ],
)
def test_only_a_playlist_is_demuxed_adaptively(protocol, is_adaptive):
    assert Stream(url="http://host/v", protocol=protocol).is_adaptive is is_adaptive


def test_paired_audio_makes_a_playlist_out_of_any_protocol():
    """Pairing audio means a generated playlist, whatever the video was."""

    stream = Stream(
        url="http://host/v",
        protocol="http",
        audio_tracks=Streams({"a": Stream(url="http://host/a", protocol="http")}),
    )

    assert stream.is_adaptive is True


def test_audio_track_carries_its_language():
    resolver = _resolver(
        {
            "is_live": False,
            "formats": [_audio_fmt("audio_ja", language="ja"), _dash_fmt("video")],
        }
    )

    _, video = next(iter(resolver.streams.video_streams.items()))
    _, track = next(iter(video.audio_tracks.items()))

    assert track.language == "ja"


def test_silent_video_has_no_language_of_its_own():
    """It borrows one from whichever audio track it is paired with."""

    resolver = _resolver(
        {
            "is_live": False,
            # yt-dlp tags a video-only format with the language of the
            # audio group it was listed under, which it does not carry
            "formats": [_audio_fmt(), _dash_fmt("video", language="ja")],
        }
    )

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.language is None


def test_muxed_video_keeps_the_language_of_its_audio():
    """A format that carries its own sound is the language of that sound.

    YouTube serves multi-language videos this way when it hands out an HLS
    ladder: one full rendition per language, muxed, differing in nothing
    else.
    """

    resolver = _resolver(
        {
            "is_live": False,
            "formats": [
                _dash_fmt("video_en", acodec="mp4a.40.2", language="en"),
                _dash_fmt("video_ja", acodec="mp4a.40.2", language="ja"),
            ],
        }
    )

    languages = {s.language for s in resolver.streams.video_streams.values()}

    assert languages == {"en", "ja"}


@pytest.mark.parametrize("language", [None, "none", ""])
def test_untagged_stream_has_no_language(language):
    """yt-dlp spells "no language" several ways, none of them a language."""

    resolver = _resolver(
        {
            "is_live": False,
            "formats": [_dash_fmt("video", acodec="mp4a.40.2", language=language)],
        }
    )

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.language is None


def _live(*formats):
    return _resolver({"is_live": True, "formats": list(formats)})


def test_live_dash_rungs_that_are_all_one_manifest_become_one():
    """A live ladder is a ladder VLC climbs, not one the menu can."""

    resolver = _live(
        _audio_fmt(),
        _dash_fmt("360p", height=360),
        _dash_fmt("720p", height=720),
        _dash_fmt("1080p", height=1080),
    )

    video_streams = resolver.streams.video_streams

    assert list(video_streams) == ["Adaptive"]
    assert next(iter(video_streams.values())).url == MANIFEST


def test_the_collapsed_rung_stops_auto_chasing_the_pane_size():
    """Three names for one URL made every resize a reload of the same thing."""

    ladder = _live(
        _audio_fmt(),
        _dash_fmt("360p", height=360),
        _dash_fmt("720p", height=720),
        _dash_fmt("1080p", height=1080),
    ).streams

    assert ladder.fit_to_height(360) == ladder.fit_to_height(1080)


def test_live_audio_rungs_collapse_on_their_own():
    """Audio-only stays on offer: it is served by muting, not by URL."""

    resolver = _live(
        _audio_fmt("audio_low", abr=48),
        _audio_fmt("audio_high", abr=128),
        _dash_fmt("720p", height=720),
    )

    assert list(resolver.streams.audio_only_streams) == ["Audio"]
    assert list(resolver.streams.video_streams) == ["720p [avc1]"]


def test_a_lone_live_rung_keeps_the_name_it_came_with():
    """Nothing was promised that cannot be kept, so nothing is taken away."""

    resolver = _live(_audio_fmt(), _dash_fmt("720p", height=720))

    assert list(resolver.streams.video_streams) == ["720p [avc1]"]


def test_a_ladder_the_proxy_serves_is_left_alone():
    """Recorded DASH rungs share a manifest URL and are still real rungs.

    Their segment lists are their own, so collapsing on the URL beside
    them would throw away the quality menu on every recorded video.
    """

    resolver = _resolver(
        {
            "is_live": False,
            "formats": [
                _audio_fmt(),
                _dash_fmt("360p", height=360),
                _dash_fmt("720p", height=720),
            ],
        }
    )

    video_streams = resolver.streams.video_streams

    assert len(video_streams) == 2
    assert {s.protocol for s in video_streams.values()} == {"dash"}


def test_two_manifests_are_two_rungs():
    """Sameness is the URL, not the protocol: different sources still differ."""

    resolver = _live(
        _audio_fmt(),
        _dash_fmt("a", height=720, url="http://host/one.mpd"),
        _dash_fmt("b", height=720, url="http://host/two.mpd"),
    )

    assert len(resolver.streams.video_streams) == 2


@pytest.fixture
def has_cookies(mocker):
    """Whether the jar holds a login for the host the manifest is on.

    What counts as holding one is settled in test_cookies_applied; here
    it is only the answer that matters.
    """

    return mocker.patch(
        "gridplayer.utils.url_resolve.resolver_yt_dlp.has_cookies_for",
        return_value=False,
    )


def test_live_dash_behind_a_login_is_fetched_by_the_proxy(has_cookies):
    """VLC cannot be told a cookie, so it cannot be left to fetch this."""

    has_cookies.return_value = True

    resolver = _live(_audio_fmt(), _dash_fmt("720p", height=720))

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.protocol == "dash_proxy"
    assert video.url == MANIFEST
    assert video.session is not None


def test_live_dash_nothing_is_stored_for_is_still_left_to_vlc(has_cookies):
    """The relay would buy nothing and cost a hop on every segment."""

    resolver = _live(_audio_fmt(), _dash_fmt("720p", height=720))

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.protocol == "direct"


def test_recorded_dash_is_served_as_a_playlist_either_way(has_cookies):
    """Its segments are known here, so the proxy already fetches them."""

    has_cookies.return_value = True

    resolver = _resolver(
        {"is_live": False, "formats": [_audio_fmt(), _dash_fmt("720p", height=720)]}
    )

    _, video = next(iter(resolver.streams.video_streams.items()))

    assert video.protocol == "dash"


def test_a_relayed_live_ladder_is_still_only_one_rung(has_cookies):
    """Who fetches the manifest does not make its rungs any more real."""

    has_cookies.return_value = True

    resolver = _live(
        _audio_fmt(),
        _dash_fmt("360p", height=360),
        _dash_fmt("720p", height=720),
        _dash_fmt("1080p", height=1080),
    )

    assert list(resolver.streams.video_streams) == ["Adaptive"]


def test_a_live_rung_is_not_called_video_only():
    """The manifest carries the sound, and VLC is given the manifest.

    The representation the format described is silent; what plays is
    not, and a viewer who can hear it would be reading a lie.
    """

    resolver = _live(_audio_fmt(), _dash_fmt("720p", height=720))

    name, _ = next(iter(resolver.streams.video_streams.items()))

    assert "video only" not in name


def test_a_live_manifest_with_no_sound_in_it_still_says_so():
    """Nothing to hear here, so the warning is worth keeping."""

    resolver = _live(_dash_fmt("720p", height=720))

    name, _ = next(iter(resolver.streams.video_streams.items()))

    assert "(video only)" in name


def test_a_rung_the_proxy_pairs_itself_is_silent_on_its_own():
    """A recorded DASH rung carries the manifest URL without being it.

    The proxy builds a playlist out of that one rung's segments and
    pairs the audio on its own, so the sound sitting in the manifest is
    not what ends up playing. The resolver never offers such a rung
    unpaired, so this asks the rule directly: what decides is the
    protocol, not which URL the format happened to be given.
    """

    paired = Stream(url=MANIFEST, protocol="dash")

    assert not _carries_its_own_sound(paired, {MANIFEST})
