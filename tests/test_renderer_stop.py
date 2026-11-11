"""A render thread stuck in a GL driver's call holds nothing up for good: a
cleanup waits for it so long and leaves it behind."""

import threading
from unittest.mock import Mock

from gridplayer.mpv_player import renderer
from gridplayer.mpv_player.renderer import MpvRenderService, VideoRenderer


class _StuckRenderer(VideoRenderer):
    def __init__(self):
        super().__init__(Mock(), is_software=True)
        self.release = threading.Event()

    def run(self):
        # as in a GL call that never returns, until the test says
        self.release.wait(10)


def test_a_stuck_thread_isnt_waited_for_for_good(monkeypatch):
    monkeypatch.setattr(renderer, "STOP_WAIT_MS", 100)

    stuck = _StuckRenderer()
    stuck.start()

    try:
        assert stuck.stop() is False
    finally:
        stuck.release.set()
        stuck.wait()


def _service_with(the_renderer):
    service = MpvRenderService.__new__(MpvRenderService)
    service._log = Mock()
    service._listeners = {}
    service._own_window_players = set()
    service._renderer = the_renderer
    return service


def test_cleanup_leaves_a_stuck_thread_behind(monkeypatch):
    monkeypatch.setattr(renderer, "_left_behind", [])
    held = [Mock(), Mock()]
    stuck = Mock(stop=Mock(return_value=False), videos_held=Mock(return_value=held))
    service = _service_with(stuck)

    service.cleanup()

    # none plays on with no cell to show it
    for video in held:
        video.player.stop_playing.assert_called_once()

    # destroyed while it runs, a QThread takes the app down
    stuck.deleteLater.assert_not_called()
    stuck.setParent.assert_called_once_with(None)
    assert renderer._left_behind == [stuck]
    assert service._renderer is None


def test_cleanup_lets_a_stopped_thread_go(monkeypatch):
    monkeypatch.setattr(renderer, "_left_behind", [])
    stopped = Mock(stop=Mock(return_value=True))
    service = _service_with(stopped)

    service.cleanup()

    stopped.deleteLater.assert_called_once()
    assert renderer._left_behind == []


def test_the_videos_held_are_those_taken_and_queued():
    stuck = _StuckRenderer()
    taken, queued = Mock(), Mock()
    stuck._videos.append(taken)
    stuck._jobs.append((stuck._init_video, queued))
    stuck._jobs.append((stuck._release_video, taken))

    assert stuck.videos_held() == [taken, queued]
