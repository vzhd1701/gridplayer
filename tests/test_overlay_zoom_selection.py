"""The part of a picture being selected to zoom to, outlined on the overlay.

See ZoomSelectManager for the selecting, and VideoBlock.show_zoom_selection
for the overlay shown for it.
"""

from functools import partial

import pytest
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QFontMetrics, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.widgets.video_overlay import OverlayBlock, OverlayBlockFloating

SELECTION = QRect(100, 80, 200, 120)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _shown(overlay, holder):
    holder.setAttribute(Qt.WA_DontShowOnScreen)
    holder.resize(640, 360)
    overlay.resize(640, 360)
    overlay.set_color("#ffffff")
    overlay.set_position(27000, 60000)

    holder.show()
    overlay.show()
    QApplication.processEvents()

    return overlay


@pytest.fixture
def overlay():
    holder = QWidget()
    overlay = _shown(OverlayBlock(holder), holder)

    yield overlay

    holder.close()


@pytest.fixture
def opaque_overlay():
    holder = QWidget()
    overlay = OverlayBlockFloating(holder)
    overlay.make_opaque()
    overlay = _shown(overlay, holder)

    yield overlay

    overlay.close()
    holder.close()


def _covers(mask: QRegion, rect: QRect) -> bool:
    return QRegion(rect).subtracted(mask).isEmpty()


class TestTheOutline:
    def test_it_is_shown_where_the_selection_is(self, overlay):
        overlay.set_zoom_selection(SELECTION)

        assert overlay.zoom_selection.isVisible()
        assert overlay.zoom_selection.selection == SELECTION
        # see-through, it is not cut to the lines
        assert overlay.zoom_selection.mask().isEmpty()

    @pytest.mark.parametrize("selection", [None, QRect(100, 80, 0, 120)])
    def test_none_or_an_empty_one_is_nothing_to_show(self, overlay, selection):
        overlay.set_zoom_selection(SELECTION)
        overlay.set_zoom_selection(selection)

        assert not overlay.zoom_selection.isVisible()

    def test_it_is_not_faded_with_the_rest(self, overlay):
        """Faded by an effect, all of the cell would be drawn offscreen
        again at every step of a selection."""

        overlay._set_opacity(0.5)

        assert overlay.zoom_selection.graphicsEffect() is None

    def test_it_is_in_the_video_s_colour(self, overlay):
        overlay.set_color("#ff8800")

        assert overlay.zoom_selection.color.name() == "#ff8800"


class TestOnTheOpaqueOverlay:
    """Nothing shows through it, so the window is cut to the lines alone."""

    def test_the_window_is_cut_to_the_lines(self, opaque_overlay):
        opaque_overlay.set_is_chrome_visible(False)
        opaque_overlay.set_zoom_selection(SELECTION)

        mask = opaque_overlay.mask()

        assert _covers(mask, QRect(100, 80, 200, 3))
        assert _covers(mask, QRect(100, 197, 200, 3))
        assert _covers(mask, QRect(100, 80, 3, 120))
        assert _covers(mask, QRect(297, 80, 3, 120))
        assert not mask.intersects(SELECTION.adjusted(3, 3, -3, -3))

    def test_it_follows_the_selection(self, opaque_overlay):
        opaque_overlay.set_is_chrome_visible(False)
        opaque_overlay.set_zoom_selection(SELECTION)
        opaque_overlay.set_zoom_selection(QRect(50, 50, 100, 100))

        mask = opaque_overlay.mask()

        assert _covers(mask, QRect(50, 50, 100, 3))
        assert not mask.intersects(QRect(100, 197, 200, 3))

    def test_done_the_lines_are_out_of_it(self, opaque_overlay):
        opaque_overlay.set_is_chrome_visible(False)
        opaque_overlay.set_zoom_selection(SELECTION)
        opaque_overlay.set_zoom_selection(None)

        assert not opaque_overlay.mask().intersects(SELECTION)


class TestItsOwnControls:
    def test_a_bar_is_one(self, overlay):
        bar = overlay.progress_bar
        middle = bar.mapToGlobal(bar.rect().center())

        assert overlay.is_control_at(middle)

    def test_a_button_is_one(self, overlay):
        button = overlay.play_pause_button
        middle = button.mapToGlobal(button.rect().center())

        assert overlay.is_control_at(middle)

    def test_which_item_of_its_list_is_one(self, overlay):
        overlay.set_list_place("3/12")
        QApplication.processEvents()

        button = overlay.list_place_button
        middle = button.mapToGlobal(button.rect().center())

        assert overlay.is_control_at(middle)

    def test_the_picture_is_not(self, overlay):
        assert not overlay.is_control_at(overlay.mapToGlobal(QPoint(320, 180)))

    def test_hidden_there_are_none(self, overlay):
        bar = overlay.progress_bar
        middle = bar.mapToGlobal(bar.rect().center())

        overlay.set_is_chrome_visible(False)

        assert not overlay.is_control_at(middle)

        overlay.hide()

        assert not overlay.is_control_at(middle)


def _block(mocker, **ctx):
    from gridplayer.widgets.video_block import VideoBlock

    block = mocker.Mock()
    block._zoom_selection = None
    block._is_zoom_hint_shown = False
    for name in (
        "show_zoom_selection",
        "show_zoom_hint",
        "_is_zoom_ui",
        "_zoom_ui_changed",
    ):
        setattr(block, name, partial(getattr(VideoBlock, name), block))
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = ctx.get("is_disable_overlay", False)
    block._ctx.is_overlay_hide_on_timeout = True
    block.is_overlay_fits = ctx.get("is_overlay_fits", True)

    return block


