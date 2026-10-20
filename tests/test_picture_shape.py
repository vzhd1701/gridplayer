from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import VideoTransform
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


def _frame(video_dimensions):
    frame = _StubFrame(vlc_options=[])
    frame.resize(640, 360)
    track = VideoTrack(
        codec="h264",
        bitrate=0,
        language=None,
        description=None,
        video_dimensions=video_dimensions,
        fps=None,
        orientation=VideoTransform.NONE,
    )
    frame.media = MagicMock(is_audio_only=False, video_tracks={0: track})
    frame.media.cur_video_track = track
    return frame


def test_the_shape_is_said_once_known_and_when_it_changes():
    frame = _frame((0, 0))
    said = []
    frame.picture_shape_changed.connect(said.append)

    frame.adjust_view()
    assert said == []

    frame.set_track_dimensions(1080, 1920)
    assert said == [pytest.approx(9 / 16)]

    frame.resize(300, 500)
    frame.adjust_view()
    assert len(said) == 1

    frame.set_aspect_ratio("4:3")
    assert said[1:] == [pytest.approx(4 / 3)]

    frame.set_crop_ratio("1:1")
    assert said[2:] == [pytest.approx(1)]
