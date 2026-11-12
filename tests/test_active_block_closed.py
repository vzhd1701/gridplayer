from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers import active_block
from gridplayer.player.managers.active_block import ActiveBlockManager


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _manager(mocker, is_modal, blocks):
    mocker.patch.object(active_block, "is_modal_open", return_value=is_modal)
    # it says a VideoBlock, which these stand-ins aren't
    mocker.patch.object(ActiveBlockManager, "active_block_change")
    manager = ActiveBlockManager(context=SimpleNamespace(video_blocks=blocks))
    manager.get_video_block_under_mouse = MagicMock(return_value=None)
    return manager


def test_a_video_closed_with_a_menu_open_is_active_no_more(mocker):
    # a reload from the video's menu, a driver changed in Settings: its block
    # is to be deleted, and setting it inactive then fails
    closed = MagicMock()
    manager = _manager(mocker, is_modal=True, blocks=[])
    manager._ctx.active_block = closed

    manager.update_active_under_mouse()

    assert manager._ctx.active_block is None


def test_a_video_closed_is_left_alone_when_another_becomes_active(mocker):
    closed, other = MagicMock(), MagicMock()
    manager = _manager(mocker, is_modal=False, blocks=[other])
    manager._ctx.active_block = closed
    manager.get_video_block_under_mouse.return_value = other

    manager.update_active_under_mouse()

    assert manager._ctx.active_block is other
    assert other.is_active is True
    assert closed.is_active is not False


def test_a_video_still_there_stays_active_with_a_menu_open(mocker):
    block = MagicMock()
    manager = _manager(mocker, is_modal=True, blocks=[block])
    manager._ctx.active_block = block

    manager.update_active_under_mouse()

    assert manager._ctx.active_block is block
