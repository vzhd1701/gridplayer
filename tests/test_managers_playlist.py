import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.models.playlist import (
    FORMAT_ID,
    FORMAT_VERSION,
    Playlist,
    Snapshot,
    UnsupportedPlaylistVersion,
)
from gridplayer.models.video import Video
from gridplayer.params.static import (
    AudioChannelMode,
    GridMode,
    SeekSyncMode,
    UnsavedChangesMode,
    VideoAspect,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.player.managers.playlist import PlaylistManager
from gridplayer.playlist_settings import PlaylistSettings, grid_overrides_from_state
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
    """Answer with the shipped defaults, never with this machine's settings."""

    mocker.patch.object(Settings(), "get", side_effect=_default_settings.__getitem__)


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
        end_action=VideoEndAction.LOOP_FILE,
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
        "pause_background_videos": [],
        "pause_minimized": [],
        "show_overlay_border": [],
        "overlay_hide_on_timeout": [],
        "overlay_timeout": [],
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
    manager.pause_background_videos_loaded.connect(
        collected["pause_background_videos"].append
    )
    manager.pause_minimized_loaded.connect(collected["pause_minimized"].append)
    manager.show_overlay_border_loaded.connect(collected["show_overlay_border"].append)
    manager.overlay_hide_on_timeout_loaded.connect(
        collected["overlay_hide_on_timeout"].append
    )
    manager.overlay_timeout_loaded.connect(collected["overlay_timeout"].append)
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
    "playlist/pause_background_videos": False,
    "playlist/pause_minimized": False,
    "playlist/show_overlay_border": True,
    "playlist/overlay_hide_on_timeout": False,
    "playlist/overlay_timeout": 7,
    "playlist/grid_mode": GridMode.AUTO_COLS,
    "playlist/grid_fit": False,
    "playlist/grid_size": 3,
    "playlist/grid_rows": 3,
    "playlist/grid_cols": 3,
    "playlist/grid_preallocate": False,
}


def test_close_playlist_resets_session_to_settings_defaults(mocker):
    manager, _parent = _make_manager(_ctx_with_grid(GridState()))
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
    assert collected["pause_background_videos"] == [False]
    assert collected["pause_minimized"] == [False]
    assert collected["show_overlay_border"] == [True]
    assert collected["overlay_hide_on_timeout"] == [False]
    assert collected["overlay_timeout"] == [7]
    assert collected["grid_state"] == [
        GridState(mode=GridMode.AUTO_COLS, is_fit=False, size=3)
    ]


def test_force_close_playlist_does_not_ask(mocker):
    """Closing the window asks first, then force closes.

    A second prompt after a Discard would be a regression, so make the stub
    refuse: if the check ran at all, the close could not go through.
    """
    manager, _parent = _make_manager(_ctx_with_grid(GridState()))
    check = mocker.patch.object(manager, "check_playlist_save", return_value=False)

    closed = []
    manager.playlist_closed.connect(lambda: closed.append(True))

    manager.cmd_force_close_playlist()

    check.assert_not_called()
    assert closed == [True]


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
        "pause_background_videos": [],
        "pause_minimized": [],
        "show_overlay_border": [],
        "overlay_hide_on_timeout": [],
        "overlay_timeout": [],
        "grid_state": [],
    }


def test_load_playlist_applies_file_settings_after_reset(mocker):
    manager, _parent = _make_manager(_ctx_with_grid(GridState()))
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
        pause_background_videos=True,
        pause_minimized=True,
        show_overlay_border=False,
        overlay_hide_on_timeout=True,
        overlay_timeout=3,
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
    assert collected["pause_background_videos"] == [False, True]
    assert collected["pause_minimized"] == [False, True]
    assert collected["show_overlay_border"] == [True, False]
    assert collected["overlay_hide_on_timeout"] == [False, True]
    assert collected["overlay_timeout"] == [7, 3]
    assert collected["grid_state"] == [
        GridState(mode=GridMode.AUTO_COLS, is_fit=False, size=3),
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
    ]


def test_load_playlist_emits_videos_in_file_order(mocker):
    commands = mocker.Mock()
    manager, _parent = _make_manager(_ctx_with_grid(GridState(), commands=commands))
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
    manager, _parent = _make_manager(_ctx_with_grid(GridState(), commands=commands))
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
    assert json.loads(text) == {"format": FORMAT_ID, "version": FORMAT_VERSION}


