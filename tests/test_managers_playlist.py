import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.models.playlist import Playlist, Snapshot
from gridplayer.models.video import Video
from gridplayer.params.static import (
    AudioChannelMode,
    GridMode,
    SeekSyncMode,
    UnsavedChangesMode,
    VideoAspect,
    VideoRepeat,
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
    assert text.startswith("#GRIDPLAYER\n#P:")


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


def test_playlist_dump_keeps_position_and_state_with_overrides():
    video = Video(uri="http://example.com/a.mp4", current_position=125, is_paused=True)

    text = Playlist(videos=[video], save_position=True, save_state=False).dumps()
    assert '"current_position":125' in text
    assert '"is_paused"' not in text
    parsed = Playlist.parse(text)
    assert parsed.videos[0].current_position == 125

    text = Playlist(videos=[video], save_state=True).dumps()
    assert '"is_paused":true' in text
    parsed = Playlist.parse(text)
    assert parsed.videos[0].is_paused is True


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
    lines = text.splitlines()
    params_line = next(line for line in lines if line.startswith("#P:"))
    return json.loads(params_line[3:])["grid_state"]


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

    params_line = next(line for line in text.splitlines() if line.startswith("#P:"))

    assert params_line == "#P:{}"

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
