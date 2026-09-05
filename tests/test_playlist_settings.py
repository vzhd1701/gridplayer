import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.models.video import Video
from gridplayer.params.defaults_fields import PLAYLIST_FIELDS
from gridplayer.params.static import GridMode, VideoAspect
from gridplayer.playlist_settings import PlaylistSettings, grid_overrides_from_state
from gridplayer.settings import Settings, _default_settings


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _settings_get(mocker):
    settings = Settings()
    real_get = settings.get

    def fake_get(key):
        if key == "video_defaults/aspect":
            return VideoAspect.STRETCH
        try:
            return real_get(key)
        except RuntimeError:
            return _default_settings[key]

    mocker.patch.object(settings, "get", side_effect=fake_get)


def _set_grid_mode(form, mode):
    combo = form._widgets["playlist/grid_mode"]
    combo.setCurrentIndex(combo.findData(mode))


def test_get_uses_playlist_override():
    PlaylistSettings().set("video_defaults/aspect", VideoAspect.NONE)
    assert PlaylistSettings().get("video_defaults/aspect") is VideoAspect.NONE


def test_get_falls_back_to_settings():
    assert PlaylistSettings().get("video_defaults/aspect") is VideoAspect.STRETCH


def test_filter_video_uris_applies_playlist_aspect():
    from gridplayer.models.video import filter_video_uris

    PlaylistSettings().set("video_defaults/aspect", VideoAspect.NONE)
    videos = filter_video_uris(["http://example.com/a.mp4"])
    assert len(videos) == 1
    assert videos[0].aspect_mode is VideoAspect.NONE


def test_playlist_kwargs_builds_video_defaults_from_overrides(mocker):
    from gridplayer.models.playlist import Playlist

    mocker.patch.object(
        Settings(),
        "get",
        side_effect=lambda key: _default_settings[key],
    )
    PlaylistSettings().replace(
        {
            "playlist/disable_overlay": True,
            "playlist/grid_mode": GridMode.FIXED,
            "video_defaults/aspect": VideoAspect.NONE,
            "video_defaults/muted": False,
        }
    )

    playlist = Playlist(videos=[], **PlaylistSettings().playlist_kwargs())

    assert playlist.disable_overlay is True
    assert playlist.video_defaults.aspect is VideoAspect.NONE
    assert playlist.video_defaults.muted is False


def test_video_construct_picks_up_session_defaults():
    PlaylistSettings().set("video_defaults/aspect", VideoAspect.NONE)
    video = Video(uri="http://example.com/a.mp4")
    assert video.aspect_mode is VideoAspect.NONE


def test_set_is_noop_while_capture_suppressed():
    session = PlaylistSettings()
    with session.suppress_capture():
        session.set("video_defaults/aspect", VideoAspect.NONE)
    assert session.is_overridden("video_defaults/aspect") is False
    assert session.get("video_defaults/aspect") is VideoAspect.STRETCH


def test_playlist_settings_saves_aspect_even_without_edit_signal():
    from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog

    parent = QWidget()
    dialog = PlaylistSettingsDialog(
        overrides={},
        grid_state=GridState(),
        parent=parent,
    )
    combo = dialog._video_form._widgets["video_defaults/aspect"]
    combo.blockSignals(True)
    combo.setCurrentIndex(combo.findData(VideoAspect.NONE))
    combo.blockSignals(False)

    assert dialog._video_form.values()["video_defaults/aspect"] is VideoAspect.NONE
    assert "video_defaults/aspect" not in dialog._video_form.overridden_keys()
    assert dialog.result_overrides()["video_defaults/aspect"] is VideoAspect.NONE


def test_playlist_settings_does_not_mark_inherited_empty_cells():
    from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog

    parent = QWidget()
    live = GridState(
        mode=GridMode.FIXED,
        is_fit=True,
        size=0,
        rows=3,
        cols=3,
        preallocate=False,
    )
    dialog = PlaylistSettingsDialog(
        overrides={
            "playlist/grid_mode": GridMode.FIXED,
            "playlist/grid_rows": 3,
            "playlist/grid_cols": 3,
        },
        grid_state=live,
        parent=parent,
    )

    assert "playlist/grid_preallocate" not in dialog._playlist_form.overridden_keys()
    assert "playlist/grid_preallocate" not in dialog.result_overrides()


def test_grid_overrides_keep_file_preallocate_when_it_matches_settings(mocker):
    def fake_get(key):
        if key == "playlist/grid_preallocate":
            return True
        return _default_settings[key]

    mocker.patch.object(Settings(), "get", side_effect=fake_get)
    state = GridState.model_validate(
        {
            "mode": GridMode.FIXED,
            "rows": 3,
            "cols": 3,
            "preallocate": True,
        }
    )

    overrides = grid_overrides_from_state(state)

    assert overrides["playlist/grid_preallocate"] is True
    assert "playlist/grid_fit" not in overrides
    assert "playlist/grid_size" not in overrides


