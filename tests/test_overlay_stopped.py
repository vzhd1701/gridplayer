from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QImage, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.params.actions import ACTIONS
from gridplayer.params.static import VideoEndAction
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.widgets.cell_chrome import dashed_frame
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_status import StatusControl
from gridplayer.widgets.video_overlay import (
    OverlayBlock,
    OverlayBlockFloating,
    OverlayMode,
)
from gridplayer.widgets.video_overlay_elements import (
    OverlayBorder,
    OverlayDropIndicator,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_stopped_overlay_offers_play_only():

    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_position(1000, 10_000)

    assert not overlay.progress_bar.isHidden()

    overlay.set_mode(OverlayMode.STOPPED)

    assert not overlay.play_button.isHidden()
    assert overlay.stop_button.isHidden()
    assert overlay.progress_bar.isHidden()
    assert overlay.label_progress.isHidden()
    assert overlay.floating_progress.isHidden()
    assert overlay.play_pause_button.isHidden()
    assert overlay.volume_button.isHidden()
    assert overlay.volume_bar.isHidden()
    assert not overlay.progress_bar_placeholder.isHidden()

    overlay.set_position(2000, 10_000)

    assert overlay.progress_bar.isHidden()

    overlay.set_mode(OverlayMode.VIDEO)

    assert not overlay.progress_bar.isHidden()
    assert not overlay.play_pause_button.isHidden()
    assert overlay.play_button.isHidden()


def test_stopped_overlay_play_plays():
    overlay = OverlayBlock()
    played = []
    overlay.play_pause_clicked.connect(lambda: played.append(True))

    overlay.play_button.clicked.emit()

    assert played == [True]


def _shown_in(overlay, mode):
    overlay.set_mode(mode)
    QApplication.processEvents()

    return {
        OverlayMode.STOPPED: overlay.play_button,
        OverlayMode.LOADING: overlay.stop_button,
        OverlayMode.VIDEO: overlay.play_pause_button,
    }[mode]


def _sign_box(button) -> QRect:
    """Where the button's sign is drawn, in its first square: its pixels
    nearer the ink than the box, the edges smoothed as they are."""

    image = button.grab().toImage()
    ink = button.text_color
    box = button.fill_color
    side = button.height()

    def far(color, other):
        return sum(abs(a - b) for a, b in zip(color.getRgb()[:3], other.getRgb()[:3]))

    # clear of the box's rounded, half see-through corners
    inside = range(2, side - 2)

    points = []

    for x in inside:
        for y in inside:
            color = QColor(image.pixel(x, y))

            if far(color, ink) < far(color, box):
                points.append((x, y))

    xs = [x for x, _ in points]
    ys = [y for _, y in points]

    return QRect(QPoint(min(xs), min(ys)), QPoint(max(xs), max(ys)))


def test_play_stop_and_pause_follow_each_other_in_one_place():
    """Play on a stopped cell, Stop while it loads, then the video's own
    pause: each where the one before was, its sign as large."""

    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_position(1000, 10_000)
    overlay.set_is_paused(False)

    places = {}
    signs = {}

    for mode in (OverlayMode.STOPPED, OverlayMode.LOADING, OverlayMode.VIDEO):
        button = _shown_in(overlay, mode)
        places[mode] = (button.x(), button.y())
        signs[mode] = _sign_box(button)

    assert len(set(places.values())) == 1

    pause = signs[OverlayMode.VIDEO]
    for mode in (OverlayMode.STOPPED, OverlayMode.LOADING):
        assert signs[mode].left() == pause.left()
        assert abs(signs[mode].right() - pause.right()) <= 1
        assert signs[mode].height() >= pause.height() - 2


def test_leaving_stopped_shows_timecode_without_resize():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_mode(OverlayMode.STOPPED)
    overlay.set_mode(OverlayMode.VIDEO)
    overlay.set_position(1500, 10_000)

    assert overlay.progress_bar.isEnabled()
    assert not overlay.progress_bar.isHidden()
    assert not overlay.label_progress.isHidden()
    assert "/" in overlay.label_progress.text


def test_loading_overlay_offers_stop_only():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_position(1000, 10_000)

    overlay.set_mode(OverlayMode.LOADING)

    assert not overlay.stop_button.isHidden()
    assert overlay.play_pause_button.isHidden()
    assert overlay.progress_bar.isHidden()
    assert overlay.volume_button.isHidden()
    assert overlay.retry_button.isHidden()

    # the top bar stays, to close the cell
    assert not overlay.exit_button.isHidden()

    stop = overlay.stop_button
    assert stop.x() < 40
    assert stop.y() > overlay.height() * 0.6


def test_error_overlay_offers_what_the_cell_can_do():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()

    overlay.set_mode(OverlayMode.ERROR)

    assert not overlay.retry_button.isHidden()
    assert overlay.details_button.isHidden()
    assert overlay.next_button.isHidden()
    assert overlay.stop_button.isHidden()

    overlay.set_error_actions(has_details=True, can_go_next=True)

    assert not overlay.details_button.isHidden()
    assert not overlay.next_button.isHidden()

    # Next on the right, the rest on the left
    assert overlay.next_button.x() > overlay.width() / 2
    assert overlay.retry_button.x() < overlay.width() / 2


def test_told_what_it_already_shows_it_lays_nothing_out_again(mocker):
    """Told on every move of the mouse over the cell, and the time several
    times a second."""

    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.set_mode(OverlayMode.ERROR)
    overlay.set_error_actions(has_details=True, can_go_next=False)
    overlay.set_position(1000, 10_000)

    laid_out = mocker.spy(overlay, "_sync_bottom_bar")

    overlay.set_mode(OverlayMode.ERROR)
    overlay.set_error_actions(has_details=True, can_go_next=False)
    overlay.set_position(2000, 10_000)

    assert laid_out.call_count == 0

    overlay.set_position(0, 0)

    assert laid_out.call_count == 1


@pytest.mark.parametrize("size", [(200, 120), (640, 360), (1920, 1080)])
def test_chrome_overlay_stays_put_clear_of_the_frame_and_drops_its_border(size):
    overlay = OverlayBlock()
    overlay.resize(*size)
    overlay.show()
    overlay.set_is_active(True)
    QApplication.processEvents()

    assert not overlay.border_widget.isHidden()
    over_video = overlay.exit_button.geometry()

    overlay.set_is_on_chrome(True)
    QApplication.processEvents()

    assert overlay.border_widget.isHidden()

    # where it is over a video, with room to spare inside the frame's line
    assert overlay.exit_button.geometry() == over_video

    rect, stroke, _ = dashed_frame(overlay)
    frame_inner = rect.top() + stroke / 2
    assert over_video.top() - frame_inner >= 4
    assert (rect.right() - stroke / 2) - (over_video.right() + 1) >= 4

    overlay.set_is_on_chrome(False)
    QApplication.processEvents()

    assert not overlay.border_widget.isHidden()
    assert overlay.exit_button.geometry() == over_video


def test_play_pause_button_tracks_paused_state():
    overlay = OverlayBlock()

    overlay.set_is_paused(False)

    assert overlay.play_pause_button.is_off is True

    overlay.set_is_paused(True)

    assert overlay.play_pause_button.is_off is False


def test_cmd_active_shows_overlay_when_stopped_uninitialized(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_playable = True
    manager = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    manager._ctx.active_block = block

    manager.cmd_active("show_overlay")

    block.show_overlay.assert_called_once()


def _active_manager(block):
    manager = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    manager._ctx.active_block = block
    return manager


def test_cmd_active_set_end_action_when_stopped(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_playable = True
    manager = _active_manager(block)

    manager.cmd_active("set_end_action", VideoEndAction.STOP)

    block.set_end_action.assert_called_once_with(VideoEndAction.STOP)


def test_cmd_active_reload_while_loading(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_playable = False
    manager = _active_manager(block)

    manager.cmd_active("reload")

    block.reload.assert_called_once()


def test_cmd_active_ignores_play_pause_while_loading(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_playable = False
    manager = _active_manager(block)

    manager.cmd_active("play_pause")

    block.play_pause.assert_not_called()


def test_cmd_active_next_video_when_stopped(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_playable = True
    manager = _active_manager(block)

    manager.cmd_active("navigation.next")

    block.navigation.next.assert_called_once()


def test_is_active_local_file_when_stopped(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_stopped = True
    block.is_playable = True
    block.video_params.uri = Path("/tmp/a.mp4")
    manager = _active_manager(block)

    assert manager.is_active_local_file() is True


def test_is_active_local_file_false_while_loading(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_stopped = False
    block.is_playable = False
    block.video_params.uri = Path("/tmp/a.mp4")
    manager = _active_manager(block)

    assert manager.is_active_local_file() is False


def test_is_active_seekable_false_when_stopped(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_stopped = True
    block.is_live = False
    manager = _active_manager(block)

    assert manager.is_active_seekable() is False


def test_any_local_file_includes_stopped(mocker):
    stopped = mocker.Mock(
        is_local_file=True,
        is_video_initialized=False,
        is_stopped=True,
        is_playable=True,
        is_live=False,
    )
    manager = mocker.Mock()
    manager._ctx.video_blocks = [stopped]

    assert VideoBlocksManager.is_any_videos_local_file(manager) is True
    assert VideoBlocksManager.is_any_videos_playable_not_live(manager) is True


def test_stop_in_the_menu_for_every_cell_not_stopped_yet(mocker):
    """Loading, reconnecting or failed as well as playing: it was there only
    once the video played."""

    loading = mocker.Mock(is_video_initialized=False, is_stopped=False)
    stopped = mocker.Mock(is_video_initialized=False, is_stopped=True)
    empty = mocker.Mock(is_stopped=False, video_params=None)

    assert VideoBlock.is_stoppable.fget(loading) is True
    assert VideoBlock.is_stoppable.fget(stopped) is False
    assert VideoBlock.is_stoppable.fget(empty) is False

    for block in (loading, stopped):
        block.is_stoppable = VideoBlock.is_stoppable.fget(block)

    assert ACTIONS["Stop"]["show_if"] == "is_active_stoppable"
    assert _active_manager(loading).is_active_stoppable() is True
    assert _active_manager(stopped).is_active_stoppable() is False

    assert ACTIONS["Stop [ALL]"]["show_if"] == "is_any_videos_stoppable"
    manager = mocker.Mock()
    manager._ctx.video_blocks = [stopped]
    assert VideoBlocksManager.is_any_videos_stoppable(manager) is False
    manager._ctx.video_blocks = [stopped, loading]
    assert VideoBlocksManager.is_any_videos_stoppable(manager) is True


def test_cmd_active_stops_while_loading(mocker):
    block = mocker.Mock()
    block.is_video_initialized = False
    block.is_playable = False
    manager = _active_manager(block)

    manager.cmd_active("stop_playback")

    block.stop_playback.assert_called_once()


def test_any_local_file_excludes_loading(mocker):
    loading = mocker.Mock(
        is_local_file=True,
        is_video_initialized=False,
        is_stopped=False,
        is_playable=False,
        is_live=False,
    )
    manager = mocker.Mock()
    manager._ctx.video_blocks = [loading]

    assert VideoBlocksManager.is_any_videos_local_file(manager) is False
    assert VideoBlocksManager.is_any_videos_playable_not_live(manager) is False


def test_show_overlay_while_loading(mocker):
    """To close the cell or stop it, or open its list, while it loads."""

    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = True
    block._ctx.is_overlay_hide_on_timeout = False
    block.is_loading = True
    block._is_error = False
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.status.sync_overlay_mode.assert_called_once()
    block.overlay.show.assert_called_once()


def test_show_overlay_on_error(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = True
    block._ctx.is_overlay_hide_on_timeout = False
    block.is_loading = False
    block._is_error = True
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.status.sync_overlay_mode.assert_called_once()
    block.overlay.show.assert_called_once()


@pytest.mark.parametrize(
    ("is_error", "is_stopped", "is_initialized", "is_kept", "is_status", "mode"),
    [
        (True, False, False, False, True, OverlayMode.ERROR),
        (False, True, False, False, False, OverlayMode.STOPPED),
        (False, False, False, False, True, OverlayMode.LOADING),
        (False, False, True, True, True, OverlayMode.LOADING),
        (False, False, True, False, False, OverlayMode.VIDEO),
        # a reload: the status up, the old player not let go yet
        (False, False, True, False, True, OverlayMode.LOADING),
    ],
)
def test_overlay_mode_follows_the_cell(
    mocker, is_error, is_stopped, is_initialized, is_kept, is_status, mode
):
    block = mocker.Mock()
    block.is_error = is_error
    block.is_stopped = is_stopped
    block.is_video_initialized = is_initialized
    block.is_loading = not is_initialized and not is_stopped and not is_error
    block.video_status.isHidden.return_value = not is_status
    status = StatusControl(block)
    status.is_kept_for_picture = is_kept

    assert status._overlay_mode() is mode


def test_the_overlay_turns_along_with_the_status(mocker):
    """Not once the event loop comes round, which a reload holds up while
    the old player is let go."""

    block = mocker.Mock()
    order = []

    status = StatusControl(block)
    status.sync_overlay_mode = lambda: order.append("mode")
    block.overlay.lay_out_now.side_effect = lambda: order.append("laid out")
    block.repaint.side_effect = lambda: order.append("cell")
    block.overlay.isWindow.return_value = True
    block.overlay.isVisible.return_value = True
    block.overlay.repaint.side_effect = lambda: order.append("overlay")

    status.show("processing")

    assert order == ["mode", "laid out", "cell", "overlay"]


def test_the_overlay_laid_out_at_once():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_position(1000, 10_000)
    overlay.set_volume_button_visible(True)
    QApplication.processEvents()

    # Next goes to the right end as the volume button is hidden after it is
    # shown: in place before anything else is done
    overlay.set_error_actions(has_details=True, can_go_next=True)
    overlay.set_mode(OverlayMode.ERROR)
    overlay.lay_out_now()

    laid_out_at = overlay.next_button.geometry()
    QApplication.processEvents()

    assert overlay.next_button.geometry() == laid_out_at

    overlay.close()


def test_overlay_on_chrome_but_over_a_video(mocker):
    block = mocker.Mock()
    status = StatusControl(block)

    for mode in OverlayMode:
        status._overlay_mode = Mock(return_value=mode)

        status.sync_overlay_mode()

        block.overlay.set_mode.assert_called_with(mode)
        block.overlay.set_is_on_chrome.assert_called_with(mode is not OverlayMode.VIDEO)


@pytest.mark.parametrize(
    ("is_drag_ui", "is_disable_overlay"), [(False, True), (True, False)]
)
def test_overlay_mode_kept_while_it_stays_hidden(
    mocker, is_drag_ui, is_disable_overlay
):
    """A playlist opened with the overlay off: its drop disc let the
    picture through once the video played, not solid as while it loaded."""

    block = mocker.Mock()
    block._ctx.is_drag_ui = is_drag_ui
    block._ctx.is_disable_overlay = is_disable_overlay
    block.is_overlay_fits = True
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.status.sync_overlay_mode.assert_called_once()
    block.overlay.show.assert_not_called()


def test_show_overlay_skipped_when_cell_hidden(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = True
    block.is_loading = False
    block._is_error = False
    block.status.is_kept_for_picture = False
    block.isVisible.return_value = False

    VideoBlock.show_overlay(block)

    block.overlay.show.assert_not_called()


def test_show_overlay_skipped_when_cell_too_small(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = False
    block.is_loading = False
    block._is_error = False
    block.status.is_kept_for_picture = False
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.overlay.show.assert_not_called()


def test_size_policy_hides_overlay_when_cell_too_small(mocker):
    block = mocker.Mock()
    block.is_overlay_fits = False

    VideoBlock._apply_overlay_size_policy(block)

    block.overlay_hide_timer.stop.assert_called_once()
    block.overlay.hide.assert_called_once()
    block.show_overlay.assert_not_called()


def test_size_policy_shows_overlay_when_cell_fits(mocker):
    block = mocker.Mock()
    block.is_overlay_fits = True
    block._ctx.is_overlay_hide_on_timeout = False

    VideoBlock._apply_overlay_size_policy(block)

    block.show_overlay.assert_called_once()


def test_size_policy_keeps_overlay_hidden_on_timeout(mocker):
    block = mocker.Mock()
    block.is_overlay_fits = True
    block._ctx.is_overlay_hide_on_timeout = True

    VideoBlock._apply_overlay_size_policy(block)

    block.show_overlay.assert_not_called()
    block.overlay.hide.assert_not_called()


def test_hide_event_unmaps_overlay_even_when_timeout_disabled(mocker):
    block = mocker.Mock()
    block._ctx.is_overlay_hide_on_timeout = False

    VideoBlock.hideEvent(block, mocker.Mock())

    block.overlay_hide_timer.stop.assert_called_once()
    block.overlay.hide.assert_called_once()


def test_start_load_keeps_overlay(mocker):
    """Up while the next file loads, for its Stop."""

    block = mocker.Mock()
    block.video_params = mocker.Mock(
        is_http_url=False, uri="file.mp4", read_as_list=None
    )
    block.size_tuple = (100, 100)
    block._ctx.lists.is_waiting.return_value = False
    block.navigation.is_list_file_gone = False
    mocker.patch("gridplayer.widgets.video_block.MediaInput")

    VideoBlock._start_load(block)

    block.overlay.hide.assert_not_called()
    block._ensure_video_driver.assert_called_once()


def test_mouse_move_shows_overlay_on_stopped_cell(mocker):
    block = mocker.Mock()
    event = mocker.Mock()

    VideoBlock.mouseMoveEvent(block, event)

    block.show_overlay.assert_called_once()
    event.ignore.assert_called_once()


def test_stopped_cell_paints_solid_outline_and_idle_disc(mocker):
    block = mocker.Mock()
    block.is_stopped = True
    block.is_active_shown = False
    block._drop_indicator = DropIndicator.NONE
    solid = mocker.patch("gridplayer.widgets.video_block.paint_solid_outline")
    disc = mocker.patch("gridplayer.widgets.video_block.paint_idle_disc")

    VideoBlock._paint_stopped_chrome(block)

    solid.assert_called_once_with(block, is_active=False)
    disc.assert_called_once_with(block)


def test_stopped_cell_keeps_idle_disc_during_drag_when_not_target(mocker):
    block = mocker.Mock()
    block.is_stopped = True
    block.is_active_shown = False
    block._drop_indicator = DropIndicator.NONE
    solid = mocker.patch("gridplayer.widgets.video_block.paint_solid_outline")
    disc = mocker.patch("gridplayer.widgets.video_block.paint_idle_disc")

    VideoBlock._paint_stopped_chrome(block)

    solid.assert_called_once_with(block, is_active=False)
    disc.assert_called_once_with(block)


def test_stopped_cell_hides_idle_disc_on_drop_target(mocker):
    block = mocker.Mock()
    block.is_stopped = True
    block.is_active_shown = True
    block._drop_indicator = DropIndicator.DOT
    solid = mocker.patch("gridplayer.widgets.video_block.paint_solid_outline")
    disc = mocker.patch("gridplayer.widgets.video_block.paint_idle_disc")

    VideoBlock._paint_stopped_chrome(block)

    solid.assert_called_once_with(block, is_active=True)
    disc.assert_not_called()


def test_set_drop_indicator_repaints_stopped_cell(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = True
    block.is_stopped = True

    VideoBlock.set_drop_indicator(block, DropIndicator.DOT)

    assert block._drop_indicator is DropIndicator.DOT
    block.update.assert_called()
    block.overlay.show.assert_called()


def test_set_drop_indicator_does_not_repaint_playing_cell(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = True
    block.is_stopped = False

    VideoBlock.set_drop_indicator(block, DropIndicator.DOT)

    block.update.assert_not_called()
    block.overlay.show.assert_called()


def test_drop_indicator_default_circle_matches_opaque_fill():
    badge = OverlayDropIndicator()

    assert badge.circle_color.getRgb()[:3] == (0, 0, 0)


def _badge_pixels(badge, size=120) -> QImage:
    badge.resize(size, size)
    badge.set_indicator(DropIndicator.ARROW_RIGHT)

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    badge.render(image, QPoint(0, 0), QRegion(), QWidget.DrawChildren)

    return image


def test_drop_indicator_over_a_video_lets_it_through_evenly():
    badge = OverlayDropIndicator()
    badge.set_overlay_opacity(0.5)

    image = _badge_pixels(badge)
    middle = image.height() // 2
    covered = [
        color
        for color in (image.pixelColor(x, middle) for x in range(image.width()))
        if color.alpha()
    ]
    inside = [color for color in covered if color.alpha() >= 127]

    # disc and glyph alike, the glyph's strokes where they cross too: no
    # part of it covers the picture more than the rest
    assert max(color.alpha() for color in covered) <= 128
    assert {color.lightness() > 128 for color in inside} == {True, False}

    # the opaque overlay, and an empty cell's own, are solid
    badge.set_overlay_opacity(1.0)

    assert badge.opacity == 1.0
    assert _badge_pixels(badge).pixelColor(middle, middle).alpha() == 255


def test_drop_indicator_on_chrome_is_the_cells_own_disc():
    badge = OverlayDropIndicator()
    badge.set_overlay_opacity(0.5)
    badge.set_chrome_colors(QColor("#a0a0a0"), QColor("#eeeeee"))

    badge.set_on_chrome(True)

    assert badge.circle_color == QColor("#a0a0a0")
    assert badge.glyph_color == QColor("#eeeeee")
    assert badge.opacity == 1.0

    badge.set_on_chrome(False)

    assert badge.circle_color.getRgb()[:3] == (0, 0, 0)


@pytest.mark.parametrize(
    ("indicator", "is_shown"),
    [(DropIndicator.DOT, False), (DropIndicator.NONE, True)],
)
def test_drop_indicator_hides_what_the_cell_says(mocker, indicator, is_shown):
    block = mocker.Mock()
    block._ctx.is_drag_ui = True

    VideoBlock.set_drop_indicator(block, indicator)

    block._sync_drop_chrome.assert_called_once_with(indicator)

    cell = QWidget()
    block = mocker.Mock()
    block.palette = cell.palette
    block.foregroundRole = cell.foregroundRole
    block.backgroundRole = cell.backgroundRole

    VideoBlock._sync_drop_chrome(block, indicator)

    block.video_status.set_is_content_shown.assert_called_once_with(is_shown)
    block.overlay.drop_indicator.set_chrome_colors.assert_called_once()


def test_drop_indicator_glyph_change_does_not_reset_mask():
    parent = QWidget()
    parent.is_opaque = True
    parent.resize(200, 200)
    parent.show()
    badge = OverlayDropIndicator(parent=parent)
    badge.resize(200, 200)
    badge.set_indicator(DropIndicator.DOT)
    mask = QRegion(badge.mask())

    badge.set_indicator(DropIndicator.ARROW_LEFT)

    assert not badge.isHidden()
    assert badge.mask() == mask


def test_opaque_active_ring_shows_on_a_picture_of_its_own_colour():
    """Cut out of a window, it has no shadow to give: white on a white
    picture, it was not there at all. Its inside edge is drawn in the grey
    of the shadow instead."""

    parent = QWidget()
    parent.is_opaque = True
    ring = OverlayBorder(parent=parent)
    ring.color = "#ffffff"
    ring.resize(100, 80)

    image = QImage(100, 80, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    ring.render(image, QPoint(0, 0), QRegion(), QWidget.DrawChildren)

    width = ring.border_width
    row = [image.pixelColor(x, 40) for x in range(width + 1)]

    assert {color.name() for color in row[: width - 1]} == {"#ffffff"}
    assert row[width - 1].name() == ring.color_contrast_mid.name() == "#9b9b9b"
    assert row[width].alpha() == 0


def test_opaque_mask_not_reapplied_when_unchanged(mocker):
    parent = QWidget()
    overlay = OverlayBlockFloating(parent)
    overlay.is_opaque = True
    overlay.refresh_opaque_mask()
    set_mask = mocker.spy(overlay, "setMask")

    overlay.refresh_opaque_mask()

    set_mask.assert_not_called()


def test_clear_drop_indicator_hides_opaque_overlay_before_mask_change(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = True
    block.overlay.is_opaque = True
    order = []
    block.overlay.hide.side_effect = lambda: order.append("hide")
    block.overlay.set_drop_indicator.side_effect = lambda *_a, **_k: order.append("set")

    VideoBlock.set_drop_indicator(block, DropIndicator.NONE)

    assert order == ["hide", "set"]
    block.overlay.show.assert_not_called()


def test_sync_cell_background_only_fills_when_stopped(mocker):
    block = mocker.Mock()
    block.is_stopped = True
    VideoBlock._sync_cell_background(block)
    block.setAttribute.assert_called_with(Qt.WA_StyledBackground, True)
    block.setAutoFillBackground.assert_called_with(True)

    block.reset_mock()
    block.is_stopped = False
    VideoBlock._sync_cell_background(block)
    block.setAttribute.assert_called_with(Qt.WA_StyledBackground, False)
    block.setAutoFillBackground.assert_called_with(False)


def test_set_drag_ui_hides_opaque_overlay_before_chrome_change(mocker):
    block = mocker.Mock()
    block._drop_indicator = DropIndicator.NONE
    block.overlay.is_opaque = True
    order = []
    block.overlay.hide.side_effect = lambda: order.append("hide")
    block.overlay.set_is_chrome_visible.side_effect = lambda *_a, **_k: order.append(
        "chrome"
    )

    VideoBlock.set_drag_ui(block, True)

    assert order == ["hide", "chrome"]
