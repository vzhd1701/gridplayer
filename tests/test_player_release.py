"""Nothing may reach a player after libVLC has freed it.

Commands keep arriving at a player process until its loop stops, and some of
them come from VLC itself: its events schedule re-applies of the view and the
tracks for later. Reload a grid of streams while they start and one of those
lands behind the release, inside a libVLC call on freed memory.
"""

from unittest.mock import MagicMock

from gridplayer.vlc_player.player_base_threaded import VlcPlayerThreaded


class _Player(VlcPlayerThreaded):
    def __init__(self):
        super().__init__(vlc_instance=None)

        self.ran = []

    def _reapply_tracks(self):
        self.ran.append("_reapply_tracks")


def _released_player():
    player = _Player()
    player._media_player = MagicMock()
    player._tracks_manager = MagicMock()

    player.cmd_process_command((), "cleanup")

    return player


def test_commands_still_queued_are_dropped_once_the_player_is_released():
    player = _released_player()

    player.cmd_process_command((), "_reapply_tracks")

    assert player.ran == []


def test_commands_before_the_release_still_run():
    player = _Player()

    player.cmd_process_command((), "_reapply_tracks")

    assert player.ran == ["_reapply_tracks"]


def test_the_release_frees_the_player_once():
    player = _Player()
    media_player = MagicMock()
    player._media_player = media_player

    player.cmd_process_command((), "cleanup")
    player.cmd_process_command((), "cleanup")

    media_player.release.assert_called_once_with()


def test_tracks_are_not_put_back_on_a_released_player():
    """The tracks manager keeps the player it was made with."""
    player = VlcPlayerThreaded(vlc_instance=None)
    tracks_manager = MagicMock()
    player._tracks_manager = tracks_manager
    player._media_player = MagicMock()

    player.cleanup()
    player._reapply_tracks()

    tracks_manager.reapply.assert_not_called()
