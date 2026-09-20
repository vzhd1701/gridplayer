"""Moving a video's sound against its picture, and hearing it move."""

from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.audio_delay import SetAudioDelayDialog
from gridplayer.models.video import Video
from gridplayer.params.static import (
    AUDIO_DELAY_STEP_MS,
    MAX_AUDIO_DELAY_MS,
    MIN_AUDIO_DELAY_MS,
)
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock, audio_delay_txt


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _block(delay_ms=0, has_audio=True):
    block = Mock()
    block.is_video_initialized = True
    block.audio_tracks = {0: Mock()} if has_audio else {}
    block.video_params = Video(uri="http://example.com/a.mp4")
    block.video_params.audio_delay_ms = delay_ms

    # the steps and the reset all go through the setter, which a mock would
    # otherwise answer for without moving anything
    block.set_audio_delay = partial(VideoBlock.set_audio_delay, block)

    return block


class TestHowFarTheSoundIsMoved:
    def test_the_video_is_told_and_the_choice_is_kept(self):
        block = _block()

        VideoBlock.set_audio_delay(block, 150)

        assert block.video_params.audio_delay_ms == 150
        block.video_driver.set_audio_delay.assert_called_once_with(150)

    @pytest.mark.parametrize(
        ("asked", "landed"),
        [
            (MAX_AUDIO_DELAY_MS + 1000, MAX_AUDIO_DELAY_MS),
            (MIN_AUDIO_DELAY_MS - 1000, MIN_AUDIO_DELAY_MS),
        ],
    )
    def test_it_goes_no_further_than_the_model_allows(self, asked, landed):
        """Past the range the video itself would refuse to be saved."""

        block = _block()

        VideoBlock.set_audio_delay(block, asked)

        assert block.video_params.audio_delay_ms == landed

    def test_later_and_earlier_move_it_by_one_step(self):
        block = _block(delay_ms=100)

        VideoBlock.audio_delay_increase(block)
        assert block.video_params.audio_delay_ms == 100 + AUDIO_DELAY_STEP_MS

        VideoBlock.audio_delay_decrease(block)
        VideoBlock.audio_delay_decrease(block)
        assert block.video_params.audio_delay_ms == 100 - AUDIO_DELAY_STEP_MS

    def test_reset_puts_it_back_level(self):
        block = _block(delay_ms=-350)

        VideoBlock.audio_delay_reset(block)

        assert block.video_params.audio_delay_ms == 0

    def test_a_silent_video_is_left_alone(self):
        """Nothing to move, and nothing for libVLC to move it against."""

        block = _block(has_audio=False)

        VideoBlock.set_audio_delay(block, 150)

        assert block.video_params.audio_delay_ms == 0
        block.video_driver.set_audio_delay.assert_not_called()


class TestSayingSoOverTheVideo:
    """A shortcut changes nothing that can be seen, so it has to be said."""

    def test_the_new_delay_is_shown(self):
        block = _block()

        VideoBlock.set_audio_delay(block, 150)

        block.info_change.emit.assert_called_once_with("Audio delay: +150 ms")

    def test_a_silent_change_says_nothing(self):
        """Putting back what was already chosen is not news; see load."""

        block = _block()

        VideoBlock.set_audio_delay(block, 150, is_silent=True)

        block.info_change.emit.assert_not_called()

    def test_the_menu_reads_the_same_as_the_video(self):
        block = _block(delay_ms=-50)

        assert VideoBlock.get_audio_delay(block) == "-50 ms"

    @pytest.mark.parametrize(
        ("delay_ms", "txt"),
        [(0, "0 ms"), (50, "+50 ms"), (-50, "-50 ms"), (1500, "+1500 ms")],
    )
    def test_which_way_it_went_is_always_on_the_face_of_it(self, delay_ms, txt):
        assert audio_delay_txt(delay_ms) == txt


class FakeBlock:
    """Just enough of a video block for the dialog to talk to."""

    def __init__(self, delay_ms=0):
        self.video_params = SimpleNamespace(audio_delay_ms=delay_ms)
        self.calls = []

    def set_audio_delay(self, delay_ms, is_silent=False):
        self.video_params.audio_delay_ms = delay_ms
        self.calls.append((delay_ms, is_silent))


class TestTheDialogIsHeardAsItIsUsed:
    """Whether a delay is right is heard, not worked out on paper."""

    def test_every_change_reaches_the_video_at_once(self):
        block = FakeBlock(delay_ms=100)
        dialog = SetAudioDelayDialog.for_video_block(block)

        dialog.spinbox.setValue(250)

        assert block.calls == [(250, True)]
        assert block.video_params.audio_delay_ms == 250

    def test_it_opens_on_the_delay_the_video_already_has(self):
        dialog = SetAudioDelayDialog.for_video_block(FakeBlock(delay_ms=-75))

        assert dialog.spinbox.value() == -75

    def test_cancel_puts_back_the_delay_it_opened_on(self):
        block = FakeBlock(delay_ms=100)
        dialog = SetAudioDelayDialog.for_video_block(block)

        dialog.spinbox.setValue(250)
        dialog.reject()

        assert block.video_params.audio_delay_ms == 100
        assert block.calls[-1] == (100, True), "quietly, it was never announced"

    def test_cancelling_a_dialog_nothing_was_done_in_touches_nothing(self):
        block = FakeBlock(delay_ms=100)

        SetAudioDelayDialog.for_video_block(block).reject()

        assert block.calls == []

    def test_ok_says_out_loud_what_was_settled_on(self):
        block = FakeBlock(delay_ms=0)
        dialog = SetAudioDelayDialog.for_video_block(block)

        dialog.spinbox.setValue(250)
        dialog.accept()

        assert block.calls[-1] == (250, False)

    def test_reset_is_heard_like_any_other_change(self):
        block = FakeBlock(delay_ms=250)
        dialog = SetAudioDelayDialog.for_video_block(block)

        dialog._on_reset()

        assert block.video_params.audio_delay_ms == 0

    def test_a_dialog_with_no_video_behind_it_hands_back_the_number(self, monkeypatch):
        monkeypatch.setattr(SetAudioDelayDialog, "exec_", lambda self: 1)

        assert SetAudioDelayDialog.get_delay_ms(delay_ms=250) == 250

    def test_cancelling_that_one_hands_back_nothing(self, monkeypatch):
        """None, since zero is a delay somebody may well have meant."""

        monkeypatch.setattr(SetAudioDelayDialog, "exec_", lambda self: 0)

        assert SetAudioDelayDialog.get_delay_ms(delay_ms=250) is None