def test_playlist_parse_accepts_header_only():
    parsed = Playlist.parse("#GRIDPLAYER\n")
    assert parsed.videos == []
    assert parsed.snapshots is None


def test_playlist_omits_inherited_session_fields():
    text = Playlist(videos=[], disable_overlay=True).dumps()
    parsed = Playlist.parse(text)
    assert parsed.disable_overlay is True
    assert parsed.seek_sync_mode is None
    assert parsed.video_defaults.muted is None


def test_playlist_dump_omits_position_and_state_by_default(mocker):
    _patch_playlist_settings(
        mocker, {"playlist/save_position": False, "playlist/save_state": False}
    )
    video = Video(uri="http://example.com/a.mp4", current_position=125, is_paused=True)

    text = Playlist(videos=[video]).dumps()

    assert "current_position" not in text
    assert "is_paused" not in text
    assert "is_stopped" not in text
    assert "playback_state" not in text


def test_playlist_dump_keeps_position_and_state_with_overrides():
    video = Video(uri="http://example.com/a.mp4", current_position=125, is_paused=True)

    text = Playlist(videos=[video], save_position=True, save_state=False).dumps()
    video_dump = json.loads(text)["videos"][0]
    assert video_dump["current_position"] == 125
    assert "is_paused" not in video_dump
    assert "playback_state" not in video_dump
    parsed = Playlist.parse(text)
    assert parsed.videos[0].current_position == 125

    text = Playlist(videos=[video], save_state=True).dumps()
    video_dump = json.loads(text)["videos"][0]
    assert video_dump["playback_state"] == "paused"
    assert "is_paused" not in video_dump
    assert "is_stopped" not in video_dump
    parsed = Playlist.parse(text)
    assert parsed.videos[0].is_paused is True
    assert parsed.videos[0].is_stopped is False
    assert parsed.videos[0].playback_state is VideoInitialState.PAUSED


def test_playlist_dump_writes_stopped_when_save_state():
    video = Video(
        uri="http://example.com/a.mp4",
        is_paused=True,
        is_stopped=True,
    )

    text = Playlist(videos=[video], save_state=True).dumps()
    video_dump = json.loads(text)["videos"][0]
    assert video_dump["playback_state"] == "stopped"
    assert "is_paused" not in video_dump
    assert "is_stopped" not in video_dump
    parsed = Playlist.parse(text)
    assert parsed.videos[0].is_paused is True
    assert parsed.videos[0].is_stopped is True
    assert parsed.videos[0].playback_state is VideoInitialState.STOPPED


def test_playlist_parse_playback_state_stopped():
    text = (
        "#GRIDPLAYER\n"
        '#P:{"save_state":true}\n'
        '#V0:{"playback_state":"stopped"}\n'
        "http://example.com/a.mp4\n"
    )
    parsed = Playlist.parse(text)
    assert parsed.videos[0].playback_state is VideoInitialState.STOPPED
    assert parsed.videos[0].is_paused is True
    assert parsed.videos[0].is_stopped is True
    dumped = json.loads(parsed.dumps())["videos"][0]
    assert "is_paused" not in dumped
    assert dumped["playback_state"] == "stopped"


def test_playlist_parse_old_paused_video_is_not_stopped():
    text = (
        "#GRIDPLAYER\n"
        '#P:{"save_state":true}\n'
        '#V0:{"is_paused":true}\n'
        "http://example.com/a.mp4\n"
    )
    parsed = Playlist.parse(text)
    assert parsed.videos[0].is_paused is True
    assert parsed.videos[0].is_stopped is False


def test_playlist_migrates_repeat_video_default():
    playlist = Playlist.model_validate(
        {"videos": [], "video_defaults": {"repeat": "none"}}
    )

    assert playlist.video_defaults.end_action is VideoEndAction.STOP
    dumped = json.loads(playlist.dumps())
    defaults = dumped["settings"]["video_defaults"]
    assert "repeat" not in defaults
    assert defaults["end_action"] == "stop"


def test_playlist_migrates_repeat_mode_on_video():
    video = Video(uri="http://example.com/a.mp4", repeat_mode="dir")

    assert video.end_action is VideoEndAction.NEXT_FILE
    dumped = json.loads(Playlist(videos=[video]).dumps())["videos"][0]
    assert "repeat_mode" not in dumped
    assert dumped["end_action"] == "next_file"


