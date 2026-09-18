"""The Stream Quality submenu: what to pick, as well as which rung."""

from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.stream import (
    STREAM_QUALITY_AUDIO_ONLY,
    STREAM_QUALITY_AUTO,
    STREAM_QUALITY_BEST,
    Stream,
    Streams,
)
from gridplayer.player.managers.active_block import ActiveBlockManager


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


VIDEO_RUNGS = ("360p", "720p", "1080p")

AUDIO_RUNG = "Audio 129kbps [opus]"


class _Manager(ActiveBlockManager):
    """The manager's menu methods, without the rest of the player behind them."""

    def __init__(self, block):
        self._ctx = SimpleNamespace(active_block=block)

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None


def _ladder(video=VIDEO_RUNGS, audio=()):
    streams = {
        quality: Stream(url=f"http://host/{quality}", protocol="http")
        for quality in video
    }

    streams.update(
        {
            quality: Stream(
                url=f"http://host/{quality}", protocol="http", is_audio_only=True
            )
            for quality in audio
        }
    )

    return Streams(streams)


def _manager(ladder=None, quality=STREAM_QUALITY_AUTO, playing="720p"):
    ladder = _ladder() if ladder is None else ladder

    block = SimpleNamespace(
        stream_ladder=ladder,
        stream_quality_playing=playing,
        video_params=SimpleNamespace(stream_quality=quality),
    )

    return _Manager(block)


def _titles(menu):
    return [item if item == "---" else item["title"] for item in menu]


def _menu_rows(manager):
    return manager.menu_generator_stream_quality()


def _ticked(manager):
    """The one row the menu would put a tick next to, if there is one."""

    ticked = [
        item["check_if"][2]
        for item in _menu_rows(manager)
        if item != "---"
        and item.get("check_if")
        and item["check_if"][2] == manager._ctx.active_block.video_params.stream_quality
    ]

    assert len(ticked) <= 1, ticked

    return ticked[0] if ticked else None


def test_a_ladder_offers_what_to_pick_before_which_rung():
    menu = _manager(ladder=_ladder(audio=(AUDIO_RUNG,))).menu_generator_stream_quality()

    assert _titles(menu) == [
        "Auto (720p)",
        "Adapt after: %v",
        "Best",
        "Audio Only",
        "---",
        "1080p",
        "720p",
        "360p",
        "---",
        AUDIO_RUNG,
    ]


def test_a_ladder_with_no_audio_rungs_does_not_offer_audio_only():
    assert "Audio Only" not in _titles(_manager().menu_generator_stream_quality())


def test_nothing_offers_the_worst_rung_any_more():
    """Still understood where it was stored, but no longer put in the way."""

    menu = _manager(ladder=_ladder(audio=(AUDIO_RUNG,))).menu_generator_stream_quality()

    assert not [title for title in _titles(menu) if "Worst" in title]


def test_a_standing_choice_spells_out_the_rung_it_settled_on():
    """The name it landed on is the one thing the choice does not say."""

    menu = _manager(quality=STREAM_QUALITY_BEST, playing="1080p")
    titles = _titles(menu.menu_generator_stream_quality())

    assert "Best (1080p)" in titles
    # the rung is only spelled out under the choice that is actually made
    assert "Auto" in titles


def test_audio_only_spells_out_the_format_it_settled_on():
    menu = _manager(
        ladder=_ladder(audio=(AUDIO_RUNG,)),
        quality=STREAM_QUALITY_AUDIO_ONLY,
        playing=AUDIO_RUNG,
    )

    assert f"Audio Only ({AUDIO_RUNG})" in _titles(menu.menu_generator_stream_quality())


def test_a_standing_choice_is_ticked_rather_than_the_rung_it_landed_on():
    """Which is why the rung has to be spelled out beside the choice."""

    menu = _manager(quality=STREAM_QUALITY_BEST, playing="1080p")

    ticked_by = {
        item["title"]: item["check_if"][2]
        for item in menu.menu_generator_stream_quality()
        if item != "---" and item.get("check_if")
    }

    assert ticked_by["Best (1080p)"] == STREAM_QUALITY_BEST
    assert ticked_by["1080p"] == "1080p"


def test_an_audio_only_ladder_does_not_offer_best_twice():
    """With no video rungs, best and audio only are the same rung."""

    # a rung picked by hand, so no standing choice is holding a place open
    menu = _manager(
        ladder=_ladder(video=(), audio=(AUDIO_RUNG,)),
        quality=AUDIO_RUNG,
        playing=AUDIO_RUNG,
    )

    assert _titles(menu.menu_generator_stream_quality()) == [
        "Audio Only",
        "---",
        AUDIO_RUNG,
    ]


