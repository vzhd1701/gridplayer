"""Asking the Wayland compositor whether it draws window frames can't keep
the app from starting: whatever goes wrong, the answer is no."""

import threading

import pytest

from gridplayer.utils import wayland_frames
from gridplayer.utils.wayland_frames import compositor_draws_frames


@pytest.fixture(autouse=True)
def _asked_afresh():
    compositor_draws_frames.cache_clear()
    yield
    compositor_draws_frames.cache_clear()


@pytest.mark.parametrize(
    ("offered", "draws"),
    [
        ({b"wl_compositor", b"zxdg_decoration_manager_v1"}, True),
        ({b"wl_compositor", b"gtk_shell1"}, False),
        (None, False),
    ],
)
def test_frames_drawn_where_decorations_are_offered(monkeypatch, offered, draws):
    monkeypatch.setattr(wayland_frames, "_wayland_globals", lambda: offered)

    assert compositor_draws_frames() is draws


@pytest.mark.parametrize("error", [OSError, AttributeError, ValueError])
def test_a_failure_is_a_no(monkeypatch, error):
    def fail():
        raise error("no such symbol")

    monkeypatch.setattr(wayland_frames, "_wayland_globals", fail)

    assert compositor_draws_frames() is False


def test_no_answer_is_a_no(monkeypatch):
    monkeypatch.setattr(wayland_frames, "_ANSWER_WAIT_S", 0.05)
    release = threading.Event()

    def hang():
        release.wait(5)
        return {b"zxdg_decoration_manager_v1"}

    monkeypatch.setattr(wayland_frames, "_wayland_globals", hang)

    try:
        assert compositor_draws_frames() is False
    finally:
        release.set()
