from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.video_block_cell_size import CellSizeControl


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
        self._is_under_cursor = is_under_cursor
        self._ctx = SimpleNamespace(
            commands=SimpleNamespace(
                is_grid_cell_steppable=Mock(return_value=True),
                step_grid_cell=Mock(),
            )
        )

    def is_under_cursor(self):
        return self._is_under_cursor


def test_the_buttons_of_a_cell_away_from_the_pointer_wait_for_the_grid():
    block = _Block()
    part = CellSizeControl(block)

    part.set_sizable(True, True)

    block.overlay.set_cell_size_controls.assert_called_once_with(True, True)
    block.overlay.set_cell_steps.assert_not_called()
    assert part._steps_timer.isActive()


def test_the_buttons_under_the_pointer_are_looked_at_once():
    block = _Block(is_under_cursor=True)
    part = CellSizeControl(block)

    part.set_sizable(True, False)
    part.sync_steps()

    block.overlay.set_cell_steps.assert_called_once_with(True, True)
    assert not part._steps_timer.isActive()


def test_the_cell_whose_button_was_clicked_is_looked_at_once():
    block = _Block()
    part = CellSizeControl(block)
    # the grid laid out again as the step is made
    block._ctx.commands.step_grid_cell.side_effect = lambda *_args: part.set_sizable(
        True, True
    )

    part.step("bigger")

    block._ctx.commands.step_grid_cell.assert_called_once_with("bigger", "A")
    block.overlay.set_cell_steps.assert_called_once()
    assert not part._is_stepped
