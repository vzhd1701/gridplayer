import pytest
from PyQt5 import sip
from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils.layout import FULL_BOX, CellLayout, grid_box


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("size", [(1000, 600), (1001, 601), (997, 13)])
def test_cells_meet_with_no_gap(size):
    area = QWidget()
    layout = CellLayout(area)
    widgets = [QWidget(area) for _ in range(9)]
    cells = [(w, grid_box(n // 3, n % 3, 3, 3)) for n, w in enumerate(widgets)]
    layout.set_widgets(widgets)
    layout.set_place(lambda _width, _height: cells)

    layout.setGeometry(QRect(0, 0, *size))

    rows = [widgets[n : n + 3] for n in (0, 3, 6)]
    for row in rows:
        assert row[0].x() == 0
        assert [a.geometry().right() + 1 for a in row[:-1]] == [b.x() for b in row[1:]]
        assert row[-1].geometry().right() + 1 == size[0]
    assert rows[-1][0].geometry().bottom() + 1 == size[1]


def test_hidden_cell_is_placed_before_it_is_shown():
    area = QWidget()
    area.resize(800, 400)
    layout = CellLayout(area)
    shown, hidden = QWidget(area), QWidget(area)
    hidden.hide()
    cells = [(shown, grid_box(0, 0, 1, 2)), (hidden, grid_box(0, 1, 1, 2))]
    layout.set_widgets([shown, hidden])
    layout.set_place(lambda _width, _height: cells)

    layout.activate()

    assert hidden.isHidden()
    assert hidden.geometry() == QRect(400, 0, 400, 400)


def test_place_is_asked_with_the_area_size():
    area = QWidget()
    layout = CellLayout(area)
    widget = QWidget(area)
    asked = []

    def place(width, height):
        asked.append((width, height))
        return [(widget, FULL_BOX)]

    layout.set_widgets([widget])
    layout.set_place(place)
    layout.setGeometry(QRect(10, 20, 300, 200))

    assert asked == [(300, 200)]
    assert widget.geometry() == QRect(10, 20, 300, 200)


def test_deleted_widget_is_skipped():
    area = QWidget()
    layout = CellLayout(area)
    gone, kept = QWidget(area), QWidget(area)
    cells = [(gone, grid_box(0, 0, 1, 2)), (kept, grid_box(0, 1, 1, 2))]
    layout.set_widgets([gone, kept])
    layout.set_place(lambda _width, _height: cells)

    sip.delete(gone)
    layout.setGeometry(QRect(0, 0, 200, 100))

    assert layout.count() == 1
    assert kept.geometry() == QRect(100, 0, 100, 100)
