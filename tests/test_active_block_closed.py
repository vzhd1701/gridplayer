from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from gridplayer.player.managers.active_block import ActiveBlockManager


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _manager(mocker, active):
    # it says a VideoBlock, which these stand-ins aren't
    mocker.patch.object(ActiveBlockManager, "active_block_change")
    manager = ActiveBlockManager(context=SimpleNamespace())
    manager._ctx.active_block = active
    return manager


def test_a_video_closed_is_active_no_more(mocker):
    # a reload from the video's menu, a driver changed in Settings: its block
    # is to be deleted, and setting it inactive then fails
    closed = MagicMock()
    manager = _manager(mocker, closed)

    manager.forget_closed([MagicMock(), closed])

    assert manager._ctx.active_block is None
    manager.active_block_change.emit.assert_called_once_with(None)


def test_the_active_video_stays_when_others_close(mocker):
    block = MagicMock()
    manager = _manager(mocker, block)

    manager.forget_closed([MagicMock()])

    assert manager._ctx.active_block is block
    manager.active_block_change.emit.assert_not_called()
