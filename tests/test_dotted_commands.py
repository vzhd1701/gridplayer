"""A command may name a method of a part of the video block, "part.method",
as well as one of the block itself."""

from types import SimpleNamespace

from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.widgets.video_block import VideoBlock


def _active_manager(block):
    manager = ActiveBlockManager(context=SimpleNamespace(active_block=None))
    manager._ctx.active_block = block
    return manager


def _playing_block(mocker):
    block = mocker.Mock()
    block.is_video_initialized = True
    block.is_playable = True
    block.is_live = False
    block.position = 0.5
    block.video_driver.length = 10_000
    block.video_params.rate = 1.5
    return block


def test_cmd_active_reaches_a_part_of_the_block(mocker):
    block = _playing_block(mocker)
    block.bookmarker.seek.return_value = "sought"

    result = _active_manager(block).cmd_active("bookmarker.seek", 3)

    block.bookmarker.seek.assert_called_once_with(3)
    assert result == "sought"


def test_cmd_active_still_takes_a_plain_name(mocker):
    block = _playing_block(mocker)

    _active_manager(block).cmd_active("reload")

    block.reload.assert_called_once_with()


def test_cmd_active_drops_a_dotted_command_while_loading(mocker):
    block = _playing_block(mocker)
    block.is_playable = False

    _active_manager(block).cmd_active("bookmarker.next")

    block.bookmarker.next.assert_not_called()


def test_runtime_param_reaches_a_part_of_the_block(mocker):
    block = _playing_block(mocker)
    block.bookmarker.count = 2
    manager = _active_manager(block)

    assert manager.is_active_runtime_param_set_to("bookmarker.count", 2)
    assert not manager.is_active_runtime_param_set_to("bookmarker.count", 3)


def test_manual_seek_reaches_a_part_and_syncs_the_others(mocker):
    block = _playing_block(mocker)

    VideoBlock.manual_seek(block, "bookmarker.seek", 3)

    block.bookmarker.seek.assert_called_once_with(3)
    block.sync_percent.emit.assert_called_once_with(0.5)
    block.sync_time.emit.assert_called_once_with(5000)


def test_manual_seek_of_a_part_that_went_nowhere_syncs_nothing(mocker):
    block = _playing_block(mocker)
    block.bookmarker.seek.return_value = False

    VideoBlock.manual_seek(block, "bookmarker.seek", 3)

    block.sync_percent.emit.assert_not_called()
    block.sync_time.emit.assert_not_called()


def test_manual_view_reaches_a_part_and_gives_back_its_result(mocker):
    block = _playing_block(mocker)
    block.view.pan_by.return_value = (1.0, 2.0)
    block.synced_view.return_value = "synced"

    result = VideoBlock.manual_view(block, "view.pan_by", 3, 4)

    block.view.pan_by.assert_called_once_with(3, 4)
    block.sync_view.emit.assert_called_once_with("synced")
    assert result == (1.0, 2.0)


def test_manual_rate_reaches_a_part_and_syncs_the_others(mocker):
    block = _playing_block(mocker)

    VideoBlock.manual_rate(block, "rate.increase")

    block.rate.increase.assert_called_once_with()
    block.sync_rate.emit.assert_called_once_with(1.5)
