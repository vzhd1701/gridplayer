"""Narrowing a ladder that carries the same video in several languages."""

import pytest

from gridplayer.models.stream import Stream, Streams


def _stream(language=None, is_original=False, is_audio_only=False):
    return Stream(
        url="http://host/s",
        protocol="http",
        language=language,
        is_original_language=is_original,
        is_audio_only=is_audio_only,
    )


def _dubbed_ladder():
    """What a site hands back for a video dubbed into three languages."""

    return Streams(
        {
            f"{height}p ({language})": _stream(language, is_original=language == "en")
            for height in (360, 720, 1080)
            for language in ("cop", "tlh", "en")
        }
    )


def test_languages_are_listed_once_each_in_the_order_offered():
    assert _dubbed_ladder().languages == ("cop", "tlh", "en")


def test_a_ladder_that_names_no_language_is_not_multilingual():
    streams = Streams({f"{h}p": _stream() for h in (360, 720)})

    assert streams.languages == ()
    assert streams.is_multilingual is False


def test_one_language_is_nothing_to_choose_between():
    streams = Streams({f"{h}p": _stream("en") for h in (360, 720)})

    assert streams.languages == ("en",)
    assert streams.is_multilingual is False


def test_a_dubbed_ladder_is_multilingual():
    assert _dubbed_ladder().is_multilingual is True


def test_untagged_rungs_are_not_a_language_of_their_own():
    """A ladder with one dub and one unlabelled rung offers one language."""

    streams = Streams({"360p": _stream("en"), "360p #2": _stream()})

    assert streams.languages == ("en",)


def test_original_language_is_the_one_the_source_marked():
    assert _dubbed_ladder().original_language == "en"


def test_original_language_is_empty_when_nothing_is_marked():
    streams = Streams({"360p": _stream("en"), "720p": _stream("ja")})

    assert streams.original_language is None


def test_for_language_keeps_only_that_language():
    narrowed = _dubbed_ladder().for_language("tlh")

    assert list(narrowed) == ["360p (tlh)", "720p (tlh)", "1080p (tlh)"]


def test_for_language_leaves_a_ladder_alone_when_asked_for_nothing():
    ladder = _dubbed_ladder()

    assert list(ladder.for_language(None)) == list(ladder)
    assert list(ladder.for_language("")) == list(ladder)


def test_for_language_leaves_a_ladder_alone_when_nothing_answers():
    """An empty ladder helps nobody, so an unknown language narrows nothing."""

    ladder = _dubbed_ladder()

    assert list(ladder.for_language("de")) == list(ladder)


def test_a_narrowed_ladder_still_picks_by_height():
    narrowed = _dubbed_ladder().for_language("en")

    quality, _ = narrowed.fit_to_height(700)

    assert quality == "720p (en)"


def test_a_narrowed_ladder_keeps_its_audio_only_rungs():
    streams = Streams(
        {
            "720p": _stream("en"),
            "720p #2": _stream("ja"),
            "audio en": _stream("en", is_audio_only=True),
            "audio ja": _stream("ja", is_audio_only=True),
        }
    )

    narrowed = streams.for_language("en")

    assert list(narrowed.video_streams) == ["720p"]
    assert list(narrowed.audio_only_streams) == ["audio en"]


@pytest.mark.parametrize("language", ["cop", "tlh", "en"])
def test_every_language_narrows_to_a_full_ladder(language):
    assert len(_dubbed_ladder().for_language(language)) == 3


def test_narrowing_keeps_the_silent_rungs_every_language_shares():
    """A video-only rung borrows its language from the audio paired with it."""

    audio = Streams({"Audio (en)": _stream("en", is_audio_only=True)})

    streams = Streams(
        {
            "1080p (video only)": Stream(
                url="http://host/v", protocol="dash", audio_tracks=audio
            ),
            "360p": _stream("en"),
            "360p #2": _stream("ja"),
        }
    )

    narrowed = streams.for_language("ja")

    assert list(narrowed) == ["1080p (video only)", "360p #2"]


def test_narrowing_drops_a_rung_whose_own_sound_has_no_name():
    """It is in some language, just not one that can be matched against."""

    streams = Streams(
        {"360p": _stream("en"), "360p #2": _stream("ja"), "360p #3": _stream()}
    )

    assert list(streams.for_language("en")) == ["360p"]


def test_language_for_answers_with_the_language_asked_for():
    assert _dubbed_ladder().language_for("tlh") == "tlh"


def test_language_for_falls_back_to_the_original():
    assert _dubbed_ladder().language_for("de") == "en"


def test_language_for_has_nothing_to_say_about_one_language():
    streams = Streams({"360p": _stream("en")})

    assert streams.language_for("en") is None
