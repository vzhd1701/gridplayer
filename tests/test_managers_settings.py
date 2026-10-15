from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtWidgets import QApplication, QDialog, QWidget

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

        def exec_(self):
            return QDialog.Accepted

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
