import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.empty_cell import EmptyCell


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_empty_cell_paints_plus_without_message():
    cell = EmptyCell()
    cell.resize(200, 150)
    pixmap = cell.grab()
    assert pixmap.size() == cell.size()
    assert cell._message is None


def test_empty_cell_paints_message_instead_of_plus():
    cell = EmptyCell(message="Drag and drop media files or URLs here")
    cell.resize(640, 360)
    pixmap = cell.grab()
    assert pixmap.size() == cell.size()
    assert cell._message == "Drag and drop media files or URLs here"
    assert cell.is_empty_cell
