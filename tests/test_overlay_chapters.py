"""Chapters on the seek bar: the notches, and the label that names them."""

import math

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.seek_mark import SeekMark, chapter_at
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_elements import chapter_notch_half_width

LENGTH = 60000

MARKS = (
    SeekMark(5000, "Opening"),
    SeekMark(25000, "The Heist"),
    SeekMark(40000, "Credits roll and a very long chapter name that goes on"),
)


@pytest.fixture
def overlay():
    overlay = OverlayBlock()
    overlay.setAttribute(Qt.WA_DontShowOnScreen)
    overlay.resize(520, 200)
    overlay.set_color("#ffffff")
    overlay.set_is_stopped(False)
    overlay.set_position(27000, LENGTH)
    overlay.show()

    yield overlay

    overlay.close()


def _hover(overlay, fraction):
    bar = overlay.progress_bar
    x = round(bar.width() * fraction)

    overlay.floating_progress.on_mouse_over(
        bar.mapToParent(QPoint(x, 0)), x / bar.width()
    )

    return overlay.floating_progress


class TestWhereAChapterIs:
    def test_a_time_inside_a_chapter_is_in_it(self):
        mark, start_ms, end_ms = chapter_at(MARKS, 30000, LENGTH)

        assert (mark.label, start_ms, end_ms) == ("The Heist", 25000, 40000)

    def test_the_last_one_runs_to_the_end(self):
        _, _, end_ms = chapter_at(MARKS, 50000, LENGTH)

        assert end_ms == LENGTH

    def test_before_the_first_one_is_in_none(self):
        assert chapter_at(MARKS, 1000, LENGTH) is None


class TestTheHoverLabel:
    # hovered mid-second: the mouse is on a whole pixel, a tenth of a second
    # either side of the fraction asked for

    def test_it_names_the_chapter_under_the_mouse(self, overlay):
        overlay.set_seek_marks(MARKS)

        label = _hover(overlay, 30.5 / 60)

        assert label.text == "0:30 - The Heist"

    def test_before_the_first_chapter_it_is_only_the_time(self, overlay):
        overlay.set_seek_marks(MARKS)

        assert _hover(overlay, 3.5 / 60).text == "0:03"

    def test_without_chapters_it_is_only_the_time(self, overlay):
        assert _hover(overlay, 30.5 / 60).text == "0:30"

    def test_a_name_too_long_for_the_pane_is_cut_short(self, overlay):
        overlay.resize(260, 150)
        overlay.set_seek_marks(MARKS)

        label = _hover(overlay, 54.5 / 60)

        # a bar this narrow is a second or so to the pixel, so the time is
        # only near where the mouse is
        time_txt, _, name = label.text.partition(" - ")

        assert time_txt.startswith("0:5")
        assert name.startswith("Credits")
        assert name.endswith("…")
        assert label.width() <= overlay.width()

    @pytest.mark.parametrize("fraction", [0.0, 0.02, 0.98, 1.0])
    def test_it_stays_inside_the_pane_at_either_end(self, overlay, fraction):
        overlay.set_seek_marks(MARKS)

        label = _hover(overlay, fraction)

        assert label.x() >= 0
        assert label.x() + label.width() <= overlay.width()

    def test_the_pointer_stays_under_the_mouse_when_it_is_pushed_in(self, overlay):
        overlay.set_seek_marks(MARKS)

        bar = overlay.progress_bar
        mouse_x = bar.mapToParent(QPoint(bar.width(), 0)).x()

        label = _hover(overlay, 1.0)

        assert label.x() + label._pointer_x == pytest.approx(mouse_x, abs=5)

    def test_it_is_sized_for_the_new_text_before_it_is_placed(self, overlay):
        """Sizing at the next paint left it off centre for a frame."""

        overlay.set_seek_marks(MARKS)

        label = _hover(overlay, 0.05)
        short_width = label.width()

        label = _hover(overlay, 0.5)

        assert label.width() > short_width
        middle = label.x() + label.width() // 2
        mouse_x = overlay.progress_bar.mapToParent(
            QPoint(round(overlay.progress_bar.width() * 0.5), 0)
        ).x()
        assert middle == pytest.approx(mouse_x, abs=1)


