"""Bookmarks' markers above the seek bar, and the hover label naming them."""

from itertools import pairwise

import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt5.QtGui import QColor, QContextMenuEvent, QMouseEvent, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.widgets import video_overlay_elements
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayBlockFloating
from gridplayer.widgets.video_overlay_elements import (
    BOOKMARK_COLOR,
    BOOKMARK_HOVER_PX,
    BOOKMARK_MARKER,
    BOOKMARK_STRIP_HEIGHT,
    BOOKMARK_TAIL,
    HOVER_POINTER_HEIGHT,
    bookmark_markers,
    marker_colors,
    marker_under,
)

LENGTH = 60000

CHAPTERS = (SeekMark(5000, "Opening"), SeekMark(25000, "The Heist"))

GOAL = SeekMark(30000, "Goal", SeekMarkKind.BOOKMARK)

SPONSOR = SeekMark(
    20000, "Sponsor", SeekMarkKind.SEGMENT, end_ms=35000, color="#00d400"
)

# the strip's last row, where a marker's point is
TIP_ROW = BOOKMARK_STRIP_HEIGHT - 1


def _bookmark(time_ms, label):
    return SeekMark(time_ms, label, SeekMarkKind.BOOKMARK)


@pytest.fixture
def overlay():
    overlay = OverlayBlock()
    overlay.setAttribute(Qt.WA_DontShowOnScreen)
    overlay.resize(800, 200)
    overlay.set_color("#ffffff")
    overlay.set_is_stopped(False)
    # before any of the marks, so the progress is not under them
    overlay.set_position(1000, LENGTH)
    overlay.show()

    yield overlay

    overlay.close()


@pytest.fixture(autouse=True)
def cursor(mocker):
    """Where the mouse is, as the strip asks once its markers change: far
    off, unless a test puts it somewhere."""

    at = [QPoint(-10000, -10000)]
    mocker.patch.object(
        video_overlay_elements.QCursor, "pos", side_effect=lambda: at[0]
    )

    return at


def _strip(overlay):
    return overlay.bookmark_markers


def _marker_x(overlay, index=0):
    return _strip(overlay).markers[index][0]


def _send(widget, event):
    QApplication.sendEvent(widget, event)

    return event


def _mouse(kind, x, button=Qt.NoButton):
    buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button

    return QMouseEvent(kind, QPointF(x, 5), button, buttons, Qt.NoModifier)


def _move_over(overlay, x):
    return _send(_strip(overlay), _mouse(QEvent.MouseMove, x))


def _hover_bar_at(overlay, x):
    bar = overlay.progress_bar

    bar.mouse_over.emit(bar.mapToParent(QPoint(x, 0)), x / bar.width(), bar.width())

    return overlay.floating_progress


def _names(label):
    return [row.text for row in label.bookmark_rows]


def _is_colour(image, x, y, colour) -> bool:
    """Whether a pixel is this colour, near enough.

    The overlay is drawn at half opacity, and a colour taken there and back
    through premultiplied alpha comes out a step off in a channel or two.
    """

    got = image.pixelColor(x, y)
    want = QColor(colour)

    return got.alpha() > 0 and all(
        abs(a - b) <= 2
        for a, b in zip(
            (got.red(), got.green(), got.blue()),
            (want.red(), want.green(), want.blue()),
            strict=True,
        )
    )


def _grab(overlay):
    return _strip(overlay).grab().toImage()


class TestWhereTheMarkersStand:
    def test_each_stands_where_it_is(self):
        marks = (_bookmark(15000, "A"), _bookmark(45000, "B"))

        assert [x for x, _ in bookmark_markers(marks, LENGTH, 300)] == [75, 225]

    def test_ones_closer_than_a_marker_is_wide_share_one(self):
        a = _bookmark(15000, "A")
        b = _bookmark(15500, "B")

        assert bookmark_markers((b, a), LENGTH, 300) == [(75, [a, b])]

    def test_those_at_the_ends_are_kept_whole_grown_too(self):
        marks = (_bookmark(0, "A"), _bookmark(LENGTH, "B"))

        xs = [x for x, _ in bookmark_markers(marks, LENGTH, 300)]

        edge = BOOKMARK_TAIL.half_width

        assert xs == [edge, 300 - edge - 1]

    def test_chapters_and_segments_are_no_markers(self):
        assert bookmark_markers((*CHAPTERS, SPONSOR), LENGTH, 300) == []

    def test_with_no_length_there_is_nowhere_to_put_them(self):
        assert bookmark_markers((GOAL,), 0, 300) == []

    def test_two_close_part_once_as_the_bar_widens_never_to_join_again(self):
        """By whole pixels they parted and joined again pixel after pixel
        as the window was resized."""

        marks = (_bookmark(30000, "A"), _bookmark(30500, "B"))

        counts = [
            len(bookmark_markers(marks, LENGTH, width)) for width in range(300, 1500)
        ]
        changes = [i for i in range(1, len(counts)) if counts[i] != counts[i - 1]]

        assert counts[0] == 1
        assert counts[-1] == 2
        assert len(changes) == 1

    @pytest.mark.parametrize("width", range(600, 680))
    def test_those_apart_never_stand_nearer_than_a_marker_is_wide(self, width):
        marks = tuple(
            _bookmark(time_ms, str(time_ms))
            for time_ms in (0, 300, 29000, 30000, 30500, 31100, 59500, LENGTH)
        )

        xs = [x for x, _ in bookmark_markers(marks, LENGTH, width)]

        assert all(b - a >= BOOKMARK_MARKER.half_width * 2 for a, b in pairwise(xs))