class TestTheCellWhileSelecting:
    def test_the_overlay_is_shown_with_the_selection_alone(self, mocker):
        from gridplayer.widgets.video_block import VideoBlock

        block = _block(mocker)

        VideoBlock.show_zoom_selection(block, SELECTION)
        VideoBlock.show_zoom_selection(block, QRect(100, 80, 250, 150))

        assert block.overlay.set_zoom_selection.call_args_list == [
            mocker.call(SELECTION),
            mocker.call(QRect(100, 80, 250, 150)),
        ]
        # once, when it starts
        block.overlay.set_is_chrome_visible.assert_called_once_with(False)
        block.overlay.show.assert_called_once_with()
        block.overlay_hide_timer.stop.assert_called_once_with()

    def test_it_is_not_hidden_meanwhile(self, mocker):
        from gridplayer.widgets.video_block import VideoBlock

        block = _block(mocker)

        VideoBlock.show_zoom_selection(block, SELECTION)
        VideoBlock.hide_overlay(block)

        block.overlay.hide.assert_not_called()

    def test_done_the_overlay_is_as_it_would_be(self, mocker):
        from gridplayer.widgets.video_block import VideoBlock

        block = _block(mocker)

        VideoBlock.show_zoom_selection(block, SELECTION)
        VideoBlock.show_zoom_selection(block, None)

        block.overlay.set_zoom_selection.assert_called_with(None)
        block.overlay.set_is_chrome_visible.assert_called_with(True)
        block.show_overlay.assert_called_once_with()
        assert block._zoom_selection is None

    @pytest.mark.parametrize(
        "ctx", [{"is_disable_overlay": True}, {"is_overlay_fits": False}]
    )
    def test_done_an_overlay_that_is_off_goes_again(self, mocker, ctx):
        from gridplayer.widgets.video_block import VideoBlock

        block = _block(mocker, **ctx)

        VideoBlock.show_zoom_selection(block, SELECTION)
        VideoBlock.show_zoom_selection(block, None)

        block.overlay.hide.assert_called_once_with()
        block.show_overlay.assert_not_called()

    def test_with_none_going_on_nothing_changes(self, mocker):
        from gridplayer.widgets.video_block import VideoBlock

        block = _block(mocker)

        VideoBlock.show_zoom_selection(block, None)

        block.overlay.set_zoom_selection.assert_not_called()
        block.show_overlay.assert_not_called()


class TestTheHintOnTheCell:
    def test_the_overlay_is_shown_with_the_hint_alone(self, mocker):
        block = _block(mocker)

        block.show_zoom_hint(True)

        block.overlay.set_zoom_hint.assert_called_once_with(True)
        block.overlay.set_is_chrome_visible.assert_called_once_with(False)
        block.overlay.show.assert_called_once_with()
        block.overlay_hide_timer.stop.assert_called_once_with()

    def test_it_is_not_hidden_meanwhile(self, mocker):
        from gridplayer.widgets.video_block import VideoBlock

        block = _block(mocker)

        block.show_zoom_hint(True)
        VideoBlock.hide_overlay(block)

        block.overlay.hide.assert_not_called()

    def test_from_the_hint_to_the_selection_the_chrome_stays_away(self, mocker):
        block = _block(mocker)

        block.show_zoom_hint(True)
        block.show_zoom_selection(SELECTION)
        # as the selecting goes on, the hint is let go of again
        block.show_zoom_hint(False)

        block.overlay.set_zoom_hint.assert_called_with(False)
        block.overlay.set_is_chrome_visible.assert_called_once_with(False)
        block.show_overlay.assert_not_called()

    def test_let_go_of_the_overlay_is_as_it_would_be(self, mocker):
        block = _block(mocker)

        block.show_zoom_hint(True)
        block.show_zoom_hint(False)

        block.overlay.set_is_chrome_visible.assert_called_with(True)
        block.show_overlay.assert_called_once_with()


def _hint_layout(overlay, width, height):
    overlay.resize(width, height)
    overlay.layout().activate()

    return overlay.zoom_hint._layout()


class TestTheHint:
    def test_it_says_how_in_the_middle(self, overlay):
        overlay.set_zoom_hint(True)

        lines, box = _hint_layout(overlay, 640, 360)

        assert overlay.zoom_hint.isVisible()
        assert lines == ("Drag to select an area to zoom in", "Esc to cancel")
        assert abs(box.center().x() - 320) <= 1
        assert abs(box.center().y() - 180) <= 1

    def test_a_small_cell_has_it_short(self, overlay):
        hint = overlay.zoom_hint
        metrics = QFontMetrics(hint.font())
        # the short one and its padding, inside the cell's padding
        width = metrics.horizontalAdvance("Drag to zoom in") + hint.padding * 4 + 2

        overlay.set_zoom_hint(True)

        lines, _ = _hint_layout(overlay, width, 120)

        assert lines == ("Drag to zoom in",)
        assert overlay.zoom_hint.isVisible()

    def test_one_too_small_for_any_has_none(self, overlay):
        overlay.set_zoom_hint(True)

        _hint_layout(overlay, 60, 40)

        assert not overlay.zoom_hint.isVisible()

    def test_let_go_of_it_is_gone(self, overlay):
        overlay.set_zoom_hint(True)
        overlay.set_zoom_hint(False)

        assert not overlay.zoom_hint.isVisible()

    def test_the_opaque_overlay_is_cut_to_it(self, opaque_overlay):
        opaque_overlay.set_is_chrome_visible(False)
        opaque_overlay.set_zoom_hint(True)

        _, box = opaque_overlay.zoom_hint._layout()
        mask = opaque_overlay.mask()

        assert _covers(mask, box)
        assert not mask.intersects(QRect(0, 0, 640, box.top()))
