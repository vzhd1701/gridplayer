import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.widgets.cell_chrome import (
    idle_disc_rect,
    paint_dashed_outline,
    paint_idle_disc,
    paint_solid_outline,
)
from gridplayer.widgets.empty_cell import EmptyCell


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_paint_dashed_outline_on_widget():
    widget = QWidget()
    widget.resize(200, 150)
    paint_dashed_outline(widget)
    pixmap = widget.grab()
    assert pixmap.size() == widget.size()


def test_paint_solid_outline_on_widget():
    widget = QWidget()
    widget.resize(200, 150)
    paint_solid_outline(widget)
    pixmap = widget.grab()
    assert pixmap.size() == widget.size()


def test_paint_idle_disc_on_widget():
    widget = QWidget()
    widget.resize(200, 150)
    paint_idle_disc(widget)
    pixmap = widget.grab()
    assert pixmap.size() == widget.size()
    disc = idle_disc_rect(widget)
    assert disc.width() == pytest.approx(min(200, 150) * 0.6)
    assert disc.center().x() == pytest.approx(100)
    assert disc.center().y() == pytest.approx(75)


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


def test_empty_cell_message_hidden_when_too_small():
    holder = QWidget()
    cell = EmptyCell(message="Drag and drop media files or URLs here", parent=holder)
    holder.show()

    cell.resize(640, 360)
    assert cell._message_label.isVisibleTo(cell)

    cell.resize(400, 199)
    assert not cell._message_label.isVisibleTo(cell)

    cell.resize(199, 400)
    assert not cell._message_label.isVisibleTo(cell)

    cell.resize(250, 250)
    assert cell._message_label.isVisibleTo(cell)

    cell.resize(200, 200)
    assert not cell._message_label.isVisibleTo(cell)


def test_empty_cell_drop_indicator_hides_message():
    cell = EmptyCell(message="Drag and drop media files or URLs here")
    cell.resize(640, 360)
    assert cell._message_label.isVisibleTo(cell)

    cell.set_drop_indicator(DropIndicator.DOT)
    assert not cell._message_label.isVisibleTo(cell)

    cell.set_drop_indicator(DropIndicator.NONE)
    assert cell._message_label.isVisibleTo(cell)


def test_empty_cell_minimum_size_hint_is_zero():
    cell = EmptyCell(message="Drag and drop media files or URLs here")
    assert cell.minimumSizeHint() == QSize(0, 0)