def test_playlist_migrates_paused_video_default():
    playlist = Playlist.model_validate(
        {"videos": [], "video_defaults": {"paused": True}}
    )

    assert playlist.video_defaults.initial_state is VideoInitialState.PAUSED
    dumped = json.loads(playlist.dumps())
    defaults = dumped["settings"]["video_defaults"]
    assert "paused" not in defaults
    assert defaults["initial_state"] == "paused"


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
    assert manager._saved_playlist_path == path


def test_load_playlist_file_accepts_header_only_empty_playlist(tmp_path, mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "load_playlist", return_value=True)
    mocker.patch.object(manager, "_make_playlist", return_value=Playlist(videos=[]))

    path = tmp_path / "empty.gpls"
    path.write_text("#GRIDPLAYER\n", encoding="utf-8")

    errors = []
    loaded = []
    manager.error.connect(errors.append)
    manager.playlist_file_loaded.connect(loaded.append)

    manager.load_playlist_file(path)

    assert errors == []
    assert loaded == [path]
    loaded_playlist = manager.load_playlist.call_args[0][0]
    assert loaded_playlist.videos == []
    assert manager._saved_playlist_path == path


def test_load_playlist_file_rejects_blank_file(tmp_path, mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "load_playlist", return_value=True)

    path = tmp_path / "blank.gpls"
    path.write_text("   \n\n", encoding="utf-8")

    errors = []
    manager.error.connect(errors.append)

    manager.load_playlist_file(path)

    assert len(errors) == 1
    assert "Invalid playlist format!" in errors[0]
    manager.load_playlist.assert_not_called()


def test_playlist_settings_applies_grid_via_config_not_restore(mocker):
    apply = mocker.Mock(return_value=True)
    ctx = SimpleNamespace(
        commands=SimpleNamespace(apply_grid_config=apply),
        grid_state=GridState(
            mode=GridMode.FIXED,
            rows=3,
            cols=3,
            preallocate=True,
        ),
    )
    manager, _parent = _make_manager(ctx)
    new_state = GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=True)
    dialog = mocker.Mock()
    dialog.exec_.return_value = True
    dialog.result_overrides.return_value = {}
    dialog.result_grid_state.return_value = new_state
    mocker.patch(
        "gridplayer.player.managers.playlist.PlaylistSettingsDialog",
        return_value=dialog,
    )
    restored = []
    manager.grid_state_loaded.connect(restored.append)

    manager.cmd_playlist_settings()

    apply.assert_called_once_with(new_state)
    assert restored == []


def test_check_playlist_save_skips_unsaved_empty(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question"
    )

    assert manager.check_playlist_save() is True
    question.assert_not_called()


def test_check_playlist_save_prompts_dirty_empty_template(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    manager._saved_playlist_path = Path("template.gpls")
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question",
        return_value=QMessageBox.No,
    )

    assert manager.check_playlist_save() is True
    question.assert_called_once()


def test_check_playlist_save_discard_mode_skips_prompt(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    manager._saved_playlist_path = Path("x.gpls")
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    save = mocker.patch.object(manager, "cmd_save_playlist")
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question"
    )
    PlaylistSettings().set("playlist/unsaved_changes", UnsavedChangesMode.DISCARD)

    assert manager.check_playlist_save() is True
    save.assert_not_called()
    question.assert_not_called()


def test_check_playlist_save_auto_save_discard_saves_named_playlist(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    manager._saved_playlist_path = Path("x.gpls")
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    save = mocker.patch.object(manager, "cmd_save_playlist", return_value=True)
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question"
    )
    PlaylistSettings().set(
        "playlist/unsaved_changes", UnsavedChangesMode.AUTO_SAVE_DISCARD
    )

    assert manager.check_playlist_save() is True
    save.assert_called_once_with()
    question.assert_not_called()


def test_check_playlist_save_auto_save_discard_drops_unnamed_playlist(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    save = mocker.patch.object(manager, "cmd_save_playlist")
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question"
    )
    PlaylistSettings().set(
        "playlist/unsaved_changes", UnsavedChangesMode.AUTO_SAVE_DISCARD
    )

    assert manager.check_playlist_save() is True
    save.assert_not_called()
    question.assert_not_called()