def test_grid_overrides_omit_preallocate_when_file_omits_it():
    state = GridState.model_validate({"mode": GridMode.FIXED, "rows": 3, "cols": 3})

    overrides = grid_overrides_from_state(state)

    assert "playlist/grid_preallocate" not in overrides
    assert overrides["playlist/grid_mode"] is GridMode.FIXED


def test_recent_list_add_uses_playlist_video_defaults(mocker):
    from gridplayer.player.managers.recent_list import RecentListManager

    parent = QWidget()
    PlaylistSettings().set("video_defaults/aspect", VideoAspect.NONE)
    manager = RecentListManager(context=object(), parent=parent)
    manager._keep_parent = parent
    mocker.patch.object(manager, "add_recent_videos")
    added = []
    manager.videos_added.connect(added.append)

    manager.cmd_add_video("http://example.com/a.mp4")

    assert len(added) == 1
    assert added[0][0].aspect_mode is VideoAspect.NONE


def test_defaults_form_disables_hidden_grid_fields():
    from gridplayer.widgets.defaults_form import DefaultsForm

    form = DefaultsForm(PLAYLIST_FIELDS)

    _set_grid_mode(form, GridMode.FIXED)
    _set_grid_mode(form, GridMode.AUTO_ROWS)

    auto_hidden = (
        "playlist/grid_rows",
        "playlist/grid_cols",
        "playlist/grid_preallocate",
    )
    auto_shown = ("playlist/grid_size", "playlist/grid_fit")
    for key in auto_hidden:
        assert form._rows[key].isHidden()
        assert not form.is_enabled(key)
    for key in auto_shown:
        assert not form._rows[key].isHidden()
        assert form.is_enabled(key)

    _set_grid_mode(form, GridMode.FIXED)

    for key in auto_hidden:
        assert not form._rows[key].isHidden()
        assert form.is_enabled(key)
    for key in auto_shown:
        assert form._rows[key].isHidden()
        assert not form.is_enabled(key)


def test_result_overrides_drops_hidden_grid_overrides():
    from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog

    live = GridState(mode=GridMode.FIXED, rows=3, cols=3, preallocate=False)
    dialog = PlaylistSettingsDialog(
        overrides={
            "playlist/grid_mode": GridMode.FIXED,
            "playlist/grid_rows": 3,
            "playlist/grid_cols": 3,
        },
        grid_state=live,
    )

    _set_grid_mode(dialog._playlist_form, GridMode.AUTO_ROWS)

    overrides = dialog.result_overrides()

    assert overrides["playlist/grid_mode"] is GridMode.AUTO_ROWS
    assert "playlist/grid_rows" not in overrides
    assert "playlist/grid_cols" not in overrides


def test_result_grid_state_keeps_live_values_for_hidden_keys():
    from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog

    live = GridState(
        mode=GridMode.FIXED, is_fit=True, size=0, rows=3, cols=3, preallocate=False
    )
    dialog = PlaylistSettingsDialog(
        overrides={"playlist/grid_mode": GridMode.FIXED},
        grid_state=live,
    )

    _set_grid_mode(dialog._playlist_form, GridMode.AUTO_ROWS)

    result = dialog.result_grid_state(live)

    assert result.mode is GridMode.AUTO_ROWS
    assert result.is_fit is True
    assert result.size == 0
    assert result.rows == 3
    assert result.cols == 3


def test_settings_dialog_save_skips_hidden_grid_fields(mocker):
    from gridplayer.dialogs.settings import SettingsDialog

    dialog = SettingsDialog(None)

    form = dialog.playlist_defaults_form
    current_mode = form._widgets["playlist/grid_mode"].currentData()
    other_mode = (
        GridMode.FIXED if current_mode is not GridMode.FIXED else GridMode.AUTO_ROWS
    )
    _set_grid_mode(form, other_mode)

    if other_mode is GridMode.FIXED:
        hidden_key = "playlist/grid_size"
    else:
        hidden_key = "playlist/grid_rows"
    hidden_widget = form._widgets[hidden_key]
    assert not form.is_enabled(hidden_key)
    hidden_widget.setValue(hidden_widget.value() + 5)

    written = {}
    mocker.patch.object(
        Settings(),
        "set",
        side_effect=lambda key, value: written.__setitem__(key, value),
    )

    dialog.save_settings()

    assert hidden_key not in written
    assert written["playlist/grid_mode"] is other_mode
