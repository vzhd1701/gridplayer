"""A window drawn with GL takes its new size before it is painted: Qt is asked
for it only when its widgets are behind the size the window has. And it is put
together at most once a screen refresh: a paint asked for sooner waits."""

import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEvent, QObject, QSize
from PyQt6.QtWidgets import QApplication, QWidget

from gridplayer.utils import gl_window_size


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _filter(window_size):
    widget = QWidget()
    widget.resize(400, 300)

    flushes = []
    new_size_first = gl_window_size._GLWindowPaints(widget, flushes.append)

    window = MagicMock()
    window.size.return_value = QSize(*window_size)
    widget.windowHandle = lambda: window

    return widget, new_size_first, flushes


def test_a_paint_at_the_size_the_window_has_goes_ahead():
    widget, new_size_first, flushes = _filter((400, 300))

    new_size_first.eventFilter(widget, QEvent(QEvent.Type.UpdateRequest))

    assert flushes == []


@pytest.mark.parametrize("kind", [QEvent.Type.UpdateRequest, QEvent.Type.Expose])
def test_a_paint_at_an_old_size_takes_the_new_one_first(kind):
    widget, new_size_first, flushes = _filter((400, 280))

    new_size_first.eventFilter(widget, QEvent(kind))

    assert flushes == [0x01]


def test_other_events_are_left_alone():
    widget, new_size_first, flushes = _filter((400, 280))

    new_size_first.eventFilter(widget, QEvent(QEvent.Type.MouseMove))

    assert flushes == []


def test_the_window_is_put_together_at_most_once_a_refresh(monkeypatch):
    widget, paints, _ = _filter((400, 300))
    monkeypatch.setattr(gl_window_size, "paint_interval_s", lambda _s: 0.016)
    now = [100.0]
    monkeypatch.setattr(gl_window_size.time, "perf_counter", lambda: now[0])
    request = QEvent(QEvent.Type.UpdateRequest)

    assert not paints.eventFilter(widget, request)

    now[0] += 0.005
    assert paints.eventFilter(widget, request)
    assert paints._held_paint.isActive()

    now[0] += 0.012
    assert not paints.eventFilter(widget, request)
    paints._held_paint.stop()


def test_a_held_paint_is_asked_for_once_its_time_comes():
    widget, paints, _ = _filter((400, 300))
    seen = []

    class _Seen(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.UpdateRequest:
                seen.append(watched)
            return False

    # the last filter installed hears it first
    seen_filter = _Seen()
    widget.installEventFilter(seen_filter)

    paints._paint_held()
    QApplication.sendPostedEvents(widget, QEvent.Type.UpdateRequest)

    assert seen == [widget]


def test_what_the_system_asks_for_is_never_held(monkeypatch):
    widget, paints, _ = _filter((400, 300))
    monkeypatch.setattr(gl_window_size.time, "perf_counter", lambda: 100.0)
    paints.eventFilter(widget, QEvent(QEvent.Type.UpdateRequest))

    assert not paints.eventFilter(widget.windowHandle(), QEvent(QEvent.Type.Expose))


# GL output isn't offered on macOS
@pytest.mark.skipif(sys.platform == "darwin", reason="not on macOS")
def test_qt_can_be_asked_on_this_system():
    assert gl_window_size._qt_flush() is not None


def test_what_is_painted_now_is_never_held(monkeypatch):
    widget, paints, _ = _filter((400, 300))
    widget._gl_window_paints = paints
    monkeypatch.setattr(gl_window_size.time, "perf_counter", lambda: 100.0)
    paints.eventFilter(widget, QEvent(QEvent.Type.UpdateRequest))
    held = []
    monkeypatch.setattr(
        widget,
        "repaint",
        lambda: held.append(
            paints.eventFilter(widget, QEvent(QEvent.Type.UpdateRequest))
        ),
    )

    gl_window_size.repaint_now(widget)

    assert held == [False]
    paints._held_paint.stop()


class _FakeX11:
    """X11's size of the window, as the test says it is."""

    def __init__(self, size):
        self.now = size
        self.asked = 0

    def size(self, _window_id):
        self.asked += 1
        return self.now


def _x11_filter(monkeypatch, x11_size):
    """Qt's widgets at 400x300, X11's window at x11_size."""

    widget, paints, _ = _filter((400, 300))
    monkeypatch.setattr(gl_window_size.time, "perf_counter", lambda: 100.0)
    monkeypatch.setattr(widget, "devicePixelRatioF", lambda: 1.0)
    x11 = _FakeX11(x11_size)
    paints._x11 = x11
    return widget, paints, x11


def _is_held(widget, paints):
    held = paints.eventFilter(widget, QEvent(QEvent.Type.UpdateRequest))
    paints._held_paint.stop()
    return held


def test_a_paint_waits_while_x11_has_a_size_qt_has_not_taken(monkeypatch):
    # by X11's, the window has grown; Qt's widgets are still 400x300
    widget, paints, _ = _x11_filter(monkeypatch, (520, 510))

    assert _is_held(widget, paints)

    # Qt has taken it
    widget.resize(520, 510)

    assert not _is_held(widget, paints)


def test_a_drag_ahead_of_qt_is_waited_for_at_each_step(monkeypatch):
    widget, paints, x11 = _x11_filter(monkeypatch, (520, 510))
    widget.resize(520, 510)
    # Qt takes one size of a drag while X11 is at the next already
    x11.now = (540, 520)
    paints.eventFilter(widget, QEvent(QEvent.Type.Resize))

    assert _is_held(widget, paints)


def test_a_size_qt_asked_for_waits_for_x11_to_take_it(monkeypatch):
    # Qt resized its widgets to 400x300, X11's window is at the old size
    widget, paints, x11 = _x11_filter(monkeypatch, (500, 500))

    assert _is_held(widget, paints)

    x11.now = (400, 300)

    assert not _is_held(widget, paints)


def test_a_size_rounded_apart_at_a_fractional_scale_is_the_same(monkeypatch):
    widget, paints, _ = _x11_filter(monkeypatch, (401, 299))

    assert not _is_held(widget, paints)


def test_a_paint_waits_for_x11_only_so_long(monkeypatch):
    widget, paints, _ = _x11_filter(monkeypatch, (520, 510))
    now = [100.0]
    monkeypatch.setattr(gl_window_size.time, "perf_counter", lambda: now[0])

    assert _is_held(widget, paints)

    now[0] += gl_window_size.X11_CATCH_UP_MS / 1000 + 0.001
    # a refresh since the last paint too: nothing else holds it
    assert not _is_held(widget, paints)

    # nor that size again, a refresh later
    now[0] += 0.1
    assert not _is_held(widget, paints)


def test_a_paint_held_for_the_refresh_asks_nothing_of_x11(monkeypatch):
    widget, paints, x11 = _x11_filter(monkeypatch, (400, 300))
    monkeypatch.setattr(gl_window_size, "paint_interval_s", lambda _s: 0.016)

    assert not _is_held(widget, paints)
    asked = x11.asked

    # the same moment: less than a refresh since
    assert _is_held(widget, paints)
    assert x11.asked == asked