class TestTheOneUnderTheMouse:
    MARKERS = ((75, ["A"]), (90, ["B"]))

    def test_it_is_the_nearest(self):
        assert marker_under(self.MARKERS, 80) == 0
        assert marker_under(self.MARKERS, 86) == 1

    def test_as_far_off_as_half_its_grown_width_and_a_pixel(self):
        assert marker_under(self.MARKERS, 75 - BOOKMARK_HOVER_PX) == 0
        assert marker_under(self.MARKERS, 75 - BOOKMARK_HOVER_PX - 1) is None


class TestTheBar:
    def test_it_is_left_to_the_chapters_and_segments(self, overlay):
        bar = overlay.progress_bar

        overlay.set_seek_marks((*CHAPTERS, SPONSOR))
        without = bar.grab().toImage()

        overlay.set_seek_marks((*CHAPTERS, SPONSOR, GOAL))
        with_it = bar.grab().toImage()

        assert with_it == without


class TestTheStrip:
    def test_it_is_up_while_there_are_bookmarks(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, GOAL))

        assert _strip(overlay).isVisible()

    def test_without_any_it_is_not(self, overlay):
        overlay.set_seek_marks(CHAPTERS)

        assert not _strip(overlay).isVisible()

    def test_nor_once_they_are_gone(self, overlay):
        overlay.set_seek_marks((GOAL,))
        overlay.set_seek_marks(())

        assert not _strip(overlay).isVisible()

    def test_it_stands_right_above_the_bar(self, overlay):
        overlay.set_seek_marks((GOAL,))
        bar = overlay.progress_bar

        assert _strip(overlay).geometry() == QRect(
            bar.x(), bar.y() - BOOKMARK_STRIP_HEIGHT, bar.width(), BOOKMARK_STRIP_HEIGHT
        )

    def test_it_follows_the_bar(self, overlay):
        overlay.set_seek_marks((GOAL,))
        bar = overlay.progress_bar

        overlay.resize(600, 300)
        QApplication.processEvents()

        assert _strip(overlay).geometry() == QRect(
            bar.x(), bar.y() - BOOKMARK_STRIP_HEIGHT, bar.width(), BOOKMARK_STRIP_HEIGHT
        )
        assert (
            _marker_x(overlay) == bookmark_markers((GOAL,), LENGTH, bar.width())[0][0]
        )

    def test_it_goes_with_the_bar_when_the_video_stops(self, overlay):
        overlay.set_seek_marks((GOAL,))

        overlay.set_is_stopped(True)
        assert not _strip(overlay).isVisible()

        overlay.set_is_stopped(False)
        assert _strip(overlay).isVisible()

    def test_a_video_with_no_length_has_none(self, overlay):
        overlay.set_seek_marks((GOAL,))

        overlay.set_position(1000, 0)

        assert not _strip(overlay).isVisible()

    def test_it_comes_back_with_the_overlay(self, overlay):
        overlay.set_seek_marks((GOAL,))

        overlay.hide()
        overlay.show()

        assert _strip(overlay).isVisible()

    def test_it_is_under_the_rest_of_the_controls(self, overlay):
        """In a short cell, a notice under the title shows over it."""

        siblings = overlay.control_widget.children()

        assert siblings.index(_strip(overlay)) < siblings.index(overlay.label_info)


