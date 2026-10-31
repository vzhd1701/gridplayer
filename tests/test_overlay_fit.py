"""A small cell leaves out the controls it has no room for, a few at a time,
and keeps its frame whatever its size."""

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.video_overlay import (
    CONTROL_MARGIN,
    OverlayBlock,
    OverlayMode,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def overlay():
    overlay = OverlayBlock()
    overlay.resize(640, 360)
    overlay.show()
    overlay.set_label("a video with quite a long name.mp4")
    overlay.set_position(1000, 100_000)
    overlay.set_list_place("3/12")
    overlay.set_is_active(True)
    yield overlay
    overlay.close()


def _shown(overlay) -> set[str]:
    names = (
        "label_text",
        "exit_button",
        "list_place_button",
        "label_info",
        "play_pause_button",
        "label_progress",
        "progress_bar",
        "volume_button",
        "volume_bar",
        "play_button",
        "retry_button",
        "details_button",
        "next_button",
    )
    if overlay.control_widget.isHidden():
        return set()
    return {name for name in names if not getattr(overlay, name).isHidden()}


def _fits(overlay):
    """The controls shown are inside the cell, as laid out."""

    overlay.lay_out_now()
    area = overlay.rect()
    for name in _shown(overlay):
        widget = getattr(overlay, name)
        rect = widget.geometry().translated(
            widget.parent().mapTo(overlay, widget.pos()) - widget.pos()
        )
        assert area.contains(rect), (name, rect, area)


def test_a_big_cell_shows_all_of_them(overlay):
    assert _shown(overlay) == {
        "label_text",
        "exit_button",
        "list_place_button",
        "play_pause_button",
        "label_progress",
        "progress_bar",
        "volume_button",
        "volume_bar",
    }


def _gone_as_it_shrinks(overlay, sizes) -> dict[str, int]:
    """At which step each control went, the size going down step by step."""

    before = _shown(overlay)
    gone = {}

    for step, (width, height) in enumerate(sizes):
        overlay.resize(width, height)
        shown = _shown(overlay)
        assert shown <= before, (width, height)
        gone.update(dict.fromkeys(before - shown, step))
        before = shown
        _fits(overlay)

    return gone


def test_they_go_a_few_at_a_time_as_it_gets_narrower(overlay):
    gone = _gone_as_it_shrinks(overlay, [(w, 360) for w in range(640, 20, -2)])

    order = [
        "label_progress",
        "list_place_button",
        "volume_button",
        "progress_bar",
        "label_text",
        "exit_button",
    ]
    steps = [gone[name] for name in order]

    assert steps == sorted(steps)
    assert len(set(steps)) > 4
    assert gone["volume_bar"] == gone["volume_button"]
    assert gone["play_pause_button"] == gone["exit_button"]


def test_they_go_a_few_at_a_time_as_it_gets_shorter(overlay):
    overlay.set_info_label("Speed 1.5x")
    gone = _gone_as_it_shrinks(overlay, [(640, h) for h in range(360, 20, -2)])

    assert (
        gone["volume_bar"]
        < gone["label_info"]
        < gone["label_text"]
        < gone["exit_button"]
    )
    assert gone["list_place_button"] == gone["label_text"]
    # the rest is in the one row kept to the last
    assert len(set(gone.values())) == 4


def test_close_and_play_are_kept_to_the_last(overlay):
    overlay.resize(60, 75)

    assert _shown(overlay) == {"exit_button", "play_pause_button"}


def test_in_a_cell_too_short_for_two_rows_they_are_in_one(overlay):
    overlay.resize(90, 50)

    assert _shown(overlay) == {"exit_button", "play_pause_button"}
    assert overlay.bottom_bar.indexOf(overlay.exit_button) >= 0
    _fits(overlay)

    overlay.lay_out_now()
    play = overlay.play_pause_button.geometry()
    close = overlay.exit_button.geometry()
    assert play.top() == close.top()
    assert play.right() < close.left()

    overlay.resize(640, 360)

    assert overlay.title_bar.indexOf(overlay.exit_button) >= 0
    assert "label_text" in _shown(overlay)


def test_a_cell_too_small_for_them_shows_only_its_frame(overlay):
    overlay.resize(40, 30)

    assert overlay.control_widget.isHidden()
    assert not overlay.border_widget.isHidden()


def test_they_come_back_as_it_gets_bigger(overlay):
    shown = _shown(overlay)

    overlay.resize(40, 30)
    overlay.resize(640, 360)

    assert _shown(overlay) == shown


def test_a_failed_cell_keeps_try_again_to_the_last(overlay):
    overlay.set_error_actions(has_details=True, can_go_next=True)
    overlay.set_mode(OverlayMode.ERROR)

    assert {"retry_button", "details_button", "next_button"} <= _shown(overlay)

    # room for Try Again and Next, not Details as well
    margins = 2 * CONTROL_MARGIN
    spacing = overlay.bottom_bar.spacing()
    retry = overlay.retry_button.width()
    next_ = overlay.next_button.width()
    # and the room kept in place of the bar, a gap apart
    overlay.resize(margins + retry + spacing + next_ + spacing, 360)
    shown = _shown(overlay)

    assert "retry_button" in shown
    assert "next_button" in shown
    assert "details_button" not in shown
    _fits(overlay)


def test_one_wanted_back_comes_back_only_with_room(overlay):
    overlay.resize(60, 75)
    overlay.set_list_place("4/12")

    assert "list_place_button" not in _shown(overlay)

    overlay.resize(640, 360)

    assert "list_place_button" in _shown(overlay)


def test_hidden_chrome_stays_hidden_whatever_the_size(overlay):
    overlay.set_is_chrome_visible(False)
    overlay.resize(500, 300)

    assert overlay.control_widget.isHidden()

    overlay.set_is_chrome_visible(True)

    assert not overlay.control_widget.isHidden()


def test_the_size_buttons_go_before_close_as_it_comes_back(overlay):
    overlay.set_cell_size_controls(is_shown=True, has_picker=True)
    overlay.resize(200, 50)
    overlay.resize(640, 360)

    row = overlay.title_bar
    close = row.indexOf(overlay.exit_button)
    buttons = [row.indexOf(b) for b in overlay._cell_size_buttons()]

    assert buttons == sorted(buttons)
    assert buttons[0] > 0
    assert buttons[-1] < close
    assert {"label_text", "exit_button"} <= _shown(overlay)
    assert not overlay.cell_size_button.isHidden()
