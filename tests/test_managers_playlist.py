from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.static import (
    AudioChannelMode,
    GridMode,
    SeekSyncMode,
    VideoAspect,
    VideoRepeat,
    VideoTransform,
)
from gridplayer.player.managers.playlist import PlaylistManager
from gridplayer.settings import Settings, _default_settings


class _Playlist:
    def __init__(self, error=None):
        self.error = error
        self.saved_to = None

    def save(self, filename):
        if self.error is not None:
            raise self.error
        self.saved_to = filename

    def dumps(self):
        return "#GRIDPLAYER\n"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _settings_get(mocker):
    settings = Settings()
    real_get = settings.get

    def fake_get(key):
        try:
            return real_get(key)
        except RuntimeError:
            return _default_settings[key]

    mocker.patch.object(settings, "get", side_effect=fake_get)


def _make_manager(ctx=None):
    parent = QWidget()
    manager = PlaylistManager(
        context=SimpleNamespace() if ctx is None else ctx,
        parent=parent,
    )
    return manager, parent


def _video(name):
    return Video(
        id=uuid4(),
        uri=f"http://example.com/{name}.mp4",
        repeat_mode=VideoRepeat.SINGLE_FILE,
        is_start_random=False,
        aspect_mode=VideoAspect.FIT,
        is_muted=True,
        is_paused=False,
        transform=VideoTransform.NONE,
        stream_quality="best",
        auto_reload_timer_min=0,
        audio_channel_mode=AudioChannelMode.UNSET,
    )


def _playlist(videos, shuffle_on_load):
    return Playlist(
        videos=videos,
        shuffle_on_load=shuffle_on_load,
        seek_sync_mode=SeekSyncMode.DISABLED,
        disable_mouse_click_events=False,
        disable_mouse_wheel_events=False,
        disable_overlay=False,
        grid_state=GridState(
            mode=GridMode.AUTO_ROWS,
            is_fit=True,
            size=0,
            rows=1,
            cols=1,
            preallocate=False,
        ),
    )


def test_write_playlist_emits_playlist_saved(mocker):
    manager, _parent = _make_manager()
    playlist = _Playlist()
    mocker.patch.object(manager, "_set_saved_playlist")

    emitted = []
    manager.playlist_saved.connect(emitted.append)

    file_path = Path("saved.gpls")
    assert manager._write_playlist(playlist, file_path) is True

    assert playlist.saved_to == file_path
    assert emitted == [file_path]


def test_write_playlist_does_not_emit_playlist_saved_on_error(mocker):
    manager, _parent = _make_manager()
    playlist = _Playlist(error=OSError("disk full"))
    mocker.patch.object(manager, "_set_saved_playlist")

    emitted = []
    manager.playlist_saved.connect(emitted.append)

    assert manager._write_playlist(playlist, Path("saved.gpls")) is False
    assert playlist.saved_to is None
    assert emitted == []
    manager._set_saved_playlist.assert_not_called()


def _collect_session_signals(manager):
    collected = {
        "seek_sync_mode": [],
        "shuffle_on_load": [],
        "disable_mouse_click_events": [],
        "disable_mouse_wheel_events": [],
        "disable_overlay": [],
        "grid_state": [],
    }
    manager.seek_sync_mode_loaded.connect(collected["seek_sync_mode"].append)
    manager.shuffle_on_load_loaded.connect(collected["shuffle_on_load"].append)
    manager.disable_mouse_click_events_loaded.connect(
        collected["disable_mouse_click_events"].append
    )
    manager.disable_mouse_wheel_events_loaded.connect(
        collected["disable_mouse_wheel_events"].append
    )
    manager.disable_overlay_loaded.connect(collected["disable_overlay"].append)
    manager.grid_state_loaded.connect(collected["grid_state"].append)
    return collected


def _patch_playlist_settings(mocker, overrides):
    settings = Settings()
    real_get = settings.get

    def fake_get(key):
        if key in overrides:
            return overrides[key]
        return real_get(key)

    mocker.patch.object(settings, "get", side_effect=fake_get)


_CUSTOM_PLAYLIST_DEFAULTS = {
    "playlist/seek_sync_mode": SeekSyncMode.PERCENT,
    "playlist/shuffle_on_load": True,
    "playlist/disable_mouse_click_events": True,
    "playlist/disable_mouse_wheel_events": True,
    "playlist/disable_overlay": True,
    "playlist/grid_mode": GridMode.AUTO_COLS,
    "playlist/grid_fit": False,
    "playlist/grid_size": 3,
    "playlist/grid_rows": 3,
    "playlist/grid_cols": 3,
    "playlist/grid_preallocate": False,
}