def test_check_playlist_save_auto_save_ask_saves_named_playlist(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    manager._saved_playlist_path = Path("x.gpls")
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    save = mocker.patch.object(manager, "cmd_save_playlist", return_value=True)
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question"
    )
    PlaylistSettings().set("playlist/unsaved_changes", UnsavedChangesMode.AUTO_SAVE_ASK)

    assert manager.check_playlist_save() is True
    save.assert_called_once_with()
    question.assert_not_called()


def test_check_playlist_save_auto_save_ask_prompts_unnamed_playlist(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    save = mocker.patch.object(manager, "cmd_save_playlist")
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question",
        return_value=QMessageBox.No,
    )
    PlaylistSettings().set("playlist/unsaved_changes", UnsavedChangesMode.AUTO_SAVE_ASK)

    assert manager.check_playlist_save() is True
    save.assert_not_called()
    question.assert_called_once()


def test_check_playlist_save_auto_save_failure_falls_back_to_ask(mocker):
    manager, _parent = _make_manager(SimpleNamespace(video_blocks=[]))
    manager._saved_playlist_path = Path("x.gpls")
    mocker.patch.object(manager, "_is_playlist_changed", return_value=True)
    save = mocker.patch.object(manager, "cmd_save_playlist", return_value=False)
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question",
        return_value=QMessageBox.No,
    )
    PlaylistSettings().set(
        "playlist/unsaved_changes", UnsavedChangesMode.AUTO_SAVE_DISCARD
    )

    assert manager.check_playlist_save() is True
    save.assert_called_once_with()
    question.assert_called_once()


def test_playlist_parse_migrates_legacy_track_changes_true():
    playlist = Playlist.parse(
        '#GRIDPLAYER\n#P:{"track_changes": true}\nhttp://example.com/a.mp4\n'
    )

    assert playlist.unsaved_changes is UnsavedChangesMode.ASK


def test_playlist_parse_migrates_legacy_track_changes_false():
    playlist = Playlist.parse(
        '#GRIDPLAYER\n#P:{"track_changes": false}\nhttp://example.com/a.mp4\n'
    )

    assert playlist.unsaved_changes is UnsavedChangesMode.DISCARD


def test_is_playlist_saved_command():
    manager, _parent = _make_manager()
    assert manager.commands["is_playlist_saved"]() is False
    manager._saved_playlist_path = Path("template.gpls")
    assert manager.commands["is_playlist_saved"]() is True


def _grid_in_dump(text):
    return json.loads(text)["settings"]["grid_state"]


def test_playlist_dump_omits_inherited_grid_keys():
    text = Playlist(
        videos=[],
        grid_state=GridState(mode=GridMode.FIXED, rows=3, cols=3),
    ).dumps()

    grid = _grid_in_dump(text)

    assert set(grid) == {"mode", "rows", "cols"}
    assert "preallocate" not in grid
    assert "is_fit" not in grid
    assert "size" not in grid
    assert "cells" not in grid
    assert "video_order" not in grid

    parsed = Playlist.parse(text)
    overrides = grid_overrides_from_state(parsed.grid_state)

    assert "playlist/grid_preallocate" not in overrides
    assert "playlist/grid_fit" not in overrides
    assert "playlist/grid_size" not in overrides
    assert overrides["playlist/grid_mode"] is GridMode.FIXED


def test_playlist_dump_keeps_explicit_grid_keys():
    text = Playlist(
        videos=[],
        grid_state=GridState(preallocate=True),
    ).dumps()

    parsed = Playlist.parse(text)
    overrides = grid_overrides_from_state(parsed.grid_state)

    assert overrides == {"playlist/grid_preallocate": True}


def test_playlist_dump_keeps_snapshot_grid_state():
    text = Playlist(
        videos=[],
        grid_state=GridState(preallocate=False),
        snapshots={
            1: Snapshot(
                grid_state=GridState(
                    mode=GridMode.FIXED, rows=3, cols=3, preallocate=True
                ),
                videos=[],
            ),
        },
    ).dumps()

    parsed = Playlist.parse(text)

    assert parsed.snapshots[1].grid_state.rows == 3
    assert parsed.snapshots[1].grid_state.cols == 3
    assert parsed.snapshots[1].grid_state.preallocate is True


