"""A window drawn with GL is only drawn at the size it has.

As a window is resized, Qt takes each new size from a queue of its own, and a
paint can come first: one asked for before, or the one Qt makes at once when
the window shrinks on Windows. The whole window is then drawn at its old size
into the new one, and with GL that frame is shown as it is: the picture jumps
by the difference and back again with the next frame. Painting in software is
spared, as what was painted stays where it was.

So before Qt paints such a window while its widgets are still at an old size,
it takes the new size first, as it does itself before a paint the system asks
for. The window's own size is always the new one: Qt asks the system for it.
"""

import ctypes
import functools
import logging

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QWidget

from gridplayer.params import env

# QWindowSystemInterface::flushWindowSystemEvents(QEventLoop::ProcessEventsFlags)
_FLUSH_WINDOWS = (
    "Qt5Gui.dll",
    (
        "?flushWindowSystemEvents@QWindowSystemInterface@@"
        "SA_NV?$QFlags@W4ProcessEventsFlag@QEventLoop@@@@@Z"
    ),
)
_FLUSH_LINUX = (
    "libQt5Gui.so.5",
    (
        "_ZN22QWindowSystemInterface23flushWindowSystemEvents"
        "E6QFlagsIN10QEventLoop17ProcessEventsFlagEE"
    ),
)
_EXCLUDE_USER_INPUT_EVENTS = 0x01

_PAINTS = frozenset((QEvent.UpdateRequest, QEvent.Expose))

logger = logging.getLogger(__name__)


@functools.cache
def _qt_flush():
    library, name = _FLUSH_WINDOWS if env.IS_WINDOWS else _FLUSH_LINUX

    try:
        # loaded already, by PyQt5
        flush = getattr(ctypes.CDLL(library), name)
    except (OSError, AttributeError):
        logger.warning("Qt can't be asked for a window's new size first")
        return None

    # the flags are a QFlags, an int passed as one
    flush.argtypes = [ctypes.c_int]
    flush.restype = ctypes.c_bool
    return flush


class _NewSizeFirst(QObject):
    def __init__(self, widget: QWidget, flush):
        super().__init__(widget)

        self._widget = widget
        self._flush = flush
        self._window = None

        widget.installEventFilter(self)
        self._follow_window()

    def eventFilter(self, watched, event):
        kind = event.type()

        # Qt's own paint when the window shrinks reaches the window, not the
        # widget; one made anew is followed
        if watched is self._widget and kind == QEvent.WinIdChange:
            self._follow_window()

        if kind in _PAINTS and self._is_behind():
            self._flush(_EXCLUDE_USER_INPUT_EVENTS)

        return False

    def _follow_window(self) -> None:
        window = self._widget.windowHandle()
        if window is not None and window is not self._window:
            window.installEventFilter(self)
            self._window = window

    def _is_behind(self) -> bool:
        window = self._widget.windowHandle()

        return window is not None and window.size() != self._widget.size()


def draw_at_window_size(widget: QWidget) -> None:
    """This window, drawn with GL, drawn only at the size it has. Asked for by
    each GL surface in it, set up by the first."""

    if getattr(widget, "_new_size_first", None) is not None:
        return

    flush = _qt_flush()
    if flush is None:
        return

    widget._new_size_first = _NewSizeFirst(widget, flush)
