from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.params.static import VideoEndAction
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_overlay import OverlayBlock, OverlayBlockFloating
from gridplayer.widgets.video_overlay_elements import OverlayDropIndicator


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_stopped_overlay_hides_seeker_and_keeps_play_button():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_position(1000, 10_000)

    assert not overlay.progress_bar.isHidden()

    overlay.set_is_stopped(True)

    assert overlay.progress_bar.isHidden()
    assert overlay.label_progress.isHidden()
    assert overlay.floating_progress.isHidden()
    assert not overlay.play_pause_button.isHidden()
    assert overlay.volume_button.isHidden()
    assert overlay.volume_bar.isHidden()
    assert not overlay.progress_bar_placeholder.isHidden()

    overlay.set_position(2000, 10_000)

    assert overlay.progress_bar.isHidden()

    overlay.set_is_stopped(False)

    assert not overlay.progress_bar.isHidden()
    assert not overlay.play_pause_button.isHidden()


def test_leaving_stopped_shows_timecode_without_resize():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_is_stopped(True)
    overlay.set_is_stopped(False)
    overlay.set_position(1500, 10_000)

    assert overlay.progress_bar.isEnabled()
    assert not overlay.progress_bar.isHidden()
    assert not overlay.label_progress.isHidden()
    assert "/" in overlay.label_progress.text


def test_stopped_play_button_stays_bottom_left():
    overlay = OverlayBlock()
    overlay.resize(400, 300)
    overlay.show()
    overlay.set_is_stopped(True)

    btn = overlay.play_pause_button
    assert btn.x() < 40
    assert btn.y() > overlay.height() * 0.6


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

    manager.cmd_active("next_video")

    block.next_video.assert_called_once()


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


def test_show_overlay_skipped_while_loading(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = True
    block.is_loading = True
    block._is_error = False
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.overlay.show.assert_not_called()


def test_show_overlay_skipped_on_error(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = True
    block.is_loading = False
    block._is_error = True
    block.isVisible.return_value = True

    VideoBlock.show_overlay(block)

    block.overlay.show.assert_not_called()


def test_show_overlay_skipped_when_cell_hidden(mocker):
    block = mocker.Mock()
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block.is_overlay_fits = True
    block.is_loading = False
    block._is_error = False
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


def test_start_load_hides_overlay(mocker):
    block = mocker.Mock()
    block.video_params = mocker.Mock(is_http_url=False, uri="file.mp4")
    block.size_tuple = (100, 100)
    mocker.patch("gridplayer.widgets.video_block.MediaInput")

    VideoBlock._start_load(block)

    block.overlay_hide_timer.stop.assert_called_once()
    block.overlay.hide.assert_called_once()
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
    block._drop_indicator = DropIndicator.NONE
    solid = mocker.patch("gridplayer.widgets.video_block.paint_solid_outline")
    disc = mocker.patch("gridplayer.widgets.video_block.paint_idle_disc")

    VideoBlock._paint_stopped_chrome(block)

    solid.assert_called_once_with(block)
    disc.assert_called_once_with(block)


def test_stopped_cell_keeps_idle_disc_during_drag_when_not_target(mocker):
    block = mocker.Mock()
    block.is_stopped = True
    block._drop_indicator = DropIndicator.NONE
    solid = mocker.patch("gridplayer.widgets.video_block.paint_solid_outline")
    disc = mocker.patch("gridplayer.widgets.video_block.paint_idle_disc")

    VideoBlock._paint_stopped_chrome(block)

    solid.assert_called_once_with(block)
    disc.assert_called_once_with(block)


def test_stopped_cell_hides_idle_disc_on_drop_target(mocker):
    block = mocker.Mock()
    block.is_stopped = True
    block._drop_indicator = DropIndicator.DOT
    solid = mocker.patch("gridplayer.widgets.video_block.paint_solid_outline")
    disc = mocker.patch("gridplayer.widgets.video_block.paint_idle_disc")

    VideoBlock._paint_stopped_chrome(block)

    solid.assert_called_once_with(block)
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

    assert badge._circle_color.getRgb()[:3] == (0, 0, 0)


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