def test_playlist_dump_omits_empty_grid_state_and_snapshots():
    text = Playlist(videos=[]).dumps()

    assert json.loads(text) == {"format": FORMAT_ID, "version": FORMAT_VERSION}

    parsed = Playlist.parse(text)

    assert parsed.videos == []
    assert parsed.snapshots is None
    assert parsed.grid_state.cells == []
    assert parsed.grid_state.video_order == []


def test_playlist_dump_keeps_nonempty_cells_and_order():
    text = Playlist(
        videos=[],
        grid_state=GridState(
            cells=[GridCell(video_id="a", row=0, col=0)],
            video_order=["a"],
        ),
    ).dumps()

    grid = _grid_in_dump(text)

    assert set(grid) == {"cells", "video_order"}
    assert grid["cells"] == [
        {"video_id": "a", "row": 0, "col": 0, "rowspan": 1, "colspan": 1}
    ]
    assert grid["video_order"] == ["a"]


def _ctx_with_grid(live_grid, commands=None):
    return SimpleNamespace(
        grid_state=live_grid,
        window_state=None,
        snapshots={},
        is_shuffle_on_load=False,
        video_blocks=SimpleNamespace(blocks_for_ids=lambda ids: []),
        commands=commands
        if commands is not None
        else SimpleNamespace(layout_order=lambda: []),
    )


def test_make_playlist_dumps_only_session_grid_overrides():
    manager, _parent = _make_manager(
        _ctx_with_grid(
            GridState(
                mode=GridMode.FIXED,
                is_fit=True,
                size=0,
                rows=3,
                cols=3,
                preallocate=True,
            )
        )
    )
    PlaylistSettings().replace(
        {
            "playlist/grid_mode": GridMode.FIXED,
            "playlist/grid_rows": 3,
            "playlist/grid_cols": 3,
        }
    )

    playlist = manager._make_playlist()
    grid = _grid_in_dump(playlist.dumps())

    assert set(grid) == {"mode", "rows", "cols"}


def test_reset_grid_override_marks_playlist_changed():
    manager, _parent = _make_manager(
        _ctx_with_grid(
            GridState(
                mode=GridMode.FIXED,
                is_fit=True,
                size=0,
                rows=3,
                cols=3,
                preallocate=True,
            )
        )
    )
    grid_state = GridState(mode=GridMode.FIXED, rows=3, cols=3, preallocate=True)
    PlaylistSettings().replace(grid_overrides_from_state(grid_state))
    manager._set_saved_playlist(Path("x.gpls"))

    assert manager._is_playlist_changed() is False

    PlaylistSettings().reset("playlist/grid_preallocate")

    assert manager._is_playlist_changed() is True


def test_init_baselines_fresh_session():
    manager, _parent = _make_manager(_ctx_with_grid(GridState()))

    manager.init()

    assert manager._saved_playlist_path is None
    assert manager._is_playlist_changed() is False


def test_check_playlist_save_alerts_modified_empty_playlist(mocker):
    manager, _parent = _make_manager(_ctx_with_grid(GridState()))
    manager.init()
    PlaylistSettings().set("playlist/disable_overlay", True)
    question = mocker.patch(
        "gridplayer.player.managers.playlist.QCustomMessageBox.cancellable_question",
        return_value=QMessageBox.No,
    )

    assert manager.check_playlist_save() is True
    question.assert_called_once()


def test_close_playlist_rebaselines_to_pristine(mocker):
    manager, _parent = _make_manager(
        _ctx_with_grid(GridState(mode=GridMode.FIXED, rows=3, cols=3, preallocate=True))
    )
    PlaylistSettings().replace(
        {
            "playlist/grid_mode": GridMode.FIXED,
            "playlist/grid_rows": 3,
            "playlist/grid_cols": 3,
        }
    )
    manager._set_saved_playlist(Path("x.gpls"))
    mocker.patch.object(manager, "check_playlist_save", return_value=True)
    closed = []
    manager.playlist_closed.connect(lambda: closed.append(True))

    assert manager.cmd_close_playlist() is True

    assert closed == [True]
    assert manager._saved_playlist_path is None
    assert manager._is_playlist_changed() is False


