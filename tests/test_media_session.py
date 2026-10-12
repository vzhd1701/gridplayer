from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget

from gridplayer.player.managers import media_session as media_session_module
from gridplayer.player.managers.actions import ActionsManager
from gridplayer.player.managers.media_session import MediaSessionManager
from gridplayer.utils.keymap import default_keymap
from gridplayer.utils.media_session import (
    KEY_NEXT,
    KEY_PAUSE,
    KEY_PLAY,
    KEY_PLAY_PAUSE,
    KEY_PREVIOUS,
    KEY_STOP,
    MediaState,
    PlaybackStatus,
)

DEFAULT_BINDINGS = {
    KEY_PLAY_PAUSE: "Play / Pause [ALL]",
    KEY_PLAY: "Play / Pause [ALL]",
    KEY_PAUSE: "Pause [ALL]",
    KEY_STOP: "Stop [ALL]",
    KEY_NEXT: "Next Video",
    KEY_PREVIOUS: "Previous Video",
}


class FakeSession(QObject):
    command = pyqtSignal(str)
    raise_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.states = []
        self.is_closed = False

    def update(self, state):
        self.states.append(state)

    def close(self):
        self.is_closed = True


class FakeBlock:
    def __init__(self, title, is_paused=False, is_visible=True):
        self.title = title
        self.video_params = SimpleNamespace(
            is_paused=is_paused, uri_name=f"{title}.uri"
        )
        self._is_visible = is_visible

    def isVisible(self):
        return self._is_visible


class FakeBlocks(list):
    @property
    def unpaused(self):
        return [vb for vb in self if not vb.video_params.is_paused]


class FakeActions:
    def __init__(self, bindings=None, unavailable=()):
        self.bindings = dict(DEFAULT_BINDINGS if bindings is None else bindings)
        self.unavailable = set(unavailable)
        self.triggered = []

    def action_for_key(self, key):
        return self.bindings.get(key)

    def is_action_available(self, action_id):
        return action_id not in self.unavailable

    def trigger(self, action_id):
        self.triggered.append(action_id)
        return True


@pytest.fixture
def session(monkeypatch):
    sessions = []

    def make(parent):
        sessions.append(FakeSession(parent))
        return sessions[-1]

    monkeypatch.setattr(media_session_module, "make_media_session", make)

    return sessions


def _manager(blocks=(), actions=None, playlist_path=None, is_single_mode=False):
    parent = QWidget()
    calls = []
    ctx = SimpleNamespace(
        video_blocks=FakeBlocks(blocks),
        actions_manager=actions if actions is not None else FakeActions(),
        is_single_mode=is_single_mode,
        commands=SimpleNamespace(
            saved_playlist_path=lambda: playlist_path,
            forget_minimize_pause=lambda: calls.append("forget"),
            activate_window=lambda: calls.append("activate"),
        ),
    )
    manager = MediaSessionManager(context=ctx, parent=parent)
    manager._keep_parent = parent
    manager.calls = calls
    manager.set_enabled(True)
    return manager


def test_default_media_keys_bindings():
    keymap = default_keymap()

    for key, action_id in DEFAULT_BINDINGS.items():
        owners = [a for a, keys in keymap.items() if key in keys]
        assert owners == [action_id], key

    assert keymap["Play [ALL]"] == []


def test_action_for_key_reads_the_keymap():
    actions = ActionsManager.__new__(ActionsManager)
    actions._bindings = {
        "Play / Pause [ALL]": ["Space", KEY_PLAY_PAUSE],
        "Next Video": ["N"],
    }

    assert actions.action_for_key(KEY_PLAY_PAUSE) == "Play / Pause [ALL]"
    assert actions.action_for_key("N") == "Next Video"
    assert actions.action_for_key(KEY_NEXT) is None


def test_no_videos_never_takes_the_keys(session):
    _manager()

    assert session[0].states == []


def test_last_video_closed_lets_the_keys_go(session):
    manager = _manager(blocks=[FakeBlock("one")])

    manager._ctx.video_blocks.clear()
    manager.refresh()

    assert session[0].states[-1] is None


def test_playing_grid_state(session):
    _manager(
        blocks=[FakeBlock("one"), FakeBlock("two", is_paused=True)],
        actions=FakeActions(unavailable={"Next Video", "Previous Video"}),
    )

    assert session[0].states == [
        MediaState(
            status=PlaybackStatus.PLAYING,
            title="Videos: 2",
            keys=frozenset({KEY_PLAY_PAUSE, KEY_PLAY, KEY_PAUSE, KEY_STOP}),
        )
    ]