class TestTheMarkers:
    def test_one_points_down_at_its_place_on_the_bar(self, overlay):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)

        image = _grab(overlay)

        assert _is_colour(image, x, TIP_ROW - 2, BOOKMARK_COLOR)
        # beside its point is the video
        assert image.pixelColor(x - BOOKMARK_MARKER.half_width, TIP_ROW).alpha() == 0

    def test_it_is_amber_to_its_sides(self, overlay):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)
        middle_row = BOOKMARK_STRIP_HEIGHT - BOOKMARK_MARKER.height + 2

        image = _grab(overlay)

        amber = [
            dx
            for dx in range(-6, 7)
            if _is_colour(image, x + dx, middle_row, BOOKMARK_COLOR)
        ]

        assert amber == list(range(-2, 3))

    def test_the_one_under_the_mouse_is_left_to_the_hover_label(self, overlay):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)

        _move_over(overlay, x + BOOKMARK_HOVER_PX)
        image = _grab(overlay)

        assert image.pixelColor(x, TIP_ROW - 2).alpha() == 0

    def test_the_others_stay(self, overlay):
        overlay.set_seek_marks((GOAL, _bookmark(50000, "Later")))

        _move_over(overlay, _marker_x(overlay, 0))
        image = _grab(overlay)

        later_x = _marker_x(overlay, 1)

        assert _is_colour(image, later_x, TIP_ROW - 2, BOOKMARK_COLOR)

    def test_with_the_mouse_gone_it_is_back(self, overlay):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)

        _move_over(overlay, x)
        _send(_strip(overlay), QEvent(QEvent.Leave))
        image = _grab(overlay)

        assert _is_colour(image, x, TIP_ROW - 2, BOOKMARK_COLOR)

    def test_two_close_together_stand_as_one(self, overlay):
        overlay.set_seek_marks((GOAL, _bookmark(30050, "Right after")))

        assert len(_strip(overlay).markers) == 1


class TestClicks:
    @pytest.fixture
    def clicked(self, overlay):
        clicked = []
        overlay.bookmark_clicked.connect(clicked.append)

        return clicked

    @pytest.fixture
    def menus(self, overlay):
        menus = []
        overlay.bookmark_menu_requested.connect(
            lambda pos, times: menus.append((pos, times))
        )

        return menus

    def test_a_click_on_a_marker_goes_to_its_bookmark(self, overlay, clicked):
        overlay.set_seek_marks((GOAL,))

        _send(
            _strip(overlay),
            _mouse(QEvent.MouseButtonPress, _marker_x(overlay), Qt.LeftButton),
        )

        assert clicked == [(30000,)]

    def test_one_as_far_off_as_it_grows_does_too(self, overlay, clicked):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay) - BOOKMARK_HOVER_PX

        _send(_strip(overlay), _mouse(QEvent.MouseButtonPress, x, Qt.LeftButton))

        assert clicked == [(30000,)]

    def test_a_shared_marker_tells_all_it_stands_for(self, overlay, clicked):
        overlay.set_seek_marks((_bookmark(30050, "Right after"), GOAL))

        _send(
            _strip(overlay),
            _mouse(QEvent.MouseButtonPress, _marker_x(overlay), Qt.LeftButton),
        )

        assert clicked == [(30000, 30050)]

    def test_the_whole_click_is_taken_so_the_video_is_not_paused(self, overlay):
        overlay.set_seek_marks((GOAL,))
        strip = _strip(overlay)
        x = _marker_x(overlay)

        pressed = _send(strip, _mouse(QEvent.MouseButtonPress, x, Qt.LeftButton))
        released = _send(strip, _mouse(QEvent.MouseButtonRelease, x, Qt.LeftButton))
        double = _send(strip, _mouse(QEvent.MouseButtonDblClick, x, Qt.LeftButton))

        assert pressed.isAccepted()
        assert released.isAccepted()
        assert double.isAccepted()

    def test_a_click_beside_the_markers_is_the_videos(self, overlay, clicked):
        overlay.set_seek_marks((GOAL,))
        strip = _strip(overlay)
        x = _marker_x(overlay) + BOOKMARK_HOVER_PX + 1

        pressed = _send(strip, _mouse(QEvent.MouseButtonPress, x, Qt.LeftButton))
        released = _send(strip, _mouse(QEvent.MouseButtonRelease, x, Qt.LeftButton))

        assert not pressed.isAccepted()
        assert not released.isAccepted()
        assert clicked == []

    def test_the_mouse_moving_over_it_is_still_seen_by_the_cell(self, overlay):
        """Which keeps the overlay up."""

        overlay.set_seek_marks((GOAL,))

        moved = _move_over(overlay, _marker_x(overlay))

        assert not moved.isAccepted()

    def test_a_right_click_asks_for_its_menu(self, overlay, clicked, menus):
        overlay.set_seek_marks((GOAL,))
        strip = _strip(overlay)
        x = _marker_x(overlay)

        _send(strip, _mouse(QEvent.MouseButtonPress, x, Qt.RightButton))
        asked = _send(
            strip,
            QContextMenuEvent(
                QContextMenuEvent.Mouse, QPoint(x, 5), strip.mapToGlobal(QPoint(x, 5))
            ),
        )

        assert asked.isAccepted()
        assert menus == [(strip.mapToGlobal(QPoint(x, 5)), (30000,))]
        assert clicked == []

    def test_a_shared_marker_offers_all_it_stands_for(self, overlay, menus):
        overlay.set_seek_marks((GOAL, _bookmark(30050, "Right after")))
        strip = _strip(overlay)
        x = _marker_x(overlay)

        _send(
            strip,
            QContextMenuEvent(
                QContextMenuEvent.Mouse, QPoint(x, 5), strip.mapToGlobal(QPoint(x, 5))
            ),
        )

        assert menus[0][1] == (30000, 30050)

    def test_a_right_click_beside_them_is_the_cells_menu(self, overlay, menus):
        overlay.set_seek_marks((GOAL,))
        strip = _strip(overlay)
        x = _marker_x(overlay) + BOOKMARK_HOVER_PX + 1

        asked = _send(
            strip,
            QContextMenuEvent(
                QContextMenuEvent.Mouse, QPoint(x, 5), strip.mapToGlobal(QPoint(x, 5))
            ),
        )

        assert not asked.isAccepted()
        assert menus == []


