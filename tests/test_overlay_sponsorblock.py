"""SponsorBlock's segments on the seek bar, and under the mouse."""

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor

from gridplayer.models.seek_mark import SeekMark, SeekMarkKind, segments_at
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_elements import HIGHLIGHT_HOVER_PX

LENGTH = 60000

SPONSOR_COLOR = "#00d400"
HIGHLIGHT_COLOR = "#ff1684"

CHAPTERS = (
    SeekMark(5000, "Opening"),
    SeekMark(25000, "The Heist"),
)

SPONSOR = SeekMark(
    20000, "Sponsor", SeekMarkKind.SEGMENT, end_ms=35000, color=SPONSOR_COLOR
)

HIGHLIGHT = SeekMark(50000, "Highlight", SeekMarkKind.HIGHLIGHT, color=HIGHLIGHT_COLOR)


@pytest.fixture
def overlay():
    overlay = OverlayBlock()
    overlay.setAttribute(Qt.WA_DontShowOnScreen)
    overlay.resize(520, 200)
    overlay.set_color("#ffffff")
    overlay.set_is_stopped(False)
    # before any of the marks, so the progress is not under them
    overlay.set_position(1000, LENGTH)
    overlay.show()

    yield overlay

    overlay.close()


def _hover(overlay, fraction):
    bar = overlay.progress_bar
    x = round(bar.width() * fraction)

    overlay.floating_progress.on_mouse_over(
        bar.mapToParent(QPoint(x, 0)), x / bar.width(), bar.width()
    )

    return overlay.floating_progress


def _grab(overlay, marks):
    bar = overlay.progress_bar
    bar.marks = marks

    return bar.grab().toImage()


def _x_at(bar, time_ms):
    return round(bar.width() * time_ms / LENGTH)


def _is_colour(image, x, y, colour) -> bool:
    """Whether a pixel is this colour, near enough.

    The overlay is drawn at half opacity, and a colour taken there and back
    through premultiplied alpha comes out a step off in a channel or two.
    """

    got = image.pixelColor(x, y)
    want = QColor(colour)

    return all(
        abs(a - b) <= 2
        for a, b in zip(
            (got.red(), got.green(), got.blue()),
            (want.red(), want.green(), want.blue()),
            strict=True,
        )
    )


class TestWhereASegmentIs:
    def test_a_time_inside_one_is_in_it(self):
        assert segments_at((*CHAPTERS, SPONSOR), 30000) == [SPONSOR]

    def test_it_ends_where_it_says(self):
        assert segments_at((SPONSOR,), 35000) == []

    def test_a_highlight_is_found_by_being_near_it(self):
        assert segments_at((HIGHLIGHT,), 50400, near_ms=500) == [HIGHLIGHT]
        assert segments_at((HIGHLIGHT,), 50600, near_ms=500) == []


