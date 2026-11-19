from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.params.static import GridMode
from gridplayer.player.managers import settings as settings_manager
from gridplayer.player.managers.settings import SettingsManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings, _default_settings


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _default_grid():
    return GridState(
        mode=GridMode.AUTO_ROWS,
        is_fit=True,
        size=0,
        rows=3,
        cols=3,
        preallocate=False,
    )


def _manager(apply, grid_state=None):
    parent = QWidget()
    ctx = SimpleNamespace(
        commands=SimpleNamespace(apply_grid_config=apply),
        grid_state=grid_state if grid_state is not None else _default_grid(),
    )
    manager = SettingsManager(context=ctx, parent=parent)
    manager._keep_parent = parent
    return manager


def test_apply_settings_applies_grid_config_when_grid_changed(mocker):
    apply = mocker.Mock()
    manager = _manager(apply)
    current = dict(_default_settings)
    current["playlist/grid_mode"] = GridMode.FIXED
    current["playlist/grid_rows"] = 1
    current["playlist/grid_cols"] = 1
    mocker.patch.object(Settings(), "get", side_effect=current.__getitem__)

    manager._apply_settings(dict(_default_settings))

    apply.assert_called_once()
    config = apply.call_args[0][0]
    assert config.mode is GridMode.FIXED
    assert config.rows == 1
    assert config.cols == 1


def test_apply_settings_updates_inherited_grid_fields_only(mocker):
    apply = mocker.Mock()
    PlaylistSettings().set("playlist/grid_mode", GridMode.FIXED)
    live = GridState(
        mode=GridMode.FIXED,
        is_fit=True,
        size=0,
        rows=3,
        cols=3,
        preallocate=False,
    )
    manager = _manager(apply, grid_state=live)
    current = dict(_default_settings)
    current["playlist/grid_preallocate"] = True
    mocker.patch.object(Settings(), "get", side_effect=current.__getitem__)

    manager._apply_settings(dict(_default_settings))

    apply.assert_called_once()
    config = apply.call_args[0][0]
    assert config.mode is GridMode.FIXED
    assert config.rows == 3
    assert config.cols == 3
    assert config.preallocate is True


def test_apply_settings_keeps_overridden_grid_field(mocker):
    apply = mocker.Mock()
    PlaylistSettings().set("playlist/grid_mode", GridMode.FIXED)
    PlaylistSettings().set("playlist/grid_preallocate", False)
    live = GridState(
        mode=GridMode.FIXED,
        is_fit=True,
        size=0,
        rows=3,
        cols=3,
        preallocate=False,
    )
    manager = _manager(apply, grid_state=live)
    current = dict(_default_settings)
    current["playlist/grid_preallocate"] = True
    mocker.patch.object(Settings(), "get", side_effect=current.__getitem__)

    manager._apply_settings(dict(_default_settings))

    apply.assert_not_called()


def test_apply_settings_skips_grid_config_when_unchanged(mocker):
    apply = mocker.Mock()
    manager = _manager(apply)
    mocker.patch.object(Settings(), "get", side_effect=_default_settings.__getitem__)

    manager._apply_settings(dict(_default_settings))

    apply.assert_not_called()


def test_apply_settings_tells_the_videos_about_sponsorblock(mocker):
    manager = _manager(mocker.Mock())
    changed = mocker.Mock()
    manager.sponsorblock_changed.connect(changed)
    current = dict(_default_settings)
    current["sponsorblock/enabled"] = True
    mocker.patch.object(Settings(), "get", side_effect=current.__getitem__)

    manager._apply_settings(dict(_default_settings))

    changed.assert_called_once_with()


def test_apply_settings_leaves_sponsorblock_be_when_unchanged(mocker):
    manager = _manager(mocker.Mock())
    changed = mocker.Mock()
    manager.sponsorblock_changed.connect(changed)
    mocker.patch.object(Settings(), "get", side_effect=_default_settings.__getitem__)

    manager._apply_settings(dict(_default_settings))

    changed.assert_not_called()


