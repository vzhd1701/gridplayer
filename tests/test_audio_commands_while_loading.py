"""Choosing audio while the video that choice reloaded is still loading."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gridplayer.player.managers.active_block import ActiveBlockManager

# picking a language reloads the stream, so the next choice lands while the
# video is not playable; dropping it there is what made "Disable Audio" do
# nothing after a switch
AUDIO_COMMANDS = (
    "set_audio_track",
    "set_audio_language",
    "apply_audio_preference",
    "audio_languages_dialog",
    "get_audio_languages",
)


class _Manager(ActiveBlockManager):
    def __init__(self, block):
        self._log = logging.getLogger("test-manager")
        self._ctx = SimpleNamespace(active_block=block)

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None


def _manager(is_playable):
    block = Mock()
    block.is_playable = is_playable

    return _Manager(block), block


@pytest.mark.parametrize("command", AUDIO_COMMANDS)
def test_audio_choices_survive_a_reload(command):
    manager, block = _manager(is_playable=False)

    manager.cmd_active(command, -1)

    getattr(block, command).assert_called_once_with(-1)


@pytest.mark.parametrize("command", AUDIO_COMMANDS)
def test_audio_choices_still_work_on_a_playing_video(command):
    manager, block = _manager(is_playable=True)

    manager.cmd_active(command, -1)

    getattr(block, command).assert_called_once_with(-1)


def test_a_command_with_no_business_mid_load_is_still_dropped():
    manager, block = _manager(is_playable=False)

    manager.cmd_active("set_audio_channel_mode", "stereo")

    block.set_audio_channel_mode.assert_not_called()


def test_nothing_is_called_without_an_active_block():
    manager = _Manager(None)

    assert manager.cmd_active("set_audio_track", -1) is None
