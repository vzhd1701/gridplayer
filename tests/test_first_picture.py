from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

import gridplayer.widgets.video_frame_vlc_base as vlc_base
from gridplayer.params.static import HWCropBorderOffset
from gridplayer.utils import darkmode
from gridplayer.utils.win32_vlc_vout import VlcPicture
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_frame_vlc_base import (
    FIRST_PICTURE_PLACE_TIMEOUT_MS,
    FIRST_PICTURE_TIMEOUT_MS,
)
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP
from gridplayer.widgets.video_frame_vlc_sw_sp import VideoFrameVLCSWSP

# where the picture goes in the cell's VLC window, and the window's size
PLACED = (0, 4, 416, 242)
WINDOW = (416, 250)

# a frame at the default frame rate, 25fps
FRAME_MS = 40


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubHWFrame(VideoFrameVLCHWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


class _StubSWFrame(VideoFrameVLCSWSP):
    def driver_setup(self, vlc_options):
        return MagicMock()


class _Clock:
    """A QElapsedTimer on a clock the test moves."""

    def __init__(self, now):
        self._now = now
        self._started = None

    def start(self):
        self._started = self._now[0]

    def invalidate(self):
        self._started = None

    def isValid(self):
        return self._started is not None

    def elapsed(self):
        return self._now[0] - self._started

    def hasExpired(self, timeout):
        return self.elapsed() > timeout


class _Vlc:
    """What VLC's windows in the surface say, as the test has them."""

    def __init__(self, monkeypatch):
        self.picture = VlcPicture(False, (0, 0, 416, 250), WINDOW, WINDOW)
        monkeypatch.setattr(vlc_base, "vlc_picture", lambda _surface: self.picture)

    def draws(self, rect=PLACED, window_size=WINDOW):
        self.picture = VlcPicture(True, rect, window_size, WINDOW)


@pytest.fixture
def frame(monkeypatch):
    monkeypatch.setattr(
        vlc_base, "Settings", lambda: MagicMock(get=lambda _: HWCropBorderOffset.PX8)
    )
    monkeypatch.setattr(vlc_base.env, "IS_WINDOWS", True)
    monkeypatch.setattr(vlc_base.env, "IS_LINUX", False)
    monkeypatch.setattr(darkmode, "is_system_dark_mode", lambda: False)

    frame = _StubHWFrame(vlc_options=[])
    frame.now = [0]
    frame._first_picture_clock = _Clock(frame.now)
    frame._picture_up_clock = _Clock(frame.now)
    frame._picture_in_place_clock = _Clock(frame.now)
    frame._vlc_picture_rect = lambda window_size: PLACED
    frame.shown = []
    frame.picture_shown.connect(lambda: frame.shown.append(frame.now[0]))

    return frame


def _load(frame):
    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))


def _at(frame, ms):
    frame.now[0] = ms
    frame._look_for_first_picture()


def test_picture_pending_until_vlc_draws_it_where_the_view_goes(frame, monkeypatch):
    """VLC's main window is black until its first picture, which comes
    after the player says the video is loaded."""
    vlc = _Vlc(monkeypatch)

    _load(frame)
    _at(frame, 100)

    assert frame.is_picture_pending

    vlc.draws()
    _at(frame, 110)

    # VLC draws the view's picture there with the next frame at the latest
    assert frame.is_picture_pending

    _at(frame, 110 + FRAME_MS + 1)

    assert not frame.is_picture_pending
    assert frame.shown == [110 + FRAME_MS + 1]


def test_picture_drawn_whole_before_the_view_is_not_taken_for_it(frame, monkeypatch):
    """VLC can draw its first picture before it takes the view up, then
    move it where the view goes, stretched there until the next one."""
    vlc = _Vlc(monkeypatch)

    _load(frame)
    vlc.draws(rect=(76, 0, 264, 250))
    _at(frame, 100)
    _at(frame, 100 + FRAME_MS + 1)

    assert frame.is_picture_pending

    vlc.draws()
    _at(frame, 200)
    _at(frame, 200 + FRAME_MS + 1)

    assert frame.shown == [200 + FRAME_MS + 1]


def test_picture_not_in_place_until_vlc_has_its_window_the_surface_size(
    frame, monkeypatch
):
    vlc = _Vlc(monkeypatch)

    _load(frame)
    vlc.draws(window_size=(400, 234))
    _at(frame, 100)
    _at(frame, 100 + FRAME_MS + 1)

    assert frame.is_picture_pending


def test_picture_never_where_worked_out_is_shown_soon_all_the_same(frame, monkeypatch):
    vlc = _Vlc(monkeypatch)

    _load(frame)
    vlc.draws(rect=(0, 0, 416, 250))
    _at(frame, 100)
    _at(frame, 100 + FIRST_PICTURE_PLACE_TIMEOUT_MS)

    assert frame.is_picture_pending

    _at(frame, 100 + FIRST_PICTURE_PLACE_TIMEOUT_MS + 1)

    assert frame.shown == [100 + FIRST_PICTURE_PLACE_TIMEOUT_MS + 1]


def test_picture_given_up_on_if_vlc_never_draws(frame, monkeypatch):
    _Vlc(monkeypatch)

    _load(frame)
    _at(frame, FIRST_PICTURE_TIMEOUT_MS)

    assert frame.is_picture_pending

    _at(frame, FIRST_PICTURE_TIMEOUT_MS + 1)

    assert frame.shown == [FIRST_PICTURE_TIMEOUT_MS + 1]


def test_nothing_to_wait_for_without_vlc_windows(frame, monkeypatch):
    """Off Windows, or VLC has none: as before, on show with the load."""
    monkeypatch.setattr(vlc_base, "vlc_picture", lambda _surface: None)

    _load(frame)

    assert not frame.is_picture_pending


def test_nothing_to_wait_for_with_audio_only(frame, monkeypatch):
    _Vlc(monkeypatch)

    frame.load_video_finish(MagicMock(is_audio_only=True))

    assert not frame.is_picture_pending


def test_vlc_windows_gone_ends_the_wait(frame, monkeypatch):
    vlc = _Vlc(monkeypatch)

    _load(frame)
    vlc.picture = None
    _at(frame, 100)

    assert frame.shown == [100]


def test_wait_ends_with_the_player(frame, monkeypatch):
    _Vlc(monkeypatch)

    _load(frame)
    frame.cleanup_start()

    assert not frame.is_picture_pending


def test_software_frame_never_waits(monkeypatch):
    """It draws the frames itself."""
    _Vlc(monkeypatch)
    frame = _StubSWFrame(vlc_options=[])

    frame.load_video_finish(MagicMock(is_audio_only=False, cur_video_track=None))

    assert not frame.is_picture_pending


def test_cell_keeps_its_status_up_until_the_picture_is(mocker):
    block = mocker.Mock()
    block.video_driver.is_picture_pending = True

    VideoBlock.load_video_finish(block)

    block.video_status.hide.assert_not_called()

    VideoBlock._picture_shown(block)

    block.video_status.hide.assert_called_once()


def test_cell_takes_its_status_off_at_once_with_nothing_to_wait_for(mocker):
    block = mocker.Mock()
    block.video_driver.is_picture_pending = False

    VideoBlock.load_video_finish(block)

    block.video_status.hide.assert_called_once()


def test_cell_status_given_something_else_to_show_stays(mocker):
    """A status set meanwhile, an error say, is not the loading one."""
    block = mocker.Mock()
    block.video_driver.is_picture_pending = True

    VideoBlock.load_video_finish(block)
    VideoBlock.set_status(block, "error")
    VideoBlock._picture_shown(block)

    block.video_status.hide.assert_not_called()
