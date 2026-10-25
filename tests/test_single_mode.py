from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.grid_state import GridState
from gridplayer.params.static import GridMode, StripMode, StripSide
from gridplayer.player.managers.grid import GridManager
from gridplayer.player.managers.single_mode import SingleModeManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.layout.boxes import Weights
from gridplayer.utils.layout.strip import strip_weights


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
    vb.video_id = block_id
    vb.video_params.is_paused = is_paused
    vb.is_stopped = is_stopped
    return vb


def _manager(mocker, blocks, active, pause_background=True):
    ctx = SimpleNamespace(
        is_single_mode=False,
        is_pause_background_videos=pause_background,
        active_block=active,
        video_blocks=_Cells(blocks),
        commands=SimpleNamespace(
            grid_cell_count=lambda: len(blocks),
            layout_order=lambda: [vb.video_id for vb in blocks],
        ),
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

    picture_shape = None

    def __init__(self, video_id, parent):
        super().__init__(parent)
        self.id = video_id
        self.video_id = video_id
        self.sizes = []
        # its overlay's buttons that size its cell, none here
        self.cell_size = SimpleNamespace(set_sizable=lambda *_args: None)

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
    window, cells, _ctx, _grid, single_mode = _grid_and_single_mode(
        single, grid_state, is_pause_background=False
    )
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


def _grid_and_single_mode(single, grid_state, *, is_pause_background):
    # six videos in a wide window
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
    ctx.is_pause_background_videos = is_pause_background
    ctx.commands = SimpleNamespace(
        grid_cell_count=lambda: grid.grid_dimensions.max_size,
        remove_video_blocks=lambda *_a: None,
        single_mode_video=single_mode.single_mode_video,
        update_active_under_mouse=lambda: None,
        strip_videos=single_mode.strip_videos,
        layout_order=lambda: grid._layout.order(),
    )
    grid.layout_changed.connect(grid.reload_video_grid)
    single_mode.mode_changed.connect(grid.on_single_mode_changed)

    grid.set_grid_state(grid_state)
    window.show()
    QApplication.processEvents()
    return window, cells, ctx, grid, single_mode


def _strip_grid(single=0, mode=StripMode.SWAP):
    # six videos in a wide window, the strip on
    PlaylistSettings().set("playlist/single_mode_strip", mode)
    return _grid_and_single_mode(
        single, GridState(mode=GridMode.AUTO_ROWS, size=0), is_pause_background=True
    )


def test_the_strip_shows_the_others_small_beside_the_big_one():
    window, cells, _ctx, _grid, single_mode = _strip_grid(single=2)

    single_mode.single_mode_on()
    QApplication.processEvents()

    assert all(c.isVisible() for c in cells)
    big = cells[2].geometry()
    assert big.left() == 0
    assert big.height() == window.height()
    for cell in cells[:2] + cells[3:]:
        assert cell.geometry().left() >= big.right()
        assert cell.width() < big.width() / 2
    window.close()


def test_a_double_click_shows_one_of_the_strip_big():
    window, cells, ctx, _grid, single_mode = _strip_grid()
    single_mode.single_mode_on()

    # the one in the strip clicked on twice
    ctx.active_block = cells[3]
    assert not single_mode.is_single_video_big()
    single_mode.toggle_single_video()
    QApplication.processEvents()

    assert ctx.is_single_mode
    assert single_mode.single_mode_video() is cells[3]
    assert cells[3].geometry().left() == 0
    assert cells[0].geometry().left() > 0

    # and twice on the big one, out of Single Mode
    single_mode.toggle_single_video()
    assert not ctx.is_single_mode
    window.close()


def test_next_video_takes_the_big_place_and_the_strip_keeps_playing(mocker):
    window, cells, _ctx, _grid, single_mode = _strip_grid()
    for cell in cells:
        cell.video_params = SimpleNamespace(is_paused=False)
        cell.set_pause = mocker.Mock()

    single_mode.single_mode_on()
    single_mode.next_single_video()
    QApplication.processEvents()

    assert single_mode.single_mode_video() is cells[1]
    assert cells[1].geometry().left() == 0
    # pause background videos is on, but none is out of sight
    for cell in cells:
        cell.set_pause.assert_not_called()

    # the strip off: the others out of sight, paused
    single_mode.choose_strip(StripMode.OFF)
    QApplication.processEvents()
    assert [c.isVisible() for c in cells] == [False, True, False, False, False, False]
    cells[0].set_pause.assert_called_once_with(True)
    window.close()


def test_with_mixed_shapes_the_strip_stays_as_it_is_through_a_swap():
    window, cells, ctx, _grid, single_mode = _strip_grid()
    for cell, shape in zip(cells, (16 / 9, 9 / 16, 4 / 3, 9 / 16, 21 / 9, 1.0)):
        cell.picture_shape = shape
    single_mode.single_mode_on()
    QApplication.processEvents()
    before = {cell.video_id: cell.geometry() for cell in cells}

    # one of the strip shown big
    ctx.active_block = cells[3]
    single_mode.toggle_single_video()
    QApplication.processEvents()

    after = {cell.video_id: cell.geometry() for cell in cells}
    # the two trade places, the rest of the strip where it was
    assert after["v3"] == before["v0"]
    assert after["v0"] == before["v3"]
    for video_id in ("v1", "v2", "v4", "v5"):
        assert after[video_id] == before[video_id]

    # and back by Next Video in the grid's order: v4 from its own tile
    single_mode.next_single_video()
    QApplication.processEvents()
    again = {cell.video_id: cell.geometry() for cell in cells}
    assert again["v4"] == before["v0"]
    assert again["v3"] == before["v4"]
    window.close()


def _tiles(cells, grid):
    # where each video is, and the big one's place held
    held = grid._held_place
    return {cell.video_id: cell.geometry() for cell in cells}, (
        held.geometry() if held.isVisible() else None,
        held.video_block,
    )


def test_the_fixed_strip_keeps_every_video_in_its_place():
    window, cells, ctx, grid, single_mode = _strip_grid(mode=StripMode.FIXED)
    single_mode.single_mode_on()
    QApplication.processEvents()
    before, (held, held_video) = _tiles(cells, grid)

    # the big one's place held in the strip, first in the grid's order
    big = before["v0"]
    assert big.left() == 0
    assert held_video is cells[0]
    assert held.left() > big.right()
    strip = [held] + [before[f"v{n}"] for n in range(1, 6)]
    assert len({(r.left(), r.top()) for r in strip}) == 6
    assert all(r.width() == held.width() for r in strip)
    # pointing at it is pointing at the big one
    centre = window.mapToGlobal(held.center())
    assert grid.strip_held_video_at(centre) is cells[0]

    # one of the strip shown big: only the big one and the held place move
    ctx.active_block = cells[3]
    single_mode.toggle_single_video()
    QApplication.processEvents()
    after, (held_after, held_video) = _tiles(cells, grid)

    assert after["v3"] == big
    assert held_video is cells[3]
    assert held_after == before["v3"]
    assert after["v0"] == held
    for video_id in ("v1", "v2", "v4", "v5"):
        assert after[video_id] == before[video_id]

    # Next Video walks the strip in its order
    single_mode.next_single_video()
    QApplication.processEvents()
    again, (held_again, held_video) = _tiles(cells, grid)
    assert held_video is cells[4]
    assert held_again == before["v4"]
    assert again["v3"] == before["v3"]
    window.close()


def test_the_strip_mode_menu_switches_between_the_strips_and_off():
    window, cells, ctx, grid, single_mode = _strip_grid()
    ctx.is_pause_background_videos = False
    single_mode.single_mode_on()
    QApplication.processEvents()
    assert not grid._held_place.isVisible()

    single_mode.choose_strip(StripMode.FIXED)
    QApplication.processEvents()
    assert single_mode.strip_mode() == StripMode.FIXED
    assert grid._held_place.isVisible()
    assert all(c.isVisible() for c in cells)

    single_mode.choose_strip(StripMode.SWAP)
    QApplication.processEvents()
    assert single_mode.strip_mode() == StripMode.SWAP
    assert not grid._held_place.isVisible()

    # the one that is on, picked again: still on
    single_mode.choose_strip(StripMode.SWAP)
    QApplication.processEvents()
    assert single_mode.strip_mode() == StripMode.SWAP

    single_mode.choose_strip(StripMode.OFF)
    QApplication.processEvents()
    assert single_mode.strip_mode() == StripMode.OFF
    assert [c.isVisible() for c in cells] == [True] + [False] * 5

    single_mode.choose_strip(StripMode.FIXED)
    single_mode.single_mode_off()
    QApplication.processEvents()
    assert not grid._held_place.isVisible()
    assert all(c.isVisible() for c in cells)
    window.close()


def test_the_strip_side_menu_moves_the_strip():
    window, cells, _ctx, _grid, single_mode = _strip_grid()
    single_mode.single_mode_on()
    QApplication.processEvents()
    assert cells[0].geometry().left() == 0

    single_mode.choose_strip_side(StripSide.LEFT)
    QApplication.processEvents()
    assert cells[0].geometry().right() == window.width() - 1
    for cell in cells[1:]:
        assert cell.geometry().right() < cells[0].geometry().left()

    single_mode.choose_strip_side(StripSide.TOP)
    QApplication.processEvents()
    assert cells[0].geometry().bottom() == window.height() - 1
    for cell in cells[1:]:
        assert cell.geometry().bottom() < cells[0].geometry().top()
    window.close()


def test_with_no_video_under_the_pointer_single_mode_is_left():
    # a gap at the end of the strip
    window, _cells, ctx, _grid, single_mode = _strip_grid()
    single_mode.single_mode_on()
    ctx.active_block = None

    single_mode.toggle_single_video()

    assert not ctx.is_single_mode
    window.close()


def test_a_closed_big_video_is_not_laid_out():
    window, cells, ctx, _grid, single_mode = _strip_grid(mode=StripMode.FIXED)
    single_mode.single_mode_on()
    assert single_mode.strip_videos() is not None

    ctx.video_blocks._cells.remove(cells[0])
    assert single_mode.strip_videos() is None
    window.close()


def test_undo_goes_past_a_step_that_changes_nothing_in_sight():
    window, _cells, _ctx, grid, single_mode = _strip_grid()
    grid.set_grid_state(GridState(mode=GridMode.FIXED, rows=2, cols=3))
    QApplication.processEvents()

    # the grid's lines moved, then the strip's edge in Single Mode
    grid.begin_grid_change()
    grid.set_grid_weights(Weights(cols=(2, 1, 1)))
    grid.end_grid_change()
    single_mode.single_mode_on()
    grid.begin_grid_change()
    grid.set_grid_weights(strip_weights(0.3))
    grid.end_grid_change()
    single_mode.single_mode_off()
    QApplication.processEvents()

    # back in the grid, one undo takes the grid's lines back
    grid.cmd_undo_grid()
    assert grid.grid_state().col_weights == []
    assert grid.grid_state().strip_share is None
    window.close()