class TestTheHoverLabel:
    def test_over_the_bar_it_tells_the_time_there_only(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, GOAL))

        # right under the marker
        label = _hover_bar_at(overlay, _marker_x(overlay))

        assert label.text.startswith("0:30.")
        assert label.text.endswith(" - The Heist")
        assert label.bookmark_rows == ()

    def test_over_a_marker_it_names_its_bookmark(self, overlay):
        overlay.set_seek_marks((*CHAPTERS, GOAL))

        _move_over(overlay, _marker_x(overlay))
        label = overlay.floating_progress

        assert label.isVisible()
        assert label.text == "0:30.000 - The Heist"
        assert _names(label) == ["Goal"]

    def test_it_tells_the_bookmarks_own_time(self, overlay):
        """Not the time where the marker stands, a pixel's worth of it off."""

        just_before = _bookmark(29999, "Just before")
        overlay.set_seek_marks((just_before,))
        bar = overlay.progress_bar

        x = _marker_x(overlay)
        assert x / bar.width() * LENGTH >= 30000

        _move_over(overlay, x)

        assert overlay.floating_progress.text == "0:29.999"

    def test_a_shared_marker_names_all_it_stands_for(self, overlay):
        overlay.set_seek_marks((GOAL, _bookmark(30050, "Right after")))

        _move_over(overlay, _marker_x(overlay))

        assert _names(overlay.floating_progress) == ["Goal", "Right after"]

    def test_off_the_marker_it_is_gone(self, overlay):
        overlay.set_seek_marks((GOAL,))

        _move_over(overlay, _marker_x(overlay))
        _send(_strip(overlay), QEvent(QEvent.Leave))

        assert not overlay.floating_progress.isVisible()

    def test_it_stays_while_the_marker_changes_under_the_mouse(self, overlay, cursor):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)
        cursor[0] = _strip(overlay).mapToGlobal(QPoint(x, 5))

        _move_over(overlay, x)
        overlay.set_seek_marks((_bookmark(30000, "Renamed"),))

        label = overlay.floating_progress
        assert label.isVisible()
        assert _names(label) == ["Renamed"]

    def test_it_goes_where_the_marker_moves_from_under_the_mouse(self, overlay, cursor):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)
        cursor[0] = _strip(overlay).mapToGlobal(QPoint(x, 5))

        _move_over(overlay, x)
        overlay.set_seek_marks((_bookmark(50000, "Later"),))

        assert not overlay.floating_progress.isVisible()

    def test_over_a_marker_it_points_down_to_the_bar(self, overlay):
        overlay.set_seek_marks((GOAL,))

        _move_over(overlay, _marker_x(overlay))
        label = overlay.floating_progress

        assert label.geometry().bottom() + 1 == overlay.progress_bar.y()

    def test_its_pointer_is_the_marker_where_it_stands(self, overlay):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)

        _move_over(overlay, x)
        label = overlay.floating_progress
        image = label.grab().toImage()

        pointer_x = label._pointer_x
        tip_row = label.height() - 1

        assert (
            label.mapTo(overlay, QPoint(pointer_x, 0)).x()
            == _strip(overlay).mapTo(overlay, QPoint(x, 0)).x()
        )
        assert _is_colour(image, pointer_x, tip_row - 3, BOOKMARK_COLOR)
        # as wide as the marker grown, and pointed at its foot
        assert _is_colour(
            image, pointer_x - BOOKMARK_TAIL.half_width + 1, tip_row - 7, BOOKMARK_COLOR
        )
        assert (
            image.pixelColor(pointer_x - BOOKMARK_TAIL.half_width, tip_row).alpha() == 0
        )

    def test_its_box_sits_as_low_as_over_the_bar_but_for_the_markers_height(
        self, overlay
    ):
        overlay.set_seek_marks((GOAL,))
        x = _marker_x(overlay)
        label = overlay.floating_progress

        _move_over(overlay, x)
        over_the_marker = label.y() + label._text_box().bottom()

        _send(_strip(overlay), QEvent(QEvent.Leave))
        _hover_bar_at(overlay, x)
        over_the_bar = label.y() + label._text_box().bottom()

        assert over_the_bar - over_the_marker == (
            BOOKMARK_STRIP_HEIGHT - HOVER_POINTER_HEIGHT
        )

    def test_the_name_goes_after_its_marker(self, overlay):
        """As the segments' go after their squares, to tell them apart."""

        overlay.set_seek_marks((GOAL,))

        _move_over(overlay, _marker_x(overlay))
        label = overlay.floating_progress
        image = label.grab().toImage()

        box_bottom = label._text_box().bottom()

        assert any(
            _is_colour(image, x, y, BOOKMARK_COLOR)
            for x in range(image.width())
            for y in range(box_bottom + 1)
        )

    def test_over_the_bar_it_stands_on_the_bar_bookmarks_or_not(self, overlay):
        for marks in ((GOAL,), CHAPTERS):
            overlay.set_seek_marks(marks)

            label = _hover_bar_at(overlay, 100)

            assert label.geometry().bottom() + 1 == overlay.progress_bar.y()

    def test_over_the_bar_its_pointer_is_its_own(self, overlay):
        overlay.set_seek_marks((GOAL,))

        _move_over(overlay, _marker_x(overlay))
        _send(_strip(overlay), QEvent(QEvent.Leave))
        label = _hover_bar_at(overlay, 100)
        image = label.grab().toImage()

        assert label.height() - label._text_box().height() == HOVER_POINTER_HEIGHT
        assert not any(
            _is_colour(image, x, y, BOOKMARK_COLOR)
            for x in range(image.width())
            for y in range(image.height())
        )

    def test_it_comes_above_the_segment_the_bookmark_is_in(self, overlay):
        overlay.set_seek_marks((SPONSOR, GOAL))

        _move_over(overlay, _marker_x(overlay))
        label = overlay.floating_progress

        assert [line.text for line in label._under_lines()] == ["Goal", "Sponsor"]

    def test_each_line_makes_it_taller(self, overlay):
        overlay.set_seek_marks((SPONSOR, GOAL))
        x = _marker_x(overlay)

        _move_over(overlay, x)
        three_lines = overlay.floating_progress.height()

        two_lines = _hover_bar_at(overlay, x).height()

        assert three_lines > two_lines

    def test_a_short_cell_lets_sponsorblocks_line_go_first(self, overlay):
        overlay.set_seek_marks((SPONSOR, GOAL))
        label = overlay.floating_progress
        bookmarks = (GOAL,)

        label.on_marker_over(QPoint(100, 500), (GOAL,), 400)
        three_lines = label.height()
        overlay.set_seek_marks((GOAL,))
        label.on_marker_over(QPoint(100, 500), bookmarks, 400)
        two_lines = label.height()
        overlay.set_seek_marks((SPONSOR, GOAL))

        # the bar's top edge only as far down as a label of two lines
        label.on_marker_over(QPoint(100, two_lines), bookmarks, 400)

        assert three_lines > two_lines
        assert _names(label) == ["Goal"]
        assert label.segment_line is None
        assert label.height() == two_lines

    def test_a_cell_shorter_still_goes_without_either(self, overlay):
        overlay.set_seek_marks((SPONSOR, GOAL))
        label = overlay.floating_progress

        label.on_marker_over(QPoint(100, 500), (GOAL,), 400)
        lines = len(label._under_lines())

        label.on_marker_over(QPoint(100, 20), (GOAL,), 400)

        assert lines == 2
        assert label.bookmark_rows == ()
        assert label.segment_line is None


