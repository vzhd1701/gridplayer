"""The guards on a video block's commands ask the block, whether the command
is the block's own or one of a part of it."""

from types import SimpleNamespace

import pytest

from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_seekable,
)


class _Part(VideoBlockPart):
    @only_initialized
    @only_seekable
    def command(self):
        return "done"


class _Block:
    def __init__(self, *, is_video_initialized, is_live):
        self.is_video_initialized = is_video_initialized
        self.is_live = is_live

    @only_initialized
    @only_seekable
    def command(self):
        return "done"


@pytest.mark.parametrize(
    ("is_video_initialized", "is_live", "result"),
    [
        (True, False, "done"),
        (False, False, None),
        (True, True, None),
    ],
)
def test_a_part_is_guarded_by_its_block(is_video_initialized, is_live, result):
    block = SimpleNamespace(is_video_initialized=is_video_initialized, is_live=is_live)

    assert _Part(block).command() == result


@pytest.mark.parametrize(
    ("is_video_initialized", "is_live", "result"),
    [
        (True, False, "done"),
        (False, False, None),
        (True, True, None),
    ],
)
def test_the_block_is_guarded_by_itself(is_video_initialized, is_live, result):
    block = _Block(is_video_initialized=is_video_initialized, is_live=is_live)

    assert block.command() == result


def test_a_part_asks_its_block_not_itself():
    block = SimpleNamespace(is_video_initialized=False, is_live=False)
    part = _Part(block)

    # what the part itself would say is not asked
    part.is_video_initialized = True

    assert part.command() is None
