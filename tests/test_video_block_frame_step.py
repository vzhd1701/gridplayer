from itertools import pairwise

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.params.static import VideoInitialState
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_vlc_base import DEFAULT_FPS, VideoFrameVLC


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _stepping_block(mocker, fps, time=0):
    block = mocker.Mock()
    block.video_params = Video(
        uri="http://example.com/a.mp4", playback_state=VideoInitialState.PAUSED
    )
    block.is_video_initialized = True
    block.is_live = False
    block.video_tracks = [mocker.Mock()]
    block.time = time
    block.video_driver.get_ms_per_frame.return_value = 1000 / fps

    def _seek_shift_ms(shift_ms):
        block.time += shift_ms

    block.seek_shift_ms.side_effect = _seek_shift_ms

    return block


def _step_times(block, frames, presses):
    times = []
    for _ in range(presses):
        VideoBlock.step_frame(block, frames)
        times.append(block.time)

    return times


def test_first_press_pauses_instead_of_stepping(mocker):
    block = _stepping_block(mocker, fps=25)
    block.video_params.playback_state = VideoInitialState.PLAYING

    VideoBlock.step_frame(block, 1)

    block.set_pause.assert_called_once_with(True)
    block.seek_shift_ms.assert_not_called()


def test_every_press_moves_a_frame(mocker):
    """A frame that is not a whole number of ms still moves on every press."""
    block = _stepping_block(mocker, fps=23.976)

    times = _step_times(block, 1, presses=100)

    steps = [b - a for a, b in pairwise(times)]
    assert min(steps) > 0
    assert set(steps) <= {41, 42}


def test_a_press_lands_inside_a_frame_not_on_its_edge(mocker):
    """A frame's edge rounds to a whole ms on either side of itself."""
    block = _stepping_block(mocker, fps=23.976)

    times = _step_times(block, 1, presses=20)

    ms_per_frame = 1000 / 23.976
    offsets = [seek_ms % ms_per_frame for seek_ms in times]
    assert min(offsets) > ms_per_frame / 4
    assert max(offsets) < ms_per_frame * 3 / 4


def test_presses_do_not_drift_off_the_frame_grid(mocker):
    """100 presses are 100 frames, not 100 roundings of one frame."""
    block = _stepping_block(mocker, fps=23.976)

    times = _step_times(block, 1, presses=100)

    assert times[-1] == round(100.5 * 1000 / 23.976)


def test_stepping_back_undoes_stepping_forward(mocker):
    block = _stepping_block(mocker, fps=29.97, time=5000)

    VideoBlock.step_frame(block, 1)
    stepped = block.time
    VideoBlock.step_frame(block, -1)

    ms_per_frame = 1000 / 29.97
    frame_5000 = int(5000 // ms_per_frame)

    assert stepped == round((frame_5000 + 1.5) * ms_per_frame)
    assert block.time == round((frame_5000 + 0.5) * ms_per_frame)


def test_frame_duration_is_not_rounded_to_whole_ms(mocker):
    frame = mocker.Mock()
    frame.media.cur_video_track.fps = 23.976

    assert VideoFrameVLC.get_ms_per_frame(frame) == pytest.approx(41.7, abs=0.05)


def test_frame_duration_falls_back_without_a_frame_rate(mocker):
    """Some tracks come with no frame rate at all."""
    frame = mocker.Mock()
    frame.media.cur_video_track.fps = None

    assert VideoFrameVLC.get_ms_per_frame(frame) == 1000 / DEFAULT_FPS