class TestOnTheOpaqueOverlay:
    @pytest.fixture
    def opaque(self):
        holder = QWidget()
        holder.setAttribute(Qt.WA_DontShowOnScreen)
        holder.resize(640, 360)

        overlay = OverlayBlockFloating(holder)
        overlay.make_opaque()
        overlay.resize(640, 360)
        overlay.set_color("#ffffff")
        overlay.set_is_stopped(False)
        overlay.set_position(1000, LENGTH)

        holder.show()
        overlay.show()
        QApplication.processEvents()

        yield overlay

        overlay.close()
        holder.close()

    def _in_overlay(self, overlay, x, y):
        return _strip(overlay).mapTo(overlay, QPoint(x, y))

    def test_the_window_takes_in_the_markers(self, opaque):
        opaque.set_seek_marks((GOAL,))
        x = _marker_x(opaque)

        assert opaque.mask().contains(self._in_overlay(opaque, x, TIP_ROW - 2))

    def test_and_no_box_round_them(self, opaque):
        """Painted in the overlay's colour, it would show round each one."""

        opaque.set_seek_marks((GOAL,))
        x = _marker_x(opaque)

        corner = self._in_overlay(opaque, x - BOOKMARK_HOVER_PX, 0)

        assert not opaque.mask().contains(corner)

    def test_the_strip_is_cut_to_what_it_paints(self, opaque):
        opaque.set_seek_marks((GOAL, _bookmark(50000, "Later")))
        strip = _strip(opaque)

        image = _grab(opaque)

        painted = QRegion()
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() >= 128:
                    painted += QRegion(x, y, 1, 1)

        assert strip.mask() == painted

    def test_the_one_under_the_mouse_is_taken_in_as_the_labels_pointer(self, opaque):
        opaque.set_seek_marks((GOAL,))
        x = _marker_x(opaque)
        # the pointer is the marker grown: wider than it and as tall as the
        # strip
        grown_edge = self._in_overlay(opaque, x - BOOKMARK_TAIL.half_width + 1, 1)

        assert not opaque.mask().contains(grown_edge)

        _move_over(opaque, x)
        assert opaque.mask().contains(grown_edge)
        assert not _strip(opaque).mask().contains(QPoint(x, TIP_ROW - 2))

        _send(_strip(opaque), QEvent(QEvent.Leave))
        assert not opaque.mask().contains(grown_edge)
        assert _strip(opaque).mask().contains(QPoint(x, TIP_ROW - 2))

    def test_the_label_is_cut_to_its_box_and_the_marker(self, opaque):
        """Beside the marker's point is the video, not the label's colour."""

        opaque.set_seek_marks((GOAL,))

        _move_over(opaque, _marker_x(opaque))
        label = opaque.floating_progress
        shape = label.mask()
        middle = label._pointer_x
        tip_row = label.height() - 1

        assert shape.contains(QPoint(middle, tip_row))
        assert shape.contains(QPoint(middle - BOOKMARK_TAIL.half_width, tip_row - 8))
        assert not shape.contains(QPoint(middle - BOOKMARK_TAIL.half_width, tip_row))
        assert not shape.contains(
            QPoint(middle - BOOKMARK_TAIL.half_width - 2, tip_row - 8)
        )

    def test_and_leaves_the_video_between_them(self, opaque):
        opaque.set_seek_marks((GOAL, _bookmark(50000, "Later")))
        x = _marker_x(opaque)

        between = self._in_overlay(opaque, x + BOOKMARK_HOVER_PX + 10, 5)

        assert not opaque.mask().contains(between)

    def test_one_added_is_taken_in_at_once(self, opaque):
        opaque.set_seek_marks((GOAL,))
        opaque.set_seek_marks((GOAL, _bookmark(50000, "Later")))
        later_x = _marker_x(opaque, 1)

        assert opaque.mask().contains(self._in_overlay(opaque, later_x, 5))

    def test_one_removed_leaves_it(self, opaque):
        opaque.set_seek_marks((GOAL, _bookmark(50000, "Later")))
        later_x = _marker_x(opaque, 1)

        opaque.set_seek_marks((GOAL,))

        assert not opaque.mask().contains(self._in_overlay(opaque, later_x, 5))

    def test_the_markers_are_painted_through_the_cut(self, opaque):
        opaque.set_seek_marks((GOAL,))
        x = _marker_x(opaque)

        image = _grab(opaque)

        assert _is_colour(image, x, TIP_ROW - 2, BOOKMARK_COLOR)