class TestTheNotches:
    def _grab(self, overlay, marks, hovered_x=None, monkeypatch=None):
        bar = overlay.progress_bar
        bar.marks = marks

        if hovered_x is not None:
            bar.progress_select_x = hovered_x
            monkeypatch.setattr(bar, "underMouse", lambda: True)

        return bar.grab().toImage()

    def test_a_chapter_is_marked_on_the_bar(self, overlay):
        without = self._grab(overlay, ())
        with_marks = self._grab(overlay, MARKS)

        assert with_marks != without

    def test_the_notch_leaves_the_middle_of_the_bar_to_the_loop_marks(self, overlay):
        bar = overlay.progress_bar
        x = round(bar.width() * 40000 / LENGTH)
        middle = bar.height() // 2

        without = self._grab(overlay, ())
        with_marks = self._grab(overlay, MARKS)

        assert with_marks.pixel(x, 0) != without.pixel(x, 0)
        assert with_marks.pixel(x, bar.height() - 1) != without.pixel(
            x, bar.height() - 1
        )
        assert with_marks.pixel(x, middle) == without.pixel(x, middle)

    def test_a_chapter_at_the_very_start_is_not_marked(self, overlay):
        without = self._grab(overlay, ())
        at_start = self._grab(overlay, (SeekMark(0, "Opening"),))

        assert at_start == without

    def test_the_chapter_under_the_mouse_stands_out(self, overlay, monkeypatch):
        bar = overlay.progress_bar
        hovered_x = round(bar.width() * 0.5)
        inside_x = round(bar.width() * 0.6)
        outside_x = round(bar.width() * 0.8)
        middle = bar.height() // 2

        plain = self._grab(overlay, (), hovered_x, monkeypatch)
        highlighted = self._grab(overlay, MARKS, hovered_x, monkeypatch)

        assert highlighted.pixel(inside_x, middle) != plain.pixel(inside_x, middle)
        assert highlighted.pixel(outside_x, middle) == plain.pixel(outside_x, middle)


@pytest.fixture
def cell():
    """An overlay at any width, which a window of its own would not go down to."""

    holder = QWidget()
    holder.setAttribute(Qt.WA_DontShowOnScreen)
    holder.resize(1200, 300)

    overlay = OverlayBlock(holder)
    overlay.set_color("#ffffff")
    overlay.set_is_stopped(False)
    overlay.set_position(27000, LENGTH)
    holder.show()

    def _sized(width):
        overlay.setGeometry(0, 0, width, 200)
        overlay._sync_progress_label()
        QApplication.processEvents()

        return overlay.progress_bar

    yield _sized

    holder.close()


def _notched_columns(bar, time_ms):
    """The columns along the top edge that one chapter's notch darkens."""

    bar.marks = ()
    without = bar.grab().toImage()

    bar.marks = (SeekMark(time_ms, "Chapter"),)
    with_mark = bar.grab().toImage()

    return [
        column
        for column in range(bar.width())
        if with_mark.pixel(column, 0) != without.pixel(column, 0)
    ]


class TestNotchesNarrowWithTheBar:
    def test_they_only_ever_get_narrower_as_the_bar_does(self):
        widths = [chapter_notch_half_width(w) for w in range(1000)]

        assert widths == sorted(widths)
        assert widths[0] == 0

    def test_a_small_cell_gets_a_one_pixel_tick(self, cell):
        # a 150px cell, the smallest that shows its controls at all
        bar = cell(150)

        columns = _notched_columns(bar, 30000)

        assert columns == [math.ceil(bar.width() * 30000 / LENGTH)]

    def test_a_large_cell_gets_the_full_wedge(self, cell):
        bar = cell(640)

        assert chapter_notch_half_width(bar.width()) == 3
        assert len(_notched_columns(bar, 30000)) >= 5

    def test_notches_too_close_to_tell_apart_are_left_out(self, cell):
        bar = cell(640)

        one_px_ms = LENGTH / bar.width()

        bar.marks = (SeekMark(30000, "A"),)
        one = bar.grab().toImage()

        bar.marks = (SeekMark(30000, "A"), SeekMark(int(30000 + one_px_ms * 3), "B"))
        crowded = bar.grab().toImage()

        assert crowded == one
