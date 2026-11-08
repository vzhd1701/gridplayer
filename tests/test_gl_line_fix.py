"""The black line fix: set up before the app starts unless it's Off, and on
Auto taken off again once the app is up, unless OpenGL is NVIDIA's."""

import pytest

import gridplayer.main.init_app as init_app
import gridplayer.mpv_player.gl_context as gl_context
import gridplayer.settings as settings
from gridplayer.params import env
from gridplayer.params.static import GLLineFix
from tests.conftest import FakeSettings


@pytest.fixture
def settle(monkeypatch):
    monkeypatch.setattr(env, "MPV_GL_OUTPUT", True)
    monkeypatch.setattr(env, "IS_WINDOWS", True)

    alpha = []
    monkeypatch.setattr(init_app, "set_gl_alpha", alpha.append)

    def run(fix, vendor):
        monkeypatch.setattr(
            settings, "Settings", lambda: FakeSettings({"internal/gl_line_fix": fix})
        )
        monkeypatch.setattr(gl_context, "wgl_vendor", lambda: vendor)
        init_app.settle_gl_line_fix()
        return alpha

    return run


@pytest.mark.parametrize(
    ("vendor", "alpha"),
    [
        ("NVIDIA Corporation", []),
        ("ATI Technologies Inc.", [0]),
        ("Intel", [0]),
        (None, [0]),
    ],
)
def test_auto_keeps_it_for_nvidia_only(settle, vendor, alpha):
    assert settle(GLLineFix.AUTO, vendor) == alpha


@pytest.mark.parametrize("fix", [GLLineFix.ON, GLLineFix.OFF])
def test_on_and_off_are_left_as_set_up(settle, fix):
    assert settle(fix, "ATI Technologies Inc.") == []
