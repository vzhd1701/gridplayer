"""Choosing a rung of the quality ladder by how big the pane showing it is."""

import pytest

from gridplayer.models.stream import Stream, Streams


def _streams(*qualities, audio_only=()):
    # a ladder runs from worst to best, which is where "best" comes from
    return Streams(
        {
            quality: Stream(
                url=f"http://host/{quality}",
                protocol="http",
                is_audio_only=quality in audio_only,
            )
            for quality in qualities
        }
    )


LADDER = ("240p", "360p", "480p", "720p", "1080p")


@pytest.mark.parametrize(
    ("pane_height", "expected"),
    [
        (100, "240p"),
        (240, "240p"),
        (241, "360p"),
        (500, "720p"),
        (720, "720p"),
        (1080, "1080p"),
    ],
)
def test_the_cheapest_rung_that_still_fills_the_pane_is_picked(pane_height, expected):
    quality, _ = _streams(*LADDER).fit_to_height(pane_height)

    assert quality == expected


def test_a_pane_taller_than_the_ladder_gets_the_best_there_is():
    quality, _ = _streams(*LADDER).fit_to_height(2160)

    assert quality == "1080p"


def test_a_rung_is_matched_on_its_size_whatever_else_its_name_says():
    streams = _streams("360p [avc1]", "720p60 [vp9]", "1080p60 [av01]")

    quality, _ = streams.fit_to_height(700)

    assert quality == "720p60 [vp9]"


def test_a_rung_that_does_not_say_its_size_is_passed_over():
    streams = _streams("Unknown 1", "480p", "Unknown 2")

    quality, _ = streams.fit_to_height(400)

    assert quality == "480p"


def test_audio_only_rungs_are_not_offered_to_a_pane():
    streams = _streams("audio", "360p", "720p", audio_only=("audio",))

    quality, _ = streams.fit_to_height(300)

    assert quality == "360p"


def test_a_single_rung_is_the_only_answer_however_small_the_pane():
    quality, _ = _streams("1080p").fit_to_height(50)

    assert quality == "1080p"
