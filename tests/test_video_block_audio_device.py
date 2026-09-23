"""Telling one video's sound to come out somewhere else."""

from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.audio_device import AudioDevice
from gridplayer.models.video import Video
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock

URI = "http://example.com/a.mp4"

SPDIF = AudioDevice(id="{C6A16AEF}", name="Digital Audio (S/PDIF)")
HEADPHONES = AudioDevice(id="{7DA058ED}", name="Headphones")


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _block(chosen=None, is_initialized=True, devices=(SPDIF, HEADPHONES)):
    block = Mock()
    block.is_video_initialized = is_initialized
    block.video_params = Video(uri=URI, audio_device=chosen)
    block.video_driver.audio_devices = devices

    return block


class TestPickingOne:
    def test_the_video_is_told_and_the_choice_is_kept(self):
        block = _block()

        VideoBlock.set_audio_device(block, SPDIF)

        assert block.video_params.audio_device == SPDIF
        block.video_driver.set_audio_device.assert_called_once_with(SPDIF)

    def test_the_machines_own_is_a_choice_like_any_other(self):
        block = _block(chosen=SPDIF)

        VideoBlock.set_audio_device(block, None)

        assert block.video_params.audio_device is None
        block.video_driver.set_audio_device.assert_called_once_with(None)

    def test_a_video_still_loading_remembers_without_being_told(self):
        """Whatever opens it puts the choice in force when it gets there."""

        block = _block(is_initialized=False)

        VideoBlock.set_audio_device(block, SPDIF)

        assert block.video_params.audio_device == SPDIF
        block.video_driver.set_audio_device.assert_not_called()

    def test_the_choice_belongs_to_the_video_alone(self):
        """Two videos, two ways out; telling one says nothing of the other."""

        first = _block()
        second = _block()

        VideoBlock.set_audio_device(first, SPDIF)

        assert second.video_params.audio_device is None


class TestWhatItCanBeSentTo:
    def test_whatever_the_process_playing_it_can_reach(self):
        block = _block()

        assert VideoBlock.audio_devices.fget(block) == (SPDIF, HEADPHONES)

    def test_nothing_before_it_has_loaded(self):
        block = _block(is_initialized=False)

        assert VideoBlock.audio_devices.fget(block) == ()

    def test_nor_where_there_is_no_player_yet(self):
        block = _block()
        block.video_driver = None

        assert VideoBlock.audio_devices.fget(block) == ()
