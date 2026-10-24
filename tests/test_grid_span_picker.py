from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.widgets.grid_span_picker import _EatenClick


class _Clicked(QWidget):
    def __init__(self):
        super().__init__()
        self.events = []

    def mousePressEvent(self, event):
        self.events.append("press")

    def mouseReleaseEvent(self, event):
        self.events.append("release")


def _send(widget, kind):
    QApplication.sendEvent(
        widget,
        QMouseEvent(kind, QPointF(1, 1), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier),
    )


def test_the_click_that_closed_the_picker_does_nothing_else():
    widget = _Clicked()

    _EatenClick()
    _send(widget, QEvent.MouseButtonPress)
    _send(widget, QEvent.MouseButtonRelease)
    QApplication.processEvents()

    assert widget.events == []

    # the next one goes through
    _send(widget, QEvent.MouseButtonPress)
    assert widget.events == ["press"]