class TestTheHoverLabelOverASharedMarker:
    SHARED = (
        _bookmark(30000, "Goal"),
        _bookmark(30050, "Right after"),
    )

    def _over(self, overlay, position):
        overlay.set_seek_marks(self.SHARED)
        overlay.set_position(position, LENGTH)
        _move_over(overlay, _marker_x(overlay))

        return overlay.floating_progress

    def _bold_txt(self, label):
        bold = [row.text for row in label.bookmark_rows if row.is_bold]

        return bold[0] if bold else None

    def test_the_one_the_video_is_on_is_in_bold_its_time_told(self, overlay):
        label = self._over(overlay, 30050)

        assert _names(label) == ["Goal", "Right after"]
        assert self._bold_txt(label) == "Right after"
        assert label.text.startswith("0:30.050")

    def test_on_none_of_them_none_is_bold_the_first_s_time_told(self, overlay):
        label = self._over(overlay, 1000)

        assert self._bold_txt(label) is None
        assert label.text.startswith("0:30.000")

    def test_it_follows_the_video_while_the_mouse_stays(self, overlay):
        label = self._over(overlay, 30000)

        assert self._bold_txt(label) == "Goal"

        overlay.set_position(30050, LENGTH)

        assert self._bold_txt(label) == "Right after"

    def test_one_standing_alone_is_never_bold(self, overlay):
        overlay.set_seek_marks((GOAL,))
        overlay.set_position(30000, LENGTH)
        _move_over(overlay, _marker_x(overlay))

        assert not any(row.is_bold for row in overlay.floating_progress.bookmark_rows)


