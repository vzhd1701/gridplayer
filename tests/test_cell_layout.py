import pytest
from PyQt5 import sip
from PyQt5.QtCore import QRect
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils.layout import FULL_BOX, CellLayout, grid_box
from gridplayer.utils.layout.cell_layout import GLIDE_MS


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


def _wait_there(layout):
    """Until the cells on their way are in their places."""

    for _ in range(100):
        if not layout.is_gliding():
            return
        QTest.qWait(GLIDE_MS // 4)
    raise AssertionError("still on their way")


def _two_cells(side_by_side=True):
    """Two cells on show in an area of 800 by 400, laid out; a place to
    turn them one over the other with."""

    area = QWidget()
    area.resize(800, 400)
    layout = CellLayout(area)
    one, two = QWidget(area), QWidget(area)
    places = {"is_side_by_side": side_by_side}

    def place(_width, _height):
        if places["is_side_by_side"]:
            return [(one, grid_box(0, 0, 1, 2)), (two, grid_box(0, 1, 1, 2))]
        return [(one, grid_box(0, 0, 2, 1)), (two, grid_box(1, 0, 2, 1))]

    layout.set_widgets([one, two])
    layout.set_place(place)
    area.show()
    layout.activate()
    return area, layout, one, two, places


def test_told_to_the_cells_slide_to_their_places():
    area, layout, one, two, places = _two_cells()
    assert two.geometry() == QRect(400, 0, 400, 400)

    places["is_side_by_side"] = False
    layout.glide()
    layout.activate()

    # on its way, not there yet
    assert layout.is_gliding()
    assert two.geometry() != QRect(0, 200, 800, 200)
    _wait_there(layout)
    assert one.geometry() == QRect(0, 0, 800, 200)
    assert two.geometry() == QRect(0, 200, 800, 200)
    area.close()


def test_slid_to_their_places_they_are_laid_out_again():
    area, layout, _one, two, places = _two_cells()
    places["is_side_by_side"] = False
    layout.glide()
    layout.activate()

    # what is laid out by the cells' places sees them there, once they are
    seen = []
    layout.laid_out.connect(lambda: seen.append(two.geometry()))
    _wait_there(layout)

    assert seen == [QRect(0, 200, 800, 200)]
    area.close()


def test_not_told_to_they_jump_there():
    area, layout, _one, two, places = _two_cells()

    places["is_side_by_side"] = False
    layout.invalidate()
    layout.activate()

    assert not layout.is_gliding()
    assert two.geometry() == QRect(0, 200, 800, 200)
    area.close()


def test_a_cell_held_still_does_not_slide():
    area, layout, one, two, places = _two_cells()

    places["is_side_by_side"] = False
    layout.glide([one])
    layout.activate()

    # where it goes at once, the other on its way
    assert one.geometry() == QRect(0, 0, 800, 200)
    assert two.geometry() != QRect(0, 200, 800, 200)
    _wait_there(layout)
    area.close()


def test_laid_out_again_a_cell_on_its_way_stays_on_it():
    area, layout, _one, two, places = _two_cells()
    places["is_side_by_side"] = False
    layout.glide()
    layout.activate()
    on_its_way = two.geometry()

    # the same place for it: not jumped there
    layout.invalidate()
    layout.activate()

    assert layout.is_gliding()
    assert two.geometry() == on_its_way
    _wait_there(layout)
    assert two.geometry() == QRect(0, 200, 800, 200)
    area.close()


def test_given_another_place_a_cell_on_its_way_jumps_there():
    area, layout, _one, two, places = _two_cells()
    places["is_side_by_side"] = False
    layout.glide()
    layout.activate()

    # back, not told to slide
    places["is_side_by_side"] = True
    layout.invalidate()
    layout.activate()

    assert not layout.is_gliding()
    assert two.geometry() == QRect(400, 0, 400, 400)
    area.close()


def test_a_cell_placed_no_more_stops_on_its_way():
    area, layout, one, two, places = _two_cells()
    places["is_side_by_side"] = False
    layout.glide()
    layout.activate()
    on_its_way = two.geometry()

    # only the other placed now, as in Single Mode
    layout.set_place(lambda _width, _height: [(one, grid_box(0, 0, 1, 1))])
    layout.activate()
    _wait_there(layout)

    assert two.geometry() == on_its_way
    area.close()


def test_a_hidden_cell_does_not_slide():
    area, layout, _one, two, places = _two_cells()
    two.hide()

    places["is_side_by_side"] = False
    layout.glide()
    layout.activate()

    assert two.geometry() == QRect(0, 200, 800, 200)
    area.close()
