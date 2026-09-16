from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.player.manager import Commands, Context
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.player.managers.window_state import WindowStateManager
from gridplayer.widgets.video_frame_vlc_sw import VideoFrameVLCSW


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _StubSWFrame(VideoFrameVLCSW):
    def driver_setup(self, vlc_options):
        return MagicMock()


class _StubBlock:
    def __init__(self, events, name):
        self._events = events
        self.id = name
        self.video_id = name
        self.video_params = MagicMock()

    def cleanup_start(self):
        self._events.append(("start", self.id))

    def close_silently(self):
        self._events.append(("close", self.id))


@pytest.fixture
def blocks_manager():
    parent = QWidget()
    manager = VideoBlocksManager(context=Context(), parent=parent)

    def _with_blocks(*names):
        events = []
        for name in names:
            block = _StubBlock(events, name)
            manager._ctx.video_blocks.append(block)
            manager.close_all_signal.connect(block.close_silently)
        return events

    yield manager, _with_blocks


def test_frame_cleanup_start_does_not_wait():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])

    frame.cleanup_start()

    frame.video_driver.cleanup_start.assert_called_once()
    frame.video_driver.cleanup_wait.assert_not_called()


def test_frame_cleanup_start_is_idempotent():
    frame = _StubSWFrame(process_manager=MagicMock(), vlc_options=[])

    frame.cleanup_start()
    frame.cleanup()

    frame.video_driver.cleanup_start.assert_called_once()
    frame.video_driver.cleanup_wait.assert_called_once()


def test_close_all_starts_every_player_before_closing_any(blocks_manager):
    manager, with_blocks = blocks_manager
    events = with_blocks("a", "b", "c")

    manager.close_all()

    assert events == [
        ("start", "a"),
        ("start", "b"),
        ("start", "c"),
        ("close", "a"),
        ("close", "b"),
        ("close", "c"),
    ]


def test_remove_videos_starts_every_player_before_closing_any(blocks_manager):
    manager, with_blocks = blocks_manager
    events = with_blocks("a", "b")

    manager.remove_videos(["a", "b"])

    assert events == [
        ("start", "a"),
        ("start", "b"),
        ("close", "a"),
        ("close", "b"),
    ]


def _window_state_manager(commands):
    window = QWidget()
    ctx = Context()
    ctx.commands = Commands()
    ctx.commands.update(commands)

    return WindowStateManager(context=ctx, parent=window), window, ctx


def test_close_event_hides_window_before_tearing_players_down(mocker):
    mocker.patch("gridplayer.player.managers.window_state.force_terminate")

    events = []
    manager, window, _ = _window_state_manager(
        {
            "check_playlist_save": lambda: (events.append("ask"), True)[1],
            "force_close_playlist": lambda: events.append("close"),
        }
    )
    mocker.patch.object(window, "hide", lambda: events.append("hide"))

    manager.closeEvent(MagicMock())

    assert events == ["ask", "hide", "close"]


def test_close_event_keeps_window_when_save_is_cancelled(mocker):
    terminate = mocker.patch("gridplayer.player.managers.window_state.force_terminate")

    manager, _, ctx = _window_state_manager(
        {
            "check_playlist_save": lambda: False,
            "force_close_playlist": MagicMock(),
        }
    )
    event = MagicMock()

    assert manager.closeEvent(event) is True

    event.ignore.assert_called_once()
    ctx.commands.force_close_playlist.assert_not_called()
    terminate.assert_not_called()