RED = "#ff3d3d"
GREEN = "#3ddc5a"
BLUE = "#3d8bff"


def _colored(time_ms, label, color):
    return SeekMark(time_ms, label, SeekMarkKind.BOOKMARK, color=color)


def _across(image, x, row, colors):
    """Which of these colours each pixel across a marker is, from two to
    its left to two to its right; None for one that is none of them."""

    return [
        next((c for c in colors if _is_colour(image, x + dx, row, c)), None)
        for dx in range(-2, 3)
    ]


class TestTheirColours:
    # a row through a marker's sides, above its point
    ROW = BOOKMARK_STRIP_HEIGHT - BOOKMARK_MARKER.height + 2

    def test_one_given_a_colour_is_drawn_in_it(self, overlay):
        overlay.set_seek_marks((_colored(30000, "Goal", BLUE),))
        x = _marker_x(overlay)

        image = _grab(overlay)

        assert _across(image, x, self.ROW, (BLUE,)) == [BLUE] * 5
        assert _is_colour(image, x, TIP_ROW - 2, BLUE)

    def test_one_given_none_is_the_bookmarks_own(self, overlay):
        overlay.set_seek_marks((_colored(30000, "Goal", None),))

        image = _grab(overlay)

        assert _is_colour(image, _marker_x(overlay), self.ROW, BOOKMARK_COLOR)

    def test_one_shared_by_two_colours_is_striped_with_them_side_by_side(self, overlay):
        overlay.set_seek_marks(
            (_colored(30000, "Goal", RED), _colored(30050, "Replay", GREEN))
        )
        x = _marker_x(overlay)

        image = _grab(overlay)

        # the first's the wider, its point and all
        assert _across(image, x, self.ROW, (RED, GREEN)) == [RED] * 3 + [GREEN] * 2
        assert _is_colour(image, x, TIP_ROW - 2, RED)

    def test_of_three_the_middle_one_is_a_pixel_between_the_other_two(self, overlay):
        overlay.set_seek_marks(
            (
                _colored(30000, "Goal", RED),
                _colored(30050, "Replay", GREEN),
                _colored(30100, "Again", BLUE),
            )
        )

        image = _grab(overlay)

        assert _across(image, _marker_x(overlay), self.ROW, (RED, GREEN, BLUE)) == [
            RED,
            RED,
            GREEN,
            BLUE,
            BLUE,
        ]

    def test_two_of_one_colour_are_one_stripe(self, overlay):
        overlay.set_seek_marks(
            (_colored(30000, "Goal", BLUE), _colored(30050, "Replay", BLUE))
        )

        image = _grab(overlay)

        assert _across(image, _marker_x(overlay), self.ROW, (BLUE,)) == [BLUE] * 5

    def test_the_one_under_the_mouse_is_the_labels_pointer_in_its_colour(self, overlay):
        overlay.set_seek_marks((_colored(30000, "Goal", BLUE),))

        _move_over(overlay, _marker_x(overlay))
        label = overlay.floating_progress
        image = label.grab().toImage()

        assert _is_colour(image, label._pointer_x, label.height() - 4, BLUE)

    def test_and_striped_where_it_stands_for_several(self, overlay):
        overlay.set_seek_marks(
            (_colored(30000, "Goal", RED), _colored(30050, "Replay", GREEN))
        )

        _move_over(overlay, _marker_x(overlay))
        label = overlay.floating_progress
        image = label.grab().toImage()

        x = label._pointer_x
        row = label.height() - 8

        assert [
            next((c for c in (RED, GREEN) if _is_colour(image, x + dx, row, c)), None)
            for dx in range(-3, 4)
        ] == [RED] * 4 + [GREEN] * 3