def test_a_choice_this_ladder_cannot_honour_is_still_on_the_menu():
    """Otherwise the menu looks like nothing at all is chosen.

    A standing choice outlives the ladder it was made on, so a video
    with no audio-only rung is played as video while audio only is
    still what was asked for. Leaving the choice off the menu hides
    both halves of that: what is in force, and that it is not being
    honoured here.
    """

    menu = _manager(quality=STREAM_QUALITY_AUDIO_ONLY, playing="1080p")
    titles = _titles(menu.menu_generator_stream_quality())

    # the rung it fell back to, named where the audio rung would have been
    assert "Audio Only (1080p)" in titles
    assert _ticked(menu) == STREAM_QUALITY_AUDIO_ONLY


@pytest.mark.parametrize("quality", [STREAM_QUALITY_AUTO, STREAM_QUALITY_BEST])
def test_the_same_where_an_audio_only_ladder_cannot_offer_a_video_choice(quality):
    menu = _manager(
        ladder=_ladder(video=(), audio=(AUDIO_RUNG,)),
        quality=quality,
        playing=AUDIO_RUNG,
    )

    assert _ticked(menu) == quality


def test_exactly_one_row_is_ticked_whatever_the_ladder_holds():
    ladders = (
        _ladder(),
        _ladder(audio=(AUDIO_RUNG,)),
        _ladder(video=(), audio=(AUDIO_RUNG,)),
    )
    choices = (
        STREAM_QUALITY_AUTO,
        STREAM_QUALITY_BEST,
        STREAM_QUALITY_AUDIO_ONLY,
    )

    for ladder in ladders:
        for quality in choices:
            menu = _manager(ladder=ladder, quality=quality)

            assert _ticked(menu) == quality, (quality, _titles(_menu_rows(menu)))


def test_there_is_nothing_to_adapt_to_without_video_rungs():
    menu = _manager(
        ladder=_ladder(video=(), audio=(AUDIO_RUNG,)),
        quality=STREAM_QUALITY_AUTO,
        playing=AUDIO_RUNG,
    )

    assert "Adapt after: %v" not in _titles(menu.menu_generator_stream_quality())


def _marked_as_playing(manager):
    """The rungs carrying the mark for the one that is on screen."""

    return [
        item["title"]
        for item in _menu_rows(manager)
        if item != "---" and item["icon"] == "play"
    ]


def test_the_rung_on_screen_is_marked_even_where_it_was_not_chosen():
    """A standing choice names no rung, so the list has to name it."""

    menu = _manager(quality=STREAM_QUALITY_BEST, playing="1080p")

    assert _marked_as_playing(menu) == ["1080p"]


def test_a_rung_picked_by_hand_is_marked_as_well_as_chosen():
    """The mark means the same thing wherever it lands, so it always lands."""

    menu = _manager(quality="720p", playing="720p")

    assert _marked_as_playing(menu) == ["720p"]


def test_an_audio_rung_on_screen_is_marked_like_any_other():
    menu = _manager(
        ladder=_ladder(audio=(AUDIO_RUNG,)),
        quality=STREAM_QUALITY_AUDIO_ONLY,
        playing=AUDIO_RUNG,
    )

    assert _marked_as_playing(menu) == [AUDIO_RUNG]


def test_a_choice_that_could_not_be_honoured_marks_what_it_fell_back_to():
    """Both halves of the surprise, in one look at the menu."""

    menu = _manager(quality=STREAM_QUALITY_AUDIO_ONLY, playing="1080p")

    assert _ticked(menu) == STREAM_QUALITY_AUDIO_ONLY
    assert _marked_as_playing(menu) == ["1080p"]


def test_the_mark_is_never_on_more_than_one_rung():
    ladders = (
        _ladder(),
        _ladder(audio=(AUDIO_RUNG,)),
        _ladder(video=(), audio=(AUDIO_RUNG,)),
    )
    choices = (
        STREAM_QUALITY_AUTO,
        STREAM_QUALITY_BEST,
        STREAM_QUALITY_AUDIO_ONLY,
        "720p",
    )

    for ladder in ladders:
        for quality in choices:
            for playing in ("720p", AUDIO_RUNG, None):
                marked = _marked_as_playing(
                    _manager(ladder=ladder, quality=quality, playing=playing)
                )

                assert len(marked) <= 1, (ladder.streams, quality, playing, marked)


def test_the_standing_choices_leave_the_mark_to_the_rungs():
    """Two rows saying "this one" would be one row too many."""

    menu = _manager(
        ladder=_ladder(audio=(AUDIO_RUNG,)),
        quality=STREAM_QUALITY_BEST,
        playing="1080p",
    )

    standing = {"Auto", "Best (1080p)", "Audio Only"}
    icons = {
        item["title"]: item["icon"]
        for item in _menu_rows(menu)
        if item != "---" and item["title"] in standing
    }

    assert icons == dict.fromkeys(standing, "empty")


def test_every_row_calls_something_that_exists_on_a_block():
    """A menu entry pointing at nothing fails silently at the click."""

    from gridplayer.widgets.video_block import VideoBlock

    menu = _manager(ladder=_ladder(audio=(AUDIO_RUNG,))).menu_generator_stream_quality()

    called = [item["func"][1] for item in menu if item != "---"]

    assert called
    for name in called:
        assert hasattr(VideoBlock, name), name
