"""Playback times that outgrow a 32-bit int.

PyQt maps a plain `int` signal argument to a 32-bit one and wraps
silently rather than raising, so a time too big for it arrives as a
different number, often a negative one. Milliseconds run out after 24.8
days, which nothing in a video file reaches -- but a live DASH manifest
counts from its availabilityStartTime, and the ones that use the epoch
hand VLC a clock three orders of magnitude past the limit on the first
frame.
"""

from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.utils.qt import MILLISECONDS
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC
from gridplayer.widgets.video_frame_vlc_hw_sp import (
    PlayerProcessSingleVLCHWSP,
    VideoDriverVLCHWSP,
)
from gridplayer.widgets.video_frame_vlc_sw_sp import (
    PlayerProcessSingleVLCSWSP,
    VideoDriverVLCSWSP,
)

# a live manifest counted from 1970, as DASH-IF's test streams are
EPOCH_CLOCK_MS = 1_789_670_361_000

# what a plain int signal would have turned that into
WRAPPED = -1_331_001_432

# every signal that carries a time or a duration, and how many it takes
CARRIERS = [
    (VLCVideoDriver, "time_changed", 1),
    (VideoBlock, "time_change", 2),
    (VideoBlock, "sync_time", 1),
    (VideoBlock, "sync_time_single", 1),
    (VideoFrameVLC, "time_changed", 1),
    (PlayerProcessSingleVLCHWSP, "time_changed", 1),
    (VideoDriverVLCHWSP, "cmd_set_time", 1),
    (PlayerProcessSingleVLCSWSP, "time_changed", 1),
    (VideoDriverVLCSWSP, "cmd_set_time", 1),
    (VideoBlocksManager, "all_seek", 1),
    (VideoBlocksManager, "all_seek_shift_ms", 1),
]


@pytest.mark.parametrize(
    ("owner", "signal_name", "arity"),
    CARRIERS,
    ids=[f"{owner.__name__}.{name}" for owner, name, _ in CARRIERS],
)
def test_a_time_too_big_for_32_bits_arrives_as_it_was_sent(owner, signal_name, arity):
    """Declared as a plain int, every one of these would wrap."""

    signal = getattr(owner, signal_name)

    class Sender(QObject):
        relay = signal

    seen = []

    sender = Sender()
    sender.relay.connect(lambda *args: seen.append(args))

    sender.relay.emit(*[EPOCH_CLOCK_MS] * arity)

    assert seen == [(EPOCH_CLOCK_MS,) * arity]


def test_the_wrap_this_guards_against_is_real():
    """Nothing here is worth doing if PyQt raised on the way instead.

    It does not: it truncates, so the failure is a plausible-looking
    number rather than an error anybody would notice.
    """

    class Sender(QObject):
        plain = pyqtSignal(int)

    seen = []

    sender = Sender()
    sender.plain.connect(seen.append)

    sender.plain.emit(EPOCH_CLOCK_MS)

    assert seen == [WRAPPED]


def test_the_type_is_the_one_qt_calls_64_bit():
    """Spelled wrong it would be ignored, and nothing else would say so."""

    assert MILLISECONDS == "qint64"


def test_a_video_block_wires_itself_up_and_carries_the_time_through():
    """A decorated slot declares its own types, and Qt refuses a mismatch.

    Widening a signal without widening the slot it feeds raises where
    the two are wired together, which is while a video block is being
    built -- so the first video opened takes the window down with it.
    Emitting into a signal on its own proves nothing about that: the
    block has to be built, the way the player builds it.
    """

    # held on to: a parent collected out from under it takes the block
    parent = QWidget()

    block = VideoBlock(video_driver=MagicMock(), context=MagicMock(), parent=parent)

    try:
        block.time_change.emit(EPOCH_CLOCK_MS, EPOCH_CLOCK_MS)

        assert block.overlay._last_position == (EPOCH_CLOCK_MS, EPOCH_CLOCK_MS)
    finally:
        block.url_resolver.cleanup()