class TestMarkerColours:
    def test_each_colour_once_first_to_last(self):
        assert marker_colors([BLUE, None, BLUE, RED]) == [
            QColor(BLUE),
            QColor(BOOKMARK_COLOR),
            QColor(RED),
        ]

    def test_no_more_than_there_is_room_for(self):
        assert len(marker_colors([RED, GREEN, BLUE, "#ffffff"])) == 3

    def test_with_none_told_the_bookmarks_own(self):
        assert marker_colors([]) == [QColor(BOOKMARK_COLOR)]


def _six(gap_ms=20):
    return tuple(_colored(30000 + i * gap_ms, f"B{i}", RED) for i in range(6))


class TestTheRowsOfASharedMarker:
    """Over a marker standing for several, each is named on a row of its
    own, after its marker in its colour."""

    def _over(self, overlay, *bookmarks, position=1000):
        overlay.set_seek_marks(bookmarks)
        overlay.set_position(position, LENGTH)
        _move_over(overlay, _marker_x(overlay))

        return overlay.floating_progress

    def test_each_is_a_row_after_its_marker_in_its_colour(self, overlay):
        label = self._over(
            overlay, _colored(30000, "Goal", RED), _colored(30050, "Replay", GREEN)
        )

        assert _names(label) == ["Goal", "Replay"]
        assert [row.marker for row in label.bookmark_rows] == [
            QColor(RED),
            QColor(GREEN),
        ]
        assert all(row.is_listed for row in label.bookmark_rows)

    def test_of_one_colour_they_have_their_markers_all_the_same(self, overlay):
        label = self._over(
            overlay, _colored(30000, "Goal", None), _colored(30050, "Replay", None)
        )

        assert [row.marker for row in label.bookmark_rows] == [
            QColor(BOOKMARK_COLOR)
        ] * 2

    def test_one_standing_alone_is_named_after_its_marker_too(self, overlay):
        label = self._over(overlay, _colored(30000, "Goal", BLUE))

        assert [(row.text, row.marker, row.is_bold) for row in label.bookmark_rows] == [
            ("Goal", QColor(BLUE), False)
        ]

    def test_past_four_rows_the_last_says_how_many_more(self, overlay):
        label = self._over(overlay, *_six())

        assert _names(label) == ["B0", "B1", "B2", ""]
        assert label.bookmark_rows[-1].after == "+3 more"
        assert label.bookmark_rows[-1].marker is None

    def test_they_keep_the_one_the_video_is_on_in_sight(self, overlay):
        label = self._over(overlay, *_six(), position=30080)

        assert _names(label) == ["B3", "B4", "B5", ""]
        assert [row.is_bold for row in label.bookmark_rows] == [
            False,
            True,
            False,
            False,
        ]

    def test_a_short_cell_takes_rows_away_one_at_a_time(self, overlay):
        six = _six()
        overlay.set_seek_marks(six)
        label = overlay.floating_progress

        seen = []
        bar_y = 500

        while True:
            label.on_marker_over(QPoint(100, bar_y), six, 400)
            seen.append([(row.text, row.after) for row in label.bookmark_rows])

            if not label.bookmark_rows:
                break

            # the bar's top edge a pixel short of this label
            bar_y = label.height() - 1

        assert seen == [
            [("B0", ""), ("B1", ""), ("B2", ""), ("", "+3 more")],
            [("B0", ""), ("B1", ""), ("", "+4 more")],
            [("B0", ""), ("", "+5 more")],
            [("B0", "+5 more")],
            [],
        ]

    def test_a_long_name_is_cut_short_on_its_row(self, overlay):
        label = self._over(
            overlay, _colored(30000, "X" * 300, RED), _colored(30050, "Replay", GREEN)
        )

        assert label.bookmark_rows[0].text.endswith("…")
        assert _names(label)[1] == "Replay"
        assert label.width() <= overlay.width()

    def test_they_are_drawn_one_under_another_lined_up(self, overlay):
        label = self._over(
            overlay, _colored(30000, "Goal", RED), _colored(30050, "Replay", GREEN)
        )

        image = label.grab().toImage()
        # above the pointer, which is striped with them too
        text_box = label._text_box()

        def pixels(colour):
            return {
                (x, y)
                for x in range(image.width())
                for y in range(text_box.bottom())
                if _is_colour(image, x, y, colour)
            }

        red, green = pixels(RED), pixels(GREEN)

        assert red
        assert green
        assert max(y for _, y in red) < min(y for _, y in green)
        assert {x for x, _ in red} == {x for x, _ in green}
