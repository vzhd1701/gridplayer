"""MPV's frames drawn by GL: the texture on show stays while its video goes, and
is let go of once another takes its place or the surface goes, drawn or not.
Nothing here draws: no GL needed."""

from unittest.mock import MagicMock

import pytest
from PyQt5 import sip
from PyQt5.QtWidgets import QApplication

from gridplayer.mpv_player.renderer import RenderedVideo
from gridplayer.params.static import VideoTransform, ViewParams
from gridplayer.widgets.video_frame_mpv import MpvGLVideoSurface


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _surface(texture=5, size=(160, 90), deleted=None):
    surface = MpvGLVideoSurface(
        delete_textures=None if deleted is None else deleted.extend
    )
    surface.resize(320, 180)
    surface.set_view(ViewParams(), VideoTransform.NONE, size)
    surface.present_texture(texture, *size)
    return surface


def _shown_by(texture) -> RenderedVideo:
    video = RenderedVideo(MagicMock())
    video.latest().texture = texture
    return video


def test_a_frame_on_show_is_placed_as_painted_ones_are():
    surface = _surface()

    assert surface.has_frame()
    assert surface.frame_size() == (160, 90)
    assert surface.placement().target == (0, 0, 320, 180)


def test_the_frame_on_show_is_kept_as_its_video_goes():
    surface = _surface(texture=5)
    video = _shown_by(5)

    surface.keep_frame(video)

    assert video.latest().texture == 0
    assert surface.has_frame()


def test_a_texture_not_on_show_is_left_for_the_renderer():
    surface = _surface(texture=5)
    video = _shown_by(6)

    surface.keep_frame(video)

    assert video.latest().texture == 6


def test_a_kept_texture_goes_once_another_is_on_show():
    deleted = []
    surface = _surface(texture=5, deleted=deleted)
    surface.keep_frame(_shown_by(5))

    surface.present_texture(5, 160, 90)
    assert deleted == []

    surface.present_texture(7, 160, 90)
    assert deleted == [5]

    surface.present_texture(8, 160, 90)
    assert deleted == [5]


def test_a_kept_texture_goes_with_the_surface_never_shown():
    deleted = []
    surface = _surface(texture=5, deleted=deleted)
    surface.keep_frame(_shown_by(5))

    sip.delete(surface)

    assert deleted == [5]


def test_a_failed_video_s_frame_is_not_shown_on():
    surface = _surface(texture=5)

    surface.drop_frame()

    assert not surface.has_frame()


def test_a_kept_frame_stays_as_a_later_video_fails():
    surface = _surface(texture=5)
    surface.keep_frame(_shown_by(5))

    surface.drop_frame()

    assert surface.has_frame()


class _Waiting:
    def __init__(self, can_start=True, is_deleted=False):
        self._can_start = can_start
        self.is_deleted = is_deleted
        self.started = False

    def can_start(self):
        return self._can_start

    def start(self):
        self.started = True


def test_surfaces_start_one_a_turn(monkeypatch):
    from gridplayer.widgets import video_surface_gl

    monkeypatch.setattr(video_surface_gl.sip, "isdeleted", lambda s: s.is_deleted)
    queue = video_surface_gl._StartQueue()
    gone, not_yet, first, second = (
        _Waiting(is_deleted=True),
        _Waiting(can_start=False),
        _Waiting(),
        _Waiting(),
    )
    for surface in (gone, not_yet, first, second):
        queue.ask(surface)

    queue._start_next()

    assert (first.started, second.started) == (True, False)
    # it asks again once it can
    assert queue._waiting == [second]

    queue._start_next()

    assert second.started
    assert queue._waiting == []
    queue._timer.stop()


def test_a_surface_out_of_any_window_waits():
    surface = _surface()

    assert not surface.can_start()
    assert not surface.is_drawing()


def test_a_started_surface_says_so():
    surface = _surface()
    started = []
    surface.drawing_started.connect(lambda: started.append(True))

    surface.start()

    assert surface.is_drawing()
    assert started == [True]
