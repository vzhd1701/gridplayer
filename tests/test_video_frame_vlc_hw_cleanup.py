from unittest.mock import Mock

import gridplayer.widgets.video_frame_vlc_hw as vlc_hw_mod
from gridplayer.widgets.video_frame_vlc_hw import PlayerProcessSingleVLCHW


class _StoppingMediaPlayer:
    """Fake libvlc media player telling of its stop as VLC does."""

    def __init__(self, player):
        self._player = player

    def stop(self):
        self._player.cb_stopped(None)

    def set_xwindow(self, xid): ...

    def release(self): ...


def test_linux_release_stop_is_not_an_error(monkeypatch):
    """On Linux the player stops its video before letting the window go:
    that stop is not one of a video stopping by itself."""

    monkeypatch.setattr(vlc_hw_mod.env, "IS_LINUX", True)

    player = object.__new__(PlayerProcessSingleVLCHW)
    player.id = "p1"
    player.init_semaphore = Mock()
    player.release_callback = Mock()
    player.cmd_send = Mock()
    player.notify_error = Mock()
    player.notify_playback_status_changed = Mock()
    player.is_video_initialized = True
    player.media_input = Mock(is_live=False)
    player._log = Mock()
    player._timer_extract_media_track = None
    player._timer_audio_slave = None
    player._timer_subtitle_slave = None
    player._timer_unpause_failsafe = None
    player._event_waiter = Mock()
    player._playlist_player = None
    player._media_player = _StoppingMediaPlayer(player)

    player.cleanup()

    player.notify_error.assert_not_called()
    player.release_callback.assert_called_once_with("p1")
