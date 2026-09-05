from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from gridplayer.models.grid_state import GridCell, GridState
from gridplayer.params.static import GridMode
from gridplayer.player.managers.grid import GridManager
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils.layout import GridLayout


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


class _Blocks:
    def __init__(self, ids):
        self.video_ids = list(ids)

    def __bool__(self):
        return bool(self.video_ids)

    def __iter__(self):
        return iter(())


def _make_grid_manager(video_ids):
    parent = QWidget()
    commands = SimpleNamespace(remove_video_blocks=lambda *_a, **_k: None)
    ctx = SimpleNamespace(
        video_blocks=_Blocks(video_ids),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=commands,
    )
    manager = GridManager(context=ctx, parent=parent)
    manager._keep_parent = parent
    return manager


def _fixed_two_in_three(manager):
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(max_rows=3, max_cols=3, preallocate=True)
    manager._grid_layout.pack_flow(["A", "B"])


def test_apply_grid_config_shrink_fixed_closes_overflow(mocker):
    manager = _make_grid_manager(["A", "B"])
    _fixed_two_in_three(manager)
    mocker.patch.object(manager, "_confirm_overflow", return_value=True)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=True)
    )

    assert ok is True
    remove.assert_called_once_with(["B"])
    assert manager._grid_layout.max_rows == 1
    assert manager._grid_layout.max_cols == 1
    assert manager._grid_layout.id_at(0, 0) == "A"
    assert manager._grid_layout.id_at(0, 1) is None


def test_apply_grid_config_shrink_cancel_keeps_videos(mocker):
    manager = _make_grid_manager(["A", "B"])
    _fixed_two_in_three(manager)
    mocker.patch.object(manager, "_confirm_overflow", return_value=False)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=True)
    )

    assert ok is False
    remove.assert_not_called()
    assert manager._grid_layout.max_rows == 3
    assert manager._grid_layout.max_cols == 3
    assert manager._grid_layout.id_at(0, 0) == "A"
    assert manager._grid_layout.id_at(0, 1) == "B"


def test_apply_grid_config_auto_to_fixed_overflow(mocker):
    manager = _make_grid_manager(["A", "B"])
    manager._flow.ids = ["A", "B"]
    mocker.patch.object(manager, "_confirm_overflow", return_value=True)
    remove = mocker.patch.object(manager._ctx.commands, "remove_video_blocks")

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.FIXED, rows=1, cols=1, preallocate=False)
    )

    assert ok is True
    remove.assert_called_once_with(["B"])
    assert manager._mode is GridMode.FIXED
    assert manager._grid_layout.id_at(0, 0) == "A"


def test_apply_grid_config_leave_fixed_with_holes(mocker):
    manager = _make_grid_manager(["A", "B"])
    manager._mode = GridMode.FIXED
    manager._grid_layout = GridLayout(
        max_rows=3,
        max_cols=3,
        preallocate=False,
        cells=[
            GridCell(video_id="A", row=0, col=0),
            GridCell(video_id="B", row=0, col=2),
        ],
    )
    question = mocker.patch(
        "gridplayer.player.managers.grid.QCustomMessageBox.question",
        return_value=QMessageBox.Yes,
    )

    ok = manager.apply_grid_config(
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0)
    )

    assert ok is True
    question.assert_called_once()
    assert manager._mode is GridMode.AUTO_ROWS
    assert manager._flow.ids == ["A", "B"]