def test_all_paused_is_paused(session):
    _manager(blocks=[FakeBlock("one", is_paused=True)])

    assert session[0].states[-1].status is PlaybackStatus.PAUSED


def test_title_one_video_saved_playlist_and_single_mode(session):
    _manager(blocks=[FakeBlock("one")])
    _manager(blocks=[FakeBlock(None)])
    _manager(
        blocks=[FakeBlock("one"), FakeBlock("two")],
        playlist_path=Path("/videos/my grid.gpls"),
    )
    _manager(
        blocks=[FakeBlock("one", is_visible=False), FakeBlock("two")],
        is_single_mode=True,
    )

    titles = [s.states[-1].title for s in session]
    assert titles == ["one", "None.uri", "my grid", "two"]


def test_same_state_is_not_told_twice(session):
    manager = _manager(blocks=[FakeBlock("one")])

    manager.refresh()
    manager.refresh()

    assert len(session[0].states) == 1


def test_media_key_runs_the_bound_action(session):
    actions = FakeActions()
    manager = _manager(blocks=[FakeBlock("one")], actions=actions)

    session[0].command.emit(KEY_NEXT)

    assert actions.triggered == ["Next Video"]
    assert manager.calls == []


def test_play_and_pause_fall_back_to_the_play_pause_key(session):
    actions = FakeActions(bindings={KEY_PLAY_PAUSE: "Play / Pause"})
    manager = _manager(blocks=[FakeBlock("one")], actions=actions)

    session[0].command.emit(KEY_PAUSE)
    manager._ctx.video_blocks[0].video_params.is_paused = True
    session[0].command.emit(KEY_PLAY)

    assert actions.triggered == ["Play / Pause", "Play / Pause"]


def test_play_while_playing_never_pauses_through_play_pause(session):
    actions = FakeActions()
    _manager(blocks=[FakeBlock("one")], actions=actions)

    session[0].command.emit(KEY_PLAY)

    assert actions.triggered == []


def test_pause_while_paused_never_plays_through_play_pause(session):
    actions = FakeActions(bindings={KEY_PLAY_PAUSE: "Toggle"})
    _manager(blocks=[FakeBlock("one", is_paused=True)], actions=actions)

    session[0].command.emit(KEY_PAUSE)

    assert actions.triggered == []


def test_play_bound_elsewhere_runs_while_playing(session):
    actions = FakeActions(bindings={KEY_PLAY_PAUSE: "Toggle", KEY_PLAY: "Play [ALL]"})
    _manager(blocks=[FakeBlock("one")], actions=actions)

    session[0].command.emit(KEY_PLAY)

    assert actions.triggered == ["Play [ALL]"]


def test_play_pause_falls_back_by_what_is_playing(session):
    actions = FakeActions(bindings={KEY_PLAY: "Play [ALL]", KEY_PAUSE: "Pause [ALL]"})
    manager = _manager(blocks=[FakeBlock("one")], actions=actions)

    session[0].command.emit(KEY_PLAY_PAUSE)
    manager._ctx.video_blocks[0].video_params.is_paused = True
    session[0].command.emit(KEY_PLAY_PAUSE)

    assert actions.triggered == ["Pause [ALL]", "Play [ALL]"]


def test_unbound_key_does_nothing(session):
    actions = FakeActions(bindings={})
    _manager(blocks=[FakeBlock("one")], actions=actions)

    session[0].command.emit(KEY_STOP)

    assert actions.triggered == []


def test_media_key_while_minimized_forgets_the_minimize_pause(session, mocker):
    manager = _manager(blocks=[FakeBlock("one")])
    mocker.patch.object(manager.parent(), "isMinimized", return_value=True)

    session[0].command.emit(KEY_PAUSE)

    assert manager.calls == ["forget"]


def test_raise_brings_the_window_up(session):
    manager = _manager(blocks=[FakeBlock("one")])

    session[0].raise_requested.emit()

    assert manager.calls == ["activate"]


def test_turned_off_closes_the_session(session):
    manager = _manager(blocks=[FakeBlock("one")])

    manager.set_enabled(False)
    manager.refresh()

    assert session[0].is_closed
    assert len(session[0].states) == 1


def test_no_session_to_be_had(monkeypatch):
    monkeypatch.setattr(media_session_module, "make_media_session", lambda _: None)

    manager = _manager(blocks=[FakeBlock("one")])
    manager.refresh()

    assert manager._session is None
