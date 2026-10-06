import pytest
from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWidgets import QApplication, QComboBox, QSpinBox, QVBoxLayout, QWidget

from gridplayer.widgets.settings_page_scroll_area import PageScrollArea


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _wheel_down(widget):
    pos = QPointF(widget.rect().center())
    event = QWheelEvent(
        pos,
        QPointF(widget.mapToGlobal(pos.toPoint())),
        QPoint(),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


@pytest.fixture
def page():
    form = QWidget()
    layout = QVBoxLayout(form)
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    spin = QSpinBox()
    layout.addWidget(combo)
    layout.addWidget(spin)
    for _ in range(30):
        layout.addWidget(QSpinBox())

    scroll = PageScrollArea()
    scroll.setWidget(form)
    scroll.setAttribute(Qt.WA_DontShowOnScreen)
    scroll.resize(200, 150)
    scroll.show()
    QApplication.processEvents()

    yield scroll, combo, spin

    scroll.close()


def test_wheel_over_unfocused_field_scrolls_the_page(page):
    scroll, combo, spin = page
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0

    _wheel_down(combo)
    assert combo.currentIndex() == 0
    assert bar.value() > 0

    scrolled = bar.value()
    _wheel_down(spin)
    assert spin.value() == 0
    assert bar.value() > scrolled


def test_wheel_does_not_give_fields_focus(page):
    _, combo, spin = page

    assert combo.focusPolicy() == Qt.StrongFocus
    assert spin.focusPolicy() == Qt.StrongFocus


def test_wheel_at_the_end_of_the_page_is_dropped(page):
    scroll, combo, _ = page
    bar = scroll.verticalScrollBar()
    bar.setValue(bar.maximum())

    _wheel_down(combo)
    assert combo.currentIndex() == 0
    assert bar.value() == bar.maximum()


def test_focused_field_takes_the_wheel(page):
    scroll, combo, _ = page
    # a window kept off the screen is never active, so focus can't be given
    combo.hasFocus = lambda: True

    _wheel_down(combo)
    assert combo.currentIndex() == 1
    assert scroll.verticalScrollBar().value() == 0