def _local_video_file(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0")
    return path


def test_playlist_dump_relative_paths(tmp_path):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    playlist = Playlist(
        videos=[Video(uri=video_file), _video("b")],
        save_paths_relative=True,
    )

    text = playlist.dumps(base_dir=tmp_path)

    doc = json.loads(text)
    assert set(doc) <= {"format", "version", "settings", "videos", "snapshots"}
    assert doc["settings"]["save_paths_relative"] is True
    assert [video["uri"] for video in doc["videos"]] == [
        "videos/a.mp4",
        "http://example.com/b.mp4",
    ]
    assert str(tmp_path) not in text


def test_playlist_dump_relative_paths_requires_flag(tmp_path):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    playlist = Playlist(videos=[Video(uri=video_file)])

    text = playlist.dumps(base_dir=tmp_path)

    assert json.loads(text)["videos"][0]["uri"] == str(video_file)
    assert "save_paths_relative" not in text


def test_playlist_dump_relative_paths_falls_back_to_absolute(tmp_path, mocker):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    playlist = Playlist(videos=[Video(uri=video_file)], save_paths_relative=True)
    mocker.patch(
        "gridplayer.models.video_uri.os.path.relpath",
        side_effect=ValueError("different drive"),
    )

    text = playlist.dumps(base_dir=tmp_path)

    assert json.loads(text)["videos"][0]["uri"] == str(video_file)


def test_playlist_parse_resolves_relative_paths_against_base_dir(tmp_path):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    text = "#GRIDPLAYER\nvideos/a.mp4\n"

    playlist = Playlist.parse(text, base_dir=tmp_path)

    assert playlist.videos[0].uri == video_file


def test_playlist_parse_keeps_urls_with_base_dir(tmp_path):
    playlist = Playlist.parse(
        "#GRIDPLAYER\nhttp://example.com/a.mp4\n", base_dir=tmp_path
    )

    assert playlist.videos[0].uri == "http://example.com/a.mp4"


def test_playlist_parse_without_base_dir_keeps_cwd_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    video_file = _local_video_file(tmp_path, "a.mp4")

    playlist = Playlist.parse("#GRIDPLAYER\na.mp4\n")

    assert playlist.videos[0].uri == video_file


def test_load_playlist_file_resolves_relative_paths(tmp_path):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    playlist_file = tmp_path / "p.gpls"
    playlist_file.write_text("#GRIDPLAYER\nvideos/a.mp4\n", encoding="utf-8")

    manager, _parent = _make_manager(_ctx_with_grid(GridState()))
    loaded = []
    manager.videos_loaded.connect(loaded.append)

    manager.load_playlist_file(playlist_file)

    assert [v.uri for v in loaded[0]] == [video_file]


def test_playlist_dump_relative_paths_follows_settings_when_unset(tmp_path, mocker):
    _patch_playlist_settings(mocker, {"playlist/save_paths_relative": True})
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    playlist = Playlist(videos=[Video(uri=video_file)])

    text = playlist.dumps(base_dir=tmp_path)

    assert json.loads(text)["videos"][0]["uri"] == "videos/a.mp4"
    assert str(tmp_path) not in text


def test_playlist_dump_parent_relative_paths_roundtrip(tmp_path):
    media_dir = tmp_path / "media"
    playlist_dir = tmp_path / "playlists"
    playlist_dir.mkdir()
    video_file = _local_video_file(media_dir, "a.mp4")
    playlist = Playlist(
        videos=[Video(uri=video_file)],
        save_paths_relative=True,
    )

    text = playlist.dumps(base_dir=playlist_dir)

    assert json.loads(text)["videos"][0]["uri"] == "../media/a.mp4"

    parsed = Playlist.parse(text, base_dir=playlist_dir)

    assert parsed.videos[0].uri == video_file


def test_playlist_save_read_relative_paths(tmp_path):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    playlist_file = tmp_path / "p.gpls"
    Playlist(videos=[Video(uri=video_file)], save_paths_relative=True).save(
        playlist_file
    )

    text = playlist_file.read_text(encoding="utf-8")
    assert json.loads(text)["videos"][0]["uri"] == "videos/a.mp4"

    parsed = Playlist.read(playlist_file)
    assert parsed.videos[0].uri == video_file


def test_playlist_relative_snapshot_uris_match_videos(tmp_path):
    video_file = _local_video_file(tmp_path, "videos/a.mp4")
    video = Video(uri=video_file)
    playlist = Playlist(
        videos=[video],
        snapshots={
            0: Snapshot(grid_state=GridState(), videos=[video.model_copy()]),
        },
        save_paths_relative=True,
    )

    text = playlist.dumps(base_dir=tmp_path)
    doc = json.loads(text)
    assert doc["videos"][0]["uri"] == "videos/a.mp4"
    assert doc["snapshots"]["0"]["videos"][0]["uri"] == "videos/a.mp4"

    parsed = Playlist.parse(text, base_dir=tmp_path)

    assert parsed.videos[0].uri == parsed.snapshots[0].videos[0].uri == video_file
    assert isinstance(parsed.videos[0].uri, Path)
    assert isinstance(parsed.snapshots[0].videos[0].uri, Path)


def test_playlist_parse_resolves_snapshot_uris_when_cwd_differs(tmp_path, monkeypatch):
    playlist_dir = tmp_path / "playlist"
    other_dir = tmp_path / "other"
    playlist_dir.mkdir()
    other_dir.mkdir()
    video_file = _local_video_file(playlist_dir, "a.mp4")
    _local_video_file(other_dir, "a.mp4")
    monkeypatch.chdir(other_dir)

    text = (
        "#GRIDPLAYER\n"
        '#P:{"snapshots":{"0":{"grid_state":{},"videos":[{"uri":"a.mp4"}]}}}\n'
        "a.mp4\n"
    )
    parsed = Playlist.parse(text, base_dir=playlist_dir)

    assert parsed.videos[0].uri == video_file
    assert parsed.snapshots[0].videos[0].uri == video_file


def test_playlist_parse_converts_absolute_snapshot_file_uris_to_path(tmp_path):
    video_file = _local_video_file(tmp_path, "a.mp4")
    text = (
        "#GRIDPLAYER\n"
        '#P:{"snapshots":{"0":{"grid_state":{},"videos":[{"uri":'
        + json.dumps(str(video_file))
        + "}]}}}\n"
        f"{video_file}\n"
    )

    parsed = Playlist.parse(text)

    assert parsed.videos[0].uri == parsed.snapshots[0].videos[0].uri == video_file
    assert isinstance(parsed.snapshots[0].videos[0].uri, Path)


def test_playlist_json_dump_uses_envelope_keys():
    video = _video("a")
    text = Playlist(
        videos=[video],
        disable_overlay=True,
        snapshots={
            0: Snapshot(grid_state=GridState(), videos=[video.model_copy()]),
        },
    ).dumps()
    doc = json.loads(text)

    assert list(doc)[:2] == ["format", "version"]
    assert doc["format"] == FORMAT_ID
    assert doc["version"] == FORMAT_VERSION
    assert set(doc) == {"format", "version", "settings", "videos", "snapshots"}
    assert "disable_overlay" not in doc
    assert doc["settings"]["disable_overlay"] is True
    assert doc["videos"][0]["uri"] == "http://example.com/a.mp4"
    assert "snapshots" not in doc["settings"]
    assert b'"format": "gridplayer-playlist"' in text.encode("utf-8")[:64]

    parsed = Playlist.parse(text)
    assert parsed.disable_overlay is True
    assert parsed.videos[0].uri == video.uri
    assert parsed.snapshots[0].videos[0].uri == video.uri


def test_playlist_json_round_trip():
    playlist = Playlist(
        videos=[_video("a")],
        disable_overlay=True,
        seek_sync_mode=SeekSyncMode.PERCENT,
        save_state=True,
    )
    parsed = Playlist.parse(playlist.dumps())

    assert parsed.disable_overlay is True
    assert parsed.seek_sync_mode is SeekSyncMode.PERCENT
    assert parsed.videos[0].uri == "http://example.com/a.mp4"


def test_playlist_parse_json_missing_version_is_v1():
    parsed = Playlist.parse(
        json.dumps(
            {
                "format": FORMAT_ID,
                "settings": {"disable_overlay": True},
                "videos": [{"uri": "http://example.com/a.mp4"}],
            }
        )
    )

    assert parsed.disable_overlay is True
    assert parsed.videos[0].uri == "http://example.com/a.mp4"


def test_playlist_parse_rejects_wrong_format_id():
    with pytest.raises(ValueError, match="Playlist format is not valid"):
        Playlist.parse(json.dumps({"format": "other", "version": 1}))


def test_playlist_parse_rejects_newer_version():
    with pytest.raises(UnsupportedPlaylistVersion) as exc_info:
        Playlist.parse(json.dumps({"format": FORMAT_ID, "version": FORMAT_VERSION + 1}))

    assert exc_info.value.version == FORMAT_VERSION + 1


def test_playlist_parse_rejects_invalid_json():
    with pytest.raises(ValueError, match="Playlist format is not valid"):
        Playlist.parse("{not json")


def test_playlist_parse_header_plus_json_uses_legacy_path():
    json_body = Playlist(videos=[], disable_overlay=True).dumps()
    parsed = Playlist.parse("#GRIDPLAYER\n" + json_body)

    assert parsed.videos == []
    assert parsed.disable_overlay is None


def test_playlist_read_strips_utf8_bom(tmp_path):
    path = tmp_path / "bom.gpls"
    body = Playlist(videos=[], disable_overlay=True).dumps()
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))

    parsed = Playlist.read(path)

    assert parsed.disable_overlay is True
    assert parsed.videos == []


