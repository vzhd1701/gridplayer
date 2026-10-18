from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

import gridplayer.widgets.video_frame_vlc_base as vlc_base
from gridplayer.params.static import (
    HWCropBorderOffset,
    VideoAnchor,
    VideoCellViewMode,
    VideoCrop,
    VideoShift,
    VideoTransform,
)
from gridplayer.utils import darkmode
from gridplayer.utils.win32_vlc_vout import VlcPicture
from gridplayer.vlc_player.static import VideoTrack
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_status import StatusControl
from gridplayer.widgets.video_frame_vlc_base import (
    FIRST_PICTURE_PLACE_TIMEOUT_MS,
    FIRST_PICTURE_TIMEOUT_MS,
    FIRST_PLAYBACK_TIMEOUT_MS,
)
from gridplayer.widgets.video_frame_vlc_hw_sp import VideoFrameVLCHWSP
from gridplayer.widgets.video_frame_vlc_sw_sp import VideoFrameVLCSWSP
from gridplayer.widgets.video_overlay import OverlayMode

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
    # as calc_vlc_picture has it: nothing to go by without the frame size
    frame._vlc_picture_rect = lambda window_size: (
        PLACED if all(frame._frame_size()) else None
    )
    frame.shown = []
    frame.picture_shown.connect(lambda: frame.shown.append(frame.now[0]))

    return frame


def _load(frame, frame_size=(1920, 1080)):
    track = VideoTrack(
        video_dimensions=frame_size,
        fps=None,
        codec="H264",
        bitrate=0,
        language=None,
        description=None,
    )
    frame.load_video_finish(
        MagicMock(is_audio_only=False, cur_video_track=track, video_tracks={1: track})
    )


def _load_stream(frame):
    """A stream that comes with no frame size, as an HLS one can."""
    _load(frame, frame_size=(0, 0))


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


# a picture VLC drew for the view worked out without the frame size: all of
# the frame, in its own shape, bars at its sides
DRAWN_WITHOUT_SIZE = (76, 0, 264, 250)


def test_stream_picture_kept_out_of_sight_until_vlc_plays(frame, monkeypatch):
    """VLC keeps a stream's first picture up, frozen, until playback proper
    starts, and stretches it over the view's shape once it takes the view
    up: its window is where it should be all that time."""
    vlc = _Vlc(monkeypatch)

    _load_stream(frame)
    vlc.draws(rect=DRAWN_WITHOUT_SIZE)
    _at(frame, 100)
    frame.set_track_dimensions(1920, 1080)
    vlc.draws()
    _at(frame, 150)
    _at(frame, 700)

    assert frame.is_picture_pending

    frame._on_playback_started()
    _at(frame, 800)
    _at(frame, 800 + FRAME_MS + 1)

    assert frame.shown == [800 + FRAME_MS + 1]


def test_stream_waits_for_playback_with_no_vlc_windows_to_go_by(frame, monkeypatch):
    """Off Windows the playback is all there is to go by."""
    monkeypatch.setattr(vlc_base, "vlc_picture", lambda _surface: None)

    _load_stream(frame)
    _at(frame, 700)

    assert frame.is_picture_pending

    frame._on_playback_started()
    _at(frame, 800)

    assert frame.shown == [800]


def test_stream_picture_not_judged_before_its_frame_size_is_in(frame, monkeypatch):
    """Where the picture goes is worked out from the frame's size."""
    vlc = _Vlc(monkeypatch)

    _load_stream(frame)
    frame._on_playback_started()
    vlc.draws(rect=DRAWN_WITHOUT_SIZE)
    _at(frame, 100)
    _at(frame, 100 + FIRST_PICTURE_PLACE_TIMEOUT_MS + FRAME_MS)

    assert frame.is_picture_pending

    frame.set_track_dimensions(1920, 1080)
    vlc.draws()
    _at(frame, 600)
    _at(frame, 600 + FRAME_MS + 1)

    assert frame.shown == [600 + FRAME_MS + 1]


def test_stream_that_never_plays_is_given_up_on_in_time(frame, monkeypatch):
    vlc = _Vlc(monkeypatch)

    _load_stream(frame)
    frame.set_track_dimensions(1920, 1080)
    vlc.draws()
    _at(frame, FIRST_PLAYBACK_TIMEOUT_MS)

    assert frame.is_picture_pending

    _at(frame, FIRST_PLAYBACK_TIMEOUT_MS + 1)

    assert frame.shown == [FIRST_PLAYBACK_TIMEOUT_MS + 1]


def test_stream_playback_is_waited_for_again_on_the_next_load(frame, monkeypatch):
    monkeypatch.setattr(vlc_base, "vlc_picture", lambda _surface: None)

    _load_stream(frame)
    frame._on_playback_started()
    _at(frame, 100)

    _start_loading(frame, is_paused=False)
    _load_stream(frame)
    _at(frame, 900)

    assert frame.is_picture_pending


def _start_loading(frame, is_paused):
    """What the frame is handed to load, as far as the wait goes."""
    frame.load_video(
        MagicMock(
            video=MagicMock(
                cell_view_mode=VideoCellViewMode.FILL,
                scale=1.0,
                crop=VideoCrop(0, 0, 0, 0),
                anchor=VideoAnchor.CENTER,
                shift=VideoShift(0, 0),
                is_shift_past_edges=False,
                transform=VideoTransform.NONE,
                is_paused=is_paused,
            )
        )
    )


def test_stream_loaded_paused_is_not_waited_on_to_play(frame, monkeypatch):
    """It never does."""
    monkeypatch.setattr(vlc_base, "vlc_picture", lambda _surface: None)

    _start_loading(frame, is_paused=True)
    _load_stream(frame)

    assert not frame.is_picture_pending


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
    block.status = StatusControl(block)

    VideoBlock.load_video_finish(block)
    block.status.show("error")
    VideoBlock._picture_shown(block)

    block.video_status.hide.assert_not_called()


def _block_showing_overlays(mocker, is_picture_pending):
    block = mocker.Mock()
    block.video_driver.is_picture_pending = is_picture_pending
    block._ctx.is_drag_ui = False
    block._ctx.is_disable_overlay = False
    block._ctx.is_overlay_hide_on_timeout = False
    block.is_loading = False
    block._is_error = False
    block.is_overlay_fits = True
    block.isVisible.return_value = True
    block.show_overlay = lambda: VideoBlock.show_overlay(block)
    return block


def test_cell_overlay_says_loading_until_the_picture_is_up(mocker):
    """Up over the loading status still counting, a stream's for longest,
    with Stop rather than the video's controls."""
    block = _block_showing_overlays(mocker, is_picture_pending=True)
    block.is_stopped = False
    block.is_video_initialized = True
    block.is_error = False
    block.status = StatusControl(block)

    VideoBlock.load_video_finish(block)
    # the mouse moving over it meanwhile
    block.show_overlay()

    block.overlay.set_mode.assert_called_with(OverlayMode.LOADING)

    VideoBlock._picture_shown(block)

    block.overlay.set_mode.assert_called_with(OverlayMode.VIDEO)


def test_cell_shows_its_overlay_on_the_load_with_nothing_to_wait_for(mocker):
    block = _block_showing_overlays(mocker, is_picture_pending=False)

    VideoBlock.load_video_finish(block)

    block.overlay.show.assert_called_once()
