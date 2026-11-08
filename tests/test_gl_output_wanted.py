"""MPV's frames are drawn by GL only with Fast picked and MPV playing: VLC,
picked or standing in, leaves Qt as it always was. A change the session didn't
start with asks for a restart."""

import pytest

from gridplayer.params import env
from gridplayer.params.static import MpvOutput, VideoDriver
from gridplayer.player.managers import settings as settings_manager
from gridplayer.player.managers.settings import SettingsManager
from gridplayer.utils import video_driver
from gridplayer.utils.video_driver import is_mpv_gl_output
from tests.conftest import FakeSettings


@pytest.fixture(autouse=True)
def _as_picked(monkeypatch):
    monkeypatch.setattr(env, "IS_MACOS", False)
    monkeypatch.setattr(video_driver, "session_video_driver", lambda picked: picked)


@pytest.mark.parametrize(
    ("output", "driver", "is_gl"),
    [
        (MpvOutput.GL, VideoDriver.MPV_HW, True),
        (MpvOutput.GL, VideoDriver.VLC_HW, False),
        (MpvOutput.GL, VideoDriver.VLC_SW_SP, False),
        (MpvOutput.READBACK, VideoDriver.MPV_HW, False),
    ],
)
def test_gl_only_with_mpv(output, driver, is_gl):
    assert is_mpv_gl_output(output, driver) is is_gl


def test_not_with_vlc_standing_in(monkeypatch):
    monkeypatch.setattr(
        video_driver, "session_video_driver", lambda picked: VideoDriver.VLC_HW
    )

    assert not is_mpv_gl_output(MpvOutput.GL, VideoDriver.MPV_HW)


def test_never_on_macos(monkeypatch):
    monkeypatch.setattr(env, "IS_MACOS", True)

    assert not is_mpv_gl_output(MpvOutput.GL, VideoDriver.MPV_HW)


def _values(driver):
    return {"player/mpv_output": MpvOutput.GL, "player/video_driver": driver}


@pytest.mark.parametrize(
    ("session_gl", "before", "after", "is_due"),
    [
        # back to MPV with Fast kept from before
        (False, VideoDriver.VLC_HW, VideoDriver.MPV_HW, True),
        (True, VideoDriver.MPV_HW, VideoDriver.VLC_SW, True),
        # back to how the session started, after a restart put off
        (False, VideoDriver.MPV_HW, VideoDriver.VLC_HW, False),
        (False, VideoDriver.VLC_HW, VideoDriver.VLC_SW, False),
    ],
)
def test_restart_for_a_change_the_session_didnt_start_with(
    monkeypatch, session_gl, before, after, is_due
):
    monkeypatch.setattr(env, "MPV_GL_OUTPUT", session_gl)
    monkeypatch.setattr(
        settings_manager, "Settings", lambda: FakeSettings(_values(after))
    )

    assert SettingsManager._is_gl_output_due(None, _values(before)) is is_due


def test_read_back_where_the_render_thread_cant_share(monkeypatch):
    """Some drivers won't share Qt's textures with the render thread's context:
    found out before any cell is made for frames drawn by GL."""

    from gridplayer.mpv_player import renderer
    from gridplayer.mpv_player.gl_context import GLContextError

    def refuse(*_args, **_kwargs):
        raise GLContextError("wglShareLists failed")

    monkeypatch.setattr(env, "MPV_GL_OUTPUT", True)
    monkeypatch.setattr(renderer, "QtShareGroup", object)
    monkeypatch.setattr(renderer, "create_gl_context", refuse)

    service = renderer.MpvRenderService.__new__(renderer.MpvRenderService)
    service._log = renderer.logging.getLogger("test")

    assert service._join_qt_share_group() is None