def test_playlist_parse_compact_json():
    body = json.dumps(
        {
            "format": FORMAT_ID,
            "version": FORMAT_VERSION,
            "settings": {"disable_overlay": True},
            "videos": [{"uri": "http://example.com/a.mp4"}],
        },
        separators=(",", ":"),
    )

    parsed = Playlist.parse(body)

    assert parsed.disable_overlay is True
    assert parsed.videos[0].uri == "http://example.com/a.mp4"
    assert b'"format":"gridplayer-playlist"' in body.encode("utf-8")[:64]


def test_playlist_parse_json_skips_invalid_videos():
    parsed = Playlist.parse(
        json.dumps(
            {
                "format": FORMAT_ID,
                "version": 1,
                "videos": [
                    {"uri": "http://example.com/good.mp4"},
                    {"uri": "http://example.com/bad.mp4", "rate": "nope"},
                    "not-an-object",
                    {"uri": 123},
                    {"no_uri": True},
                    {"uri": "http://example.com/also-good.mp4"},
                ],
            }
        )
    )

    assert [video.uri for video in parsed.videos] == [
        "http://example.com/good.mp4",
        "http://example.com/also-good.mp4",
    ]


def test_playlist_parse_json_rejects_non_object_settings():
    with pytest.raises(ValueError, match="Playlist format is not valid"):
        Playlist.parse(json.dumps({"format": FORMAT_ID, "version": 1, "settings": []}))


