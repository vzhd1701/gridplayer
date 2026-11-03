from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_cell_size import CellSizeControl
from tests.conftest import mock_block_parts


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Block(QObject):
    """A video block as its cell size part sees one."""

    def __init__(self, *, is_under_cursor=False):
        super().__init__()
        self.video_id = "A"
        self.overlay = Mock()
        self.overlay.isVisible.return_value = True
        self.overlay.has_cell_size_buttons.return_value = True
        self.overlay.has_tile_buttons.return_value = False
        self._is_under_cursor = is_under_cursor
        self._ctx = SimpleNamespace(
            commands=SimpleNamespace(
                is_grid_cell_steppable=Mock(return_value=True),
                step_grid_cell=Mock(),
            )
        )

    def is_under_cursor(self):
        return self._is_under_cursor


def test_the_buttons_of_a_cell_away_from_the_pointer_wait_for_it():
    block = _Block()
    part = CellSizeControl(block)

    part.set_sizable(True, True, False)

    block.overlay.set_cell_size_controls.assert_called_once_with(
        True, True, False, True
    )
    block.overlay.set_cell_steps.assert_not_called()

    # the pointer come to it, its overlay shown
    part.sync_steps()
    part.sync_steps()
    block.overlay.set_cell_steps.assert_called_once_with(True, True)


def test_the_buttons_under_the_pointer_are_looked_at_once():
    block = _Block(is_under_cursor=True)
    part = CellSizeControl(block)

    part.set_sizable(True, False, False)
    part.sync_steps()

    block.overlay.set_cell_steps.assert_called_once_with(True, True)


def test_the_cell_whose_button_was_clicked_is_looked_at_once():
    block = _Block()
    part = CellSizeControl(block)
    # the grid laid out again as the step is made
    block._ctx.commands.step_grid_cell.side_effect = lambda *_args: part.set_sizable(
        True, True, False
    )

    part.step("bigger")

    block._ctx.commands.step_grid_cell.assert_called_once_with("bigger", "A")
    block.overlay.set_cell_steps.assert_called_once()
    assert not part._is_stepped


@pytest.mark.parametrize(
    "command", ["fill_tile_space", "fit_tile_to_video", "lock_tile"]
)
def test_a_tiles_button_asks_the_grid_and_shows_the_tile_as_it_is_now(command):
    block = _Block()
    block.overlay.has_cell_size_buttons.return_value = False
    block.overlay.has_tile_buttons.return_value = True
    commands = block._ctx.commands
    setattr(commands, command, Mock())
    commands.is_tile_space_fillable = Mock(return_value=True)
    commands.is_tile_fittable = Mock(return_value=False)
    commands.is_tile_locked = Mock(return_value=command == "lock_tile")
    part = CellSizeControl(block)

    part.tile(command)

    getattr(commands, command).assert_called_once_with("A")
    block.overlay.set_tile_states.assert_called_once_with(
        can_fill=True, can_fit=False, is_locked=command == "lock_tile"
    )


def test_a_video_of_another_shape_has_its_buttons_looked_at_again():
    # its tile may be its shape now, or no longer, with nothing laid out
    block = mock_block_parts(Mock(spec=VideoBlock))
    block.picture_shape = 16 / 9

    VideoBlock._picture_shape_changed(block, 4 / 3)

    assert block.picture_shape == 4 / 3
    block.cell_size.forget_steps.assert_called_once()

    VideoBlock._picture_shape_changed(block, 4 / 3)

    block.cell_size.forget_steps.assert_called_once()
