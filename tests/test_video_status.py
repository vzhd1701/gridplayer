import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.video_status import VideoStatus


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _shown(status, width=480, height=300):
    status.resize(width, height)
    status.show()
    _settled()


def _settled():
    # sized, then the box asked for again at the width it was given
    for _ in range(3):
        QApplication.processEvents()


def test_text_said_after_the_cell_is_sized_is_as_large_as_ever():
    told_late = VideoStatus(status_text="")
    _shown(told_late)
    told_late.status_text = "Reading the list…"
    _settled()

    told_first = VideoStatus(status_text="Reading the list…")
    _shown(told_first)

    # the box as tall as the cell gives it room for, the font fitted to it
    assert told_late.status_info.isVisibleTo(told_late)
    assert told_late.status_info.minimumHeight() == 30
    assert told_late.status_info.maximumHeight() == 45
    assert told_late.status_info.geometry() == told_first.status_info.geometry()

    told_late.close()
    told_first.close()


@pytest.mark.parametrize("text", ["Reading the list…", "Resolving URL…"])
def test_a_text_ending_in_an_ellipsis_as_large_as_any(text):
    """Its own ellipsis is not the text cut short to fit."""

    ending = VideoStatus(status_text=text)
    _shown(ending, 800, 400)
    plain = VideoStatus(status_text=text.rstrip("…"))
    _shown(plain, 800, 400)

    font = ending.status_info.font().pixelSize()
    assert font > ending.status_info.min_font_size
    assert font == plain.status_info.font().pixelSize()
    assert ending.status_info.height() == plain.status_info.height()

    ending.close()
    plain.close()


def test_a_text_too_long_still_cut_short():
    status = VideoStatus(status_text="Reading " * 40)
    _shown(status)

    font = status.status_info.font()
    lines = status.status_info._get_lines_to_draw(
        font,
        status.status_info._text_box_for_size(
            status.status_info.width(), status.status_info.height()
        ),
    )

    assert lines[-1].endswith("…")
    status.close()


def test_no_text_no_box():
    status = VideoStatus(status_text="Loading")
    _shown(status)

    status.status_text = ""

    assert not status.status_info.isVisibleTo(status)
    status.close()


def test_a_cell_too_small_for_text_shows_none():
    status = VideoStatus(status_text="")
    status.resize(300, 100)
    status.show()
    QApplication.processEvents()

    status.status_text = "Reading the list…"

    assert not status.status_info.isVisibleTo(status)
    status.close()
