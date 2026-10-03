from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.params.static import GridMode
from gridplayer.player.managers.grid import GridManager
from gridplayer.player.managers.single_mode import SingleModeManager
from gridplayer.settings import Settings


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)


def _block(mocker, *, block_id, is_paused, is_stopped=False):
    vb = mocker.Mock()
    vb.id = block_id
    vb.video_params.is_paused = is_paused
    vb.is_stopped = is_stopped
    return vb


def _manager(mocker, blocks, active, pause_background=True):
    ctx = SimpleNamespace(
        is_single_mode=False,
        is_pause_background_videos=pause_background,
        active_block=active,
        video_blocks=blocks,
        commands=SimpleNamespace(grid_cell_count=lambda: len(blocks)),
    )
    manager = SingleModeManager(context=ctx)
    manager._ctx.is_pause_background_videos = pause_background
    return manager


def test_single_mode_pauses_only_playing_background(mocker):
    active = _block(mocker, block_id="a", is_paused=False)
    playing = _block(mocker, block_id="b", is_paused=False)
    paused = _block(mocker, block_id="c", is_paused=True)
    stopped = _block(mocker, block_id="d", is_paused=True, is_stopped=True)
    manager = _manager(mocker, [active, playing, paused, stopped], active)

    manager.single_mode_on()

    playing.set_pause.assert_called_once_with(True)
    paused.set_pause.assert_not_called()
    stopped.set_pause.assert_not_called()
    stopped.stop_playback.assert_not_called()
    playing.hide.assert_called_once()
    paused.hide.assert_called_once()
    stopped.hide.assert_called_once()


def test_single_mode_off_resumes_only_paused_playing(mocker):
    active = _block(mocker, block_id="a", is_paused=False)
    playing = _block(mocker, block_id="b", is_paused=False)
    stopped = _block(mocker, block_id="d", is_paused=True, is_stopped=True)
    manager = _manager(mocker, [active, playing, stopped], active)
    manager.single_mode_on()
    playing.set_pause.reset_mock()

    manager.single_mode_off()

    playing.set_pause.assert_called_once_with(False)
    stopped.set_pause.assert_not_called()
    stopped.stop_playback.assert_not_called()


def test_single_mode_does_not_pause_when_setting_off(mocker):
    active = _block(mocker, block_id="a", is_paused=False)
    playing = _block(mocker, block_id="b", is_paused=False)
    manager = _manager(mocker, [active, playing], active, pause_background=False)

    manager.single_mode_on()

    playing.set_pause.assert_not_called()
    playing.hide.assert_called_once()


class _Cell(QWidget):
    """A video as the grid sees one, noting every size it is given."""

    def __init__(self, video_id, parent):
        super().__init__(parent)
        self.id = video_id
        self.video_id = video_id
        self.sizes = []

    def resizeEvent(self, event):
        self.sizes.append((event.size().width(), event.size().height()))


class _Cells:
    def __init__(self, cells):
        self._cells = cells

    @property
    def video_ids(self):
        return [c.video_id for c in self._cells]

    def __bool__(self):
        return bool(self._cells)

    def __iter__(self):
        return iter(self._cells)

    def __len__(self):
        return len(self._cells)

    def by_video_id(self, video_id):
        return next((c for c in self._cells if c.video_id == video_id), None)

    def blocks_for_ids(self, video_ids):
        return [self.by_video_id(i) for i in video_ids if self.by_video_id(i)]


@pytest.mark.parametrize(
    "grid_state",
    [
        GridState(mode=GridMode.AUTO_ROWS, is_fit=True, size=0),
        GridState(mode=GridMode.FIXED, rows=3, cols=3, preallocate=True),
    ],
    ids=["auto", "fixed_with_empty_cells"],
)
@pytest.mark.parametrize("single", [0, 4])
def test_leaving_single_mode_resizes_only_the_single_video_once(grid_state, single):
    """No video is laid out in a grid it is not going to end up in.

    A hardware video holds back a resize that comes right after another,
    so one shown at an in-between size stays drawn at that size for a while.
    """
    window = QWidget()
    window.resize(1200, 700)
    cells = [_Cell(f"v{n}", window) for n in range(6)]
    ctx = SimpleNamespace(
        is_single_mode=False,
        is_shuffle_on_load=False,
        active_block=cells[single],
        video_blocks=_Cells(cells),
    )
    grid = GridManager(context=ctx, parent=window)
    single_mode = SingleModeManager(context=ctx)
    ctx.is_pause_background_videos = False
    ctx.commands = SimpleNamespace(
        grid_cell_count=lambda: grid.grid_dimensions.max_size,
        remove_video_blocks=lambda *_a: None,
    )
    grid.layout_changed.connect(grid.reload_video_grid)
    single_mode.mode_changed.connect(grid.on_single_mode_changed)

    grid.set_grid_state(grid_state)
    window.show()
    QApplication.processEvents()
    in_grid = [c.geometry() for c in cells]

    single_mode.single_mode_on()
    QApplication.processEvents()
    assert cells[single].size() == window.size()
    for cell in cells:
        cell.sizes.clear()

    single_mode.single_mode_off()

    assert [c.geometry() for c in cells] == in_grid
    assert all(c.isVisible() for c in cells)
    expected = in_grid[single].size()
    assert cells[single].sizes == [(expected.width(), expected.height())]
    assert [c.sizes for n, c in enumerate(cells) if n != single] == [[]] * 5

    window.close()
