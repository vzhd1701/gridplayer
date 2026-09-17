"""A renewed stream keeps the audio language it was being served in."""

from gridplayer.models.stream import Stream, StreamOrigin, Streams
from gridplayer.utils.stream_proxy.server import _pick_stream


def _audio(language, bitrate):
    return Stream(
        url=f"http://host/audio-{language}-{bitrate}",
        protocol="http_hls",
        is_audio_only=True,
        language=language,
    )


def _tracks(*languages):
    return Streams(
        {
            f"Audio ({language}) [{bitrate}kbps]": _audio(language, bitrate)
            for language in languages
            for bitrate in (50, 128)
        }
    )


def _video(audio_tracks):
    return Stream(
        url="http://host/video",
        protocol="dash",
        audio_tracks=audio_tracks,
        origin=StreamOrigin(url="http://site/watch", quality="720p"),
    )


def _fresh_ladder():
    return Streams({"720p": _video(_tracks("en", "ja"))})


def test_a_renewal_keeps_only_the_language_being_served():
    served = _video(_tracks("ja"))

    renewed = _pick_stream(_fresh_ladder(), served)

    assert {t.language for _, t in renewed.audio_tracks.items()} == {"ja"}


def test_a_renewal_keeps_every_rendition_of_that_language():
    """Narrowing is by language, so the proxy still gets to pick the best."""

    served = _video(_tracks("ja"))

    renewed = _pick_stream(_fresh_ladder(), served)

    assert len(renewed.audio_tracks) == 2


def test_a_renewal_offers_everything_again_when_the_language_is_gone():
    """An empty track list would leave the video with no sound at all."""

    served = _video(_tracks("de"))

    renewed = _pick_stream(_fresh_ladder(), served)

    assert len(renewed.audio_tracks) == 4


def test_a_stream_that_was_serving_every_language_keeps_them_all():
    served = _video(_tracks("en", "ja"))

    renewed = _pick_stream(_fresh_ladder(), served)

    assert len(renewed.audio_tracks) == 4


def test_the_video_half_of_a_pair_is_still_served_without_audio():
    """It was handed over solo, and must not turn back into a playlist."""

    solo = Stream(
        url="http://host/video",
        protocol="dash",
        origin=StreamOrigin(url="http://site/watch", quality="720p"),
    )

    assert _pick_stream(_fresh_ladder(), solo).audio_tracks is None
