"""A window drawn with GL takes its new size before it is painted: Qt is asked
for it only when its widgets are behind the size the window has."""

import sys
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QEvent, QSize
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.utils import gl_window_size


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _filter(window_size):
    widget = QWidget()
    widget.resize(400, 300)

    flushes = []
    new_size_first = gl_window_size._NewSizeFirst(widget, flushes.append)

    window = MagicMock()
    window.size.return_value = QSize(*window_size)
    widget.windowHandle = lambda: window

    return widget, new_size_first, flushes


def test_a_paint_at_the_size_the_window_has_goes_ahead():
    widget, new_size_first, flushes = _filter((400, 300))

    new_size_first.eventFilter(widget, QEvent(QEvent.UpdateRequest))

    assert flushes == []


@pytest.mark.parametrize("kind", [QEvent.UpdateRequest, QEvent.Expose])
def test_a_paint_at_an_old_size_takes_the_new_one_first(kind):
    widget, new_size_first, flushes = _filter((400, 280))

    new_size_first.eventFilter(widget, QEvent(kind))

    assert flushes == [0x01]


def test_other_events_are_left_alone():
    widget, new_size_first, flushes = _filter((400, 280))

    new_size_first.eventFilter(widget, QEvent(QEvent.MouseMove))

    assert flushes == []


# GL output isn't offered on macOS
@pytest.mark.skipif(sys.platform == "darwin", reason="not on macOS")
def test_qt_can_be_asked_on_this_system():
    assert gl_window_size._qt_flush() is not None