class TestOnTheBar:
    def test_a_segment_is_coloured_in_through_the_middle(self, overlay):
        bar = overlay.progress_bar
        x = _x_at(bar, 27000)

        image = _grab(overlay, (SPONSOR,))

        assert _is_colour(image, x, bar.height() // 2, SPONSOR_COLOR)

    def test_the_edges_are_left_to_the_progress_and_the_chapters(self, overlay):
        bar = overlay.progress_bar
        x = _x_at(bar, 27000)

        without = _grab(overlay, ())
        with_it = _grab(overlay, (SPONSOR,))

        assert with_it.pixel(x, 0) == without.pixel(x, 0)
        assert with_it.pixel(x, bar.height() - 1) == without.pixel(x, bar.height() - 1)

    def test_nothing_outside_it_is_touched(self, overlay):
        bar = overlay.progress_bar
        x = _x_at(bar, 45000)

        without = _grab(overlay, ())
        with_it = _grab(overlay, (SPONSOR,))

        assert with_it.pixel(x, bar.height() // 2) == without.pixel(
            x, bar.height() // 2
        )

    def test_one_too_short_for_a_pixel_still_shows(self, overlay):
        bar = overlay.progress_bar
        blip = SeekMark(
            30000, "Sponsor", SeekMarkKind.SEGMENT, end_ms=30001, color=SPONSOR_COLOR
        )

        image = _grab(overlay, (blip,))

        columns = [
            x
            for x in range(bar.width())
            if _is_colour(image, x, bar.height() // 2, SPONSOR_COLOR)
        ]

        assert len(columns) == 1

    def test_a_highlight_is_marked_where_it_is(self, overlay):
        bar = overlay.progress_bar
        x = _x_at(bar, HIGHLIGHT.time_ms)

        image = _grab(overlay, (HIGHLIGHT,))

        assert _is_colour(image, x, bar.height() // 2, HIGHLIGHT_COLOR)


class TestTheHoverLabel:
    def test_it_names_the_segment_below_the_chapter(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, SPONSOR))

        label = _hover(overlay, 30.5 / 60)

        assert label.text.startswith("0:30.")
        assert label.text.endswith(" - The Heist")
        assert label.segment_line == ("Sponsor", QColor(SPONSOR_COLOR))

    def test_outside_one_there_is_no_second_line(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, SPONSOR))

        label = _hover(overlay, 40.5 / 60)

        assert label.segment_line is None

    def test_one_outside_every_chapter_goes_under_the_time(self, overlay):
        overlay.set_seek_marks((SPONSOR,))

        label = _hover(overlay, 30.5 / 60)

        assert label.text.startswith("0:30.")
        assert label.segment_line[0] == "Sponsor"

    def test_the_second_line_makes_it_taller(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, SPONSOR))

        one_line = _hover(overlay, 40.5 / 60).height()
        two_lines = _hover(overlay, 30.5 / 60).height()

        assert two_lines > one_line

    def test_it_is_wide_enough_for_a_name_longer_than_the_time(self, overlay):
        long_name = SeekMark(
            20000,
            "Intermission/Intro Animation",
            SeekMarkKind.SEGMENT,
            end_ms=35000,
            color="#00ffff",
        )
        overlay.set_seek_marks((long_name,))

        label = _hover(overlay, 30.5 / 60)

        width = label.fontMetrics().horizontalAdvance("Intermission/Intro Animation")

        assert label.width() > width

    def test_pieces_of_one_kind_that_overlap_are_named_once(self, overlay):
        again = SeekMark(
            25000, "Sponsor", SeekMarkKind.SEGMENT, end_ms=40000, color=SPONSOR_COLOR
        )
        overlay.set_seek_marks((SPONSOR, again))

        label = _hover(overlay, 30.5 / 60)

        assert label.segment_line[0] == "Sponsor"

    def test_a_highlight_is_named_with_the_mouse_near_it(self, overlay):
        overlay.set_seek_marks((HIGHLIGHT,))
        bar = overlay.progress_bar
        near = (_x_at(bar, HIGHLIGHT.time_ms) + HIGHLIGHT_HOVER_PX - 1) / bar.width()
        far = (_x_at(bar, HIGHLIGHT.time_ms) + HIGHLIGHT_HOVER_PX * 3) / bar.width()

        assert _hover(overlay, near).segment_line[0] == "Highlight"
        assert _hover(overlay, far).segment_line is None

    def test_a_cell_with_no_room_above_the_bar_goes_without_it(self, overlay):
        overlay.set_seek_marks((SPONSOR,))
        one_line = _hover(overlay, 40.5 / 60).height()

        # the bar's top edge only as far down as a label of one line
        bar = overlay.progress_bar
        x = round(bar.width() * 30.5 / 60)
        overlay.floating_progress.on_mouse_over(
            QPoint(bar.mapToParent(QPoint(x, 0)).x(), one_line),
            x / bar.width(),
            bar.width(),
        )

        assert overlay.floating_progress.segment_line is None
        assert overlay.floating_progress.height() == one_line

    @pytest.mark.parametrize("fraction", [0.34, 0.5])
    def test_it_stays_inside_the_pane(self, overlay, fraction):
        overlay.set_seek_marks((*CHAPTERS, SPONSOR))

        label = _hover(overlay, fraction)

        assert label.x() >= 0
        assert label.y() >= 0
        assert label.x() + label.width() <= overlay.width()

    def test_it_paints(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, SPONSOR))

        label = _hover(overlay, 30.5 / 60)

        image = label.grab().toImage()

        assert any(
            _is_colour(image, x, y, SPONSOR_COLOR)
            for x in range(image.width())
            for y in range(image.height())
        )