def test_playlist_parse_json_rejects_version_zero():
    with pytest.raises(ValueError, match="Playlist format is not valid"):
        Playlist.parse(json.dumps({"format": FORMAT_ID, "version": 0}))


def test_playlist_parse_json_rejects_bool_version():
    with pytest.raises(ValueError, match="Playlist format is not valid"):
        Playlist.parse(json.dumps({"format": FORMAT_ID, "version": True}))


def test_load_playlist_file_rejects_newer_version(tmp_path, mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "load_playlist", return_value=True)

    path = tmp_path / "new.gpls"
    path.write_text(
        json.dumps({"format": FORMAT_ID, "version": FORMAT_VERSION + 1}),
        encoding="utf-8",
    )

    errors = []
    manager.error.connect(errors.append)

    manager.load_playlist_file(path)

    assert len(errors) == 1
    assert "This playlist was saved with a newer GridPlayer" in errors[0]
    manager.load_playlist.assert_not_called()


def test_load_playlist_file_rejects_invalid_settings(tmp_path, mocker):
    manager, _parent = _make_manager()
    mocker.patch.object(manager, "load_playlist", return_value=True)

    path = tmp_path / "bad.gpls"
    path.write_text(
        json.dumps(
            {
                "format": FORMAT_ID,
                "version": 1,
                "settings": {"overlay_timeout": "nope"},
            }
        ),
        encoding="utf-8",
    )

    errors = []
    manager.error.connect(errors.append)

    manager.load_playlist_file(path)

    assert len(errors) == 1
    assert "Invalid playlist format!" in errors[0]
    manager.load_playlist.assert_not_called()