def test_close_playlist_resets_session_to_settings_defaults(mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    _patch_playlist_settings(mocker, _CUSTOM_PLAYLIST_DEFAULTS)

    collected = _collect_session_signals(manager)
    closed = []
    manager.playlist_closed.connect(lambda: closed.append(True))

    assert manager.cmd_close_playlist() is True

    assert closed == [True]
    assert collected["seek_sync_mode"] == [SeekSyncMode.PERCENT]
    assert collected["shuffle_on_load"] == [True]
    assert collected["disable_mouse_click_events"] == [True]
    assert collected["disable_mouse_wheel_events"] == [True]
    assert collected["disable_overlay"] == [True]
    assert collected["grid_state"] == [
        GridState(mode=GridMode.AUTO_COLS, is_fit=False, size=3)
    ]


def test_close_playlist_does_not_reset_when_save_cancelled(mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "check_playlist_save", return_value=False)

    collected = _collect_session_signals(manager)
    closed = []
    manager.playlist_closed.connect(lambda: closed.append(True))

    assert manager.cmd_close_playlist() is False

    assert closed == []
    assert collected == {
        "seek_sync_mode": [],
        "shuffle_on_load": [],
        "disable_mouse_click_events": [],
        "disable_mouse_wheel_events": [],
        "disable_overlay": [],
        "grid_state": [],
    }


def test_load_playlist_applies_file_settings_after_reset(mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    _patch_playlist_settings(mocker, _CUSTOM_PLAYLIST_DEFAULTS)

    collected = _collect_session_signals(manager)

    playlist = Playlist(
        videos=[],
        seek_sync_mode=SeekSyncMode.TIMECODE,
        shuffle_on_load=False,
        disable_mouse_click_events=False,
        disable_mouse_wheel_events=False,
        disable_overlay=False,
        grid_state=GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
    )

    assert manager.load_playlist(playlist) is True

    assert collected["seek_sync_mode"] == [
        SeekSyncMode.PERCENT,
        SeekSyncMode.TIMECODE,
    ]
    assert collected["shuffle_on_load"] == [True, False]
    assert collected["disable_mouse_click_events"] == [True, False]
    assert collected["disable_mouse_wheel_events"] == [True, False]
    assert collected["disable_overlay"] == [True, False]
    assert collected["grid_state"] == [
        GridState(mode=GridMode.AUTO_COLS, is_fit=False, size=3),
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
    ]


def test_load_playlist_emits_videos_in_file_order(mocker):
    commands = mocker.Mock()
    manager, _parent = _make_manager(SimpleNamespace(commands=commands))
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    _patch_playlist_settings(mocker, _CUSTOM_PLAYLIST_DEFAULTS)

    videos = [_video("a"), _video("b")]
    loaded = []
    manager.videos_loaded.connect(loaded.append)

    playlist = _playlist(videos, shuffle_on_load=False)
    assert manager.load_playlist(playlist) is True

    assert loaded == [videos]
    commands.shuffle_layout.assert_not_called()


def test_load_playlist_shuffles_layout_when_flag_on(mocker):
    commands = mocker.Mock()
    manager, _parent = _make_manager(SimpleNamespace(commands=commands))
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    _patch_playlist_settings(mocker, _CUSTOM_PLAYLIST_DEFAULTS)

    videos = [_video("a"), _video("b")]
    loaded = []
    manager.videos_loaded.connect(loaded.append)

    playlist = _playlist(videos, shuffle_on_load=True)
    assert manager.load_playlist(playlist) is True

    assert loaded == [videos]
    commands.shuffle_layout.assert_called_once_with()


def test_process_arguments_adds_files_to_layout(mocker):
    commands = mocker.Mock()
    manager, _parent = _make_manager(SimpleNamespace(commands=commands))
    videos = ["file-a"]
    mocker.patch(
        "gridplayer.player.managers.playlist.get_playlist_path",
        return_value=None,
    )
    mocker.patch(
        "gridplayer.player.managers.playlist.filter_video_uris",
        return_value=videos,
    )

    manager.process_arguments(["a.mp4"])

    commands.add_videos_to_layout.assert_called_once_with(videos)
    commands.shuffle_layout.assert_not_called()


def test_playlist_dumps_with_none_videos():
    text = Playlist(videos=None).dumps()
    parsed = Playlist.parse(text)
    assert parsed.videos == []
    assert text.startswith("#GRIDPLAYER\n#P:")


def test_load_playlist_file_accepts_empty_template(tmp_path, mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "load_playlist", return_value=True)
    mocker.patch.object(manager, "_make_playlist", return_value=Playlist(videos=[]))

    path = tmp_path / "template.gpls"
    path.write_text(
        Playlist(
            videos=[],
            grid_state=GridState(
                mode=GridMode.FIXED,
                is_fit=True,
                size=0,
                rows=3,
                cols=4,
                preallocate=True,
            ),
            seek_sync_mode=SeekSyncMode.PERCENT,
        ).dumps(),
        encoding="utf-8",
    )

    errors = []
    loaded = []
    manager.error.connect(errors.append)
    manager.playlist_file_loaded.connect(loaded.append)

    manager.load_playlist_file(path)

    assert errors == []
    assert loaded == [path]
    loaded_playlist = manager.load_playlist.call_args[0][0]
    assert loaded_playlist.videos == []
    assert loaded_playlist.grid_state.mode == GridMode.FIXED
    assert loaded_playlist.grid_state.cols == 4
    assert loaded_playlist.grid_state.rows == 3
    assert loaded_playlist.seek_sync_mode == SeekSyncMode.PERCENT
    assert manager._saved_playlist["path"] == path


def test_load_playlist_file_rejects_empty_file_without_params(tmp_path, mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "load_playlist", return_value=True)

    path = tmp_path / "empty.gpls"
    path.write_text("#GRIDPLAYER\n", encoding="utf-8")

    errors = []
    loaded = []
    manager.error.connect(errors.append)
    manager.playlist_file_loaded.connect(loaded.append)

    manager.load_playlist_file(path)

    assert loaded == []
    assert len(errors) == 1
    assert "Empty or invalid playlist!" in errors[0]
    manager.load_playlist.assert_not_called()


def test_check_playlist_save_skips_unsaved_empty(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question"
    )

    assert manager.check_playlist_save() is True
    question.assert_not_called()


def test_check_playlist_save_prompts_dirty_empty_template(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    manager._saved_playlist = {"path": Path("template.gpls"), "state": 0}
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question",
        return_value=QMessageBox.No,
    )

    assert manager.check_playlist_save() is True
    question.assert_called_once()


def test_is_playlist_saved_command():
    manager, _parent = _make_manager()
    assert manager.commands["is_playlist_saved"]() is False
    manager._saved_playlist = {"path": Path("template.gpls"), "state": 0}
    assert manager.commands["is_playlist_saved"]() is True
