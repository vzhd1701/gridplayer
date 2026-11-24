from itertools import pairwise

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from gridplayer.models.video import Video
from gridplayer.mpv_player.deinterlace import makes_field_pictures
from gridplayer.params.static import SeekAim, VideoInitialState
from gridplayer.settings import Settings
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_vlc_base import DEFAULT_FPS, VideoFrameVLC


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(
        str(tmp_path / "test.ini"), QSettings.Format.IniFormat
    )


def _stepping_block(mocker, fps, time=0, steps_own_frames=False):
    block = mocker.Mock()
    block.video_params = Video(
        uri="http://example.com/a.mp4", playback_state=VideoInitialState.PAUSED
    )
    block.is_video_initialized = True
    block.is_live = False
    block.video_tracks = [mocker.Mock()]
    block.time = time
    block.loop_start = 0
    block.loop_end = 600_000
    block.video_driver.get_ms_per_frame.return_value = 1000 / fps
    block.video_driver.steps_own_frames.return_value = steps_own_frames

    def _seek_shift_ms(shift_ms, aim=SeekAim.EXACT):
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


def _aims(block):
    return [call.args[1] for call in block.seek_shift_ms.call_args_list]


def test_by_time_where_the_player_has_no_frames_of_its_own(mocker):
    """VLC: the time is all it goes by, and the others follow it at once."""
    block = _stepping_block(mocker, fps=25, time=5000)

    assert VideoBlock.step_frame(block, 1) is None
    assert VideoBlock.step_frame(block, -1) is None

    assert _aims(block) == [SeekAim.EXACT, SeekAim.EXACT]


def test_by_the_players_own_frames_where_it_has_them(mocker):
    block = _stepping_block(mocker, fps=25, time=5000, steps_own_frames=True)

    assert VideoBlock.step_frame(block, 1) is True
    assert VideoBlock.step_frame(block, -1) is True

    assert _aims(block) == [SeekAim.NEXT_FRAME, SeekAim.PREVIOUS_FRAME]


@pytest.mark.parametrize(
    ("time", "frames", "loop"),
    [
        # back from the first frame goes round to the end
        (20, -1, (0, 600_000)),
        # on from the last of a loop goes round to its start
        (9_990, 1, (0, 10_000)),
        (5_000, 1, (5_000, 5_030)),
    ],
)
def test_a_step_out_of_the_loop_goes_by_time(mocker, time, frames, loop):
    block = _stepping_block(mocker, fps=25, time=time, steps_own_frames=True)
    block.loop_start, block.loop_end = loop

    assert VideoBlock.step_frame(block, frames) is None

    assert _aims(block) == [SeekAim.EXACT]


@pytest.mark.parametrize(
    ("options", "is_own_active", "is_fields"),
    [
        ({"deinterlace": "no", "vf": ""}, None, False),
        # mpv's own, on everything or only on what's interlaced
        ({"deinterlace": "yes", "vf": ""}, None, True),
        ({"deinterlace": "auto", "vf": ""}, True, True),
        ({"deinterlace": "auto", "vf": ""}, False, False),
        # not said yet
        ({"deinterlace": "auto", "vf": ""}, None, True),
        # the modes by name
        ({"deinterlace": "no", "vf": "lavfi=[yadif=mode=send_frame]"}, None, False),
        ({"deinterlace": "no", "vf": "lavfi=[yadif=mode=send_field]"}, None, True),
        ({"deinterlace": "no", "vf": "lavfi=[bwdif=mode=send_field]"}, None, True),
        (
            {"deinterlace": "no", "vf": "lavfi=[separatefields,scale=h=ih*2]"},
            None,
            True,
        ),
        (
            {"deinterlace": "no", "vf": "lavfi=[fieldmatch,yadif,decimate]"},
            None,
            False,
        ),
    ],
)
def test_mpv_steps_a_field_where_a_picture_is_made_of_each(
    options, is_own_active, is_fields
):
    assert makes_field_pictures(options, is_own_active) is is_fields
