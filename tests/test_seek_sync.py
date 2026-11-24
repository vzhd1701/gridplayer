"""Seek sync: a seek of one cell sends the others there, and only the others
(#164). The one sought is already on its way: seeking it again doubled what a
quick drag of its bar asked of it, and VLC came out of it too late to play on
together with the rest."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gridplayer.params.static import SeekSyncMode
from gridplayer.player.managers.video_blocks import VideoBlocksManager


@pytest.fixture
def cells():
    leader = MagicMock()
    others = [MagicMock(), MagicMock()]
    manager = SimpleNamespace(
        _ctx=SimpleNamespace(video_blocks=[others[0], leader, others[1]])
    )

    return manager, leader, others


def test_by_timecode_the_others_go_there(cells):
    manager, leader, others = cells
    manager._ctx.seek_sync_mode = SeekSyncMode.TIMECODE

    VideoBlocksManager.seek_sync_timecode(manager, leader, 5200)

    for vb in others:
        vb.seek.assert_called_once_with(5200)
    assert not leader.method_calls


def test_by_percent_the_others_go_there(cells):
    manager, leader, others = cells
    manager._ctx.seek_sync_mode = SeekSyncMode.PERCENT

    VideoBlocksManager.seek_sync_percent(manager, leader, 0.25)

    for vb in others:
        vb.seek_percent.assert_called_once_with(0.25)
    assert not leader.method_calls


@pytest.mark.parametrize(
    ("mode", "sync", "arg"),
    [
        (SeekSyncMode.DISABLED, "seek_sync_timecode", 5200),
        (SeekSyncMode.DISABLED, "seek_sync_percent", 0.25),
        (SeekSyncMode.PERCENT, "seek_sync_timecode", 5200),
        (SeekSyncMode.TIMECODE, "seek_sync_percent", 0.25),
    ],
)
def test_none_go_where_seeks_are_not_synced_that_way(cells, mode, sync, arg):
    manager, leader, others = cells
    manager._ctx.seek_sync_mode = mode

    getattr(VideoBlocksManager, sync)(manager, leader, arg)

    for vb in [leader, *others]:
        assert not vb.method_calls