def test_the_dialog_is_gone_before_the_settings_are_applied(mocker):
    """Applying a theme styles over every widget there is: a closed Settings
    dialog left behind would be, every time it had been opened."""

    made = []

    class Dialog(QDialog):
        def __init__(self, parent):
            super().__init__(parent)
            made.append(self)

        def exec(self):
            return QDialog.DialogCode.Accepted

    mocker.patch.object(settings_manager, "SettingsDialog", Dialog)
    manager = _manager(mocker.Mock())
    alive = []
    mocker.patch.object(
        manager,
        "_apply_settings",
        side_effect=lambda _: alive.append(not sip.isdeleted(made[0])),
    )
    mocker.patch.object(manager, "_is_restart_needed", return_value=False)
    mocker.patch.object(manager, "_is_reload_needed", return_value=False)

    manager.cmd_settings()

    assert alive == [False]
    assert manager._keep_parent.findChildren(QDialog) == []


def test_a_change_of_mpv_output_opens_the_videos_again():
    from gridplayer.params.static import MpvOutput

    Settings().set("player/mpv_output", MpvOutput.READBACK)
    previous = Settings().get_all()
    Settings().set("player/mpv_output", MpvOutput.WINDOW)

    manager = _manager(lambda *_: None)
    manager._ctx.video_blocks = []

    try:
        assert manager._is_reload_needed(previous)
    finally:
        Settings().set("player/mpv_output", _default_settings["player/mpv_output"])


def _after_dialog(mocker, *, restart, reload, videos, output_due=None):
    """cmd_settings with the dialog closed at once: the reloads asked for and
    the restart message's details, if it was shown."""

    class Dialog(QDialog):
        def exec(self):
            return QDialog.DialogCode.Accepted

    mocker.patch.object(settings_manager, "SettingsDialog", Dialog)
    told = mocker.patch.object(settings_manager.QCustomMessageBox, "information")

    manager = _manager(mocker.Mock())
    manager._ctx.video_blocks = videos
    mocker.patch.object(manager, "_apply_settings")
    mocker.patch.object(manager, "_is_restart_needed", return_value=restart)
    mocker.patch.object(manager, "_is_reload_needed", return_value=reload)
    # what's due on restart is what draws the videos, unless said otherwise
    is_output_due = restart if output_due is None else output_due
    mocker.patch.object(manager, "_is_gl_output_due", return_value=is_output_due)
    mocker.patch.object(manager, "_is_qt_platform_due", return_value=False)
    reloads = []
    manager.reload.connect(lambda: reloads.append(True))

    manager.cmd_settings()

    info = told.call_args.kwargs["info"] if told.called else None
    return len(reloads), info


def test_videos_open_are_not_reloaded_when_a_restart_will_do_it(mocker):
    reloads, info = _after_dialog(mocker, restart=True, reload=True, videos=[object()])

    assert reloads == 0
    assert "stay as they are" in info


def test_with_no_videos_open_the_reload_still_lets_go_of_vlc(mocker):
    reloads, info = _after_dialog(mocker, restart=True, reload=True, videos=[])

    assert reloads == 1
    assert "stay as they are" not in info


def test_a_reload_with_no_restart_due_happens_at_once(mocker):
    reloads, info = _after_dialog(mocker, restart=False, reload=True, videos=[object()])

    assert reloads == 1
    assert info is None


def test_a_restart_alone_says_nothing_of_the_videos(mocker):
    reloads, info = _after_dialog(mocker, restart=True, reload=False, videos=[object()])

    assert reloads == 0
    assert "stay as they are" not in info


def test_a_restart_for_something_else_leaves_the_reload_be(mocker):
    """The language and the VLC options changed together: the options reach
    the videos at once, whether or not the app is restarted."""

    reloads, info = _after_dialog(
        mocker, restart=True, reload=True, videos=[object()], output_due=False
    )

    assert reloads == 1
    assert "stay as they are" not in info
