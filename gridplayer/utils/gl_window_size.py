"""A window drawn with GL: only drawn at the size it has, and put together
at most once a screen refresh.

As a window is resized, Qt takes each new size from a queue of its own, and a
paint can come first: one asked for before, or the one Qt makes at once when
the window shrinks on Windows. The whole window is then drawn at its old size
into the new one, and with GL that frame is shown as it is: the picture jumps
by the difference and back again with the next frame. Painting in software is
spared, as what was painted stays where it was.

So before Qt paints such a window while its widgets are still at an old size,
it takes the new size first, as it does itself before a paint the system asks
for. The window's own size is always the new one: Qt asks the system for it.

Not on X11, where Qt has the new size only once it has read the
ConfigureNotify, and the window's size is as old as its widgets'. A frame of
a video painted the window then, at its old size into the bigger buffer, which
GL fills from the bottom up: a black band over the top until the next. X11 is
asked itself (_X11Sizes), and such a paint waits until Qt has caught up.

With GL, Qt also puts all of the window together and swaps it for anything
painted anew in it, and a cell's controls are painted apart from its frames:
its time, its bar. Each swap waits for the screen, and two or more a refresh
held the GUI up and the videos with it, as soon as the controls were up. So
a paint asked for less than a refresh after the last waits for the next turn,
and goes with the frames due then. Painting for the system, as a resize does,
isn't asked for this way, and isn't held. Nor is what repaint_now paints: Qt's
repaint() asks the same way, and can't be told apart.
"""

import contextlib
import ctypes
import functools
import logging
import math
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from gridplayer.params import env
from gridplayer.utils.qt import paint_interval_s

# QWindowSystemInterface::flushWindowSystemEvents(QEventLoop::ProcessEventsFlags)
_FLUSH_WINDOWS = (
    "Qt6Gui.dll",
    (
        "?flushWindowSystemEvents@QWindowSystemInterface@@"
        "SA_NV?$QFlags@W4ProcessEventsFlag@QEventLoop@@@@@Z"
    ),
)
_FLUSH_LINUX = (
    "libQt6Gui.so.6",
    (
        "_ZN22QWindowSystemInterface23flushWindowSystemEvents"
        "E6QFlagsIN10QEventLoop17ProcessEventsFlagEE"
    ),
)
_EXCLUDE_USER_INPUT_EVENTS = 0x01

_PAINTS = frozenset((QEvent.Type.UpdateRequest, QEvent.Type.Expose))

# How long a paint waits for Qt to catch up with a size X11 has: then it goes
# ahead, should the two never agree
X11_CATCH_UP_MS = 100
X11_RETRY_MS = 1
# Qt's size and X11's at a fractional scale: one rounded, the other not
X11_ROUNDING_PX = 1

logger = logging.getLogger(__name__)


def _qt_gui_macos() -> str:
    """macOS: Qt's QtGui, the framework PyQt6's wheel carries, or one found by
    its name where Qt is the system's."""

    import PyQt6

    bundled = Path(PyQt6.__file__).parent / "Qt6/lib/QtGui.framework/Versions/A/QtGui"
    return str(bundled) if bundled.exists() else "QtGui"


@functools.cache
def _qt_flush():
    if env.IS_WINDOWS:
        library, name = _FLUSH_WINDOWS
    elif env.IS_MACOS:
        # the same C++ symbol as Linux's
        library, name = _qt_gui_macos(), _FLUSH_LINUX[1]
    else:
        library, name = _FLUSH_LINUX

    try:
        # loaded already, by PyQt6
        flush = getattr(ctypes.CDLL(library), name)
    except (OSError, AttributeError):
        logger.warning("Qt can't be asked for a window's new size first")
        return None

    # the flags are a QFlags, an int passed as one
    flush.argtypes = [ctypes.c_int]
    flush.restype = ctypes.c_bool
    return flush


class _XcbGeometryCookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint)]


class _XcbGeometryReply(ctypes.Structure):
    _fields_ = [
        ("response_type", ctypes.c_uint8),
        ("depth", ctypes.c_uint8),
        ("sequence", ctypes.c_uint16),
        ("length", ctypes.c_uint32),
        ("root", ctypes.c_uint32),
        ("x", ctypes.c_int16),
        ("y", ctypes.c_int16),
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
        ("border_width", ctypes.c_uint16),
        ("pad", ctypes.c_uint8 * 2),
    ]


class _X11Sizes:
    """A window's size as X11 has it now, asked over a connection of our own:
    Qt's isn't to be had from Python. A round trip, a tenth of a millisecond."""

    def __init__(self, xcb, libc, connection):
        self._xcb = xcb
        self._libc = libc
        self._connection = connection

    @classmethod
    def connect(cls) -> "_X11Sizes | None":
        try:
            # loaded already, by Qt's xcb platform
            xcb = ctypes.CDLL("libxcb.so.1")
            libc = ctypes.CDLL(None)
        except OSError:
            return None

        xcb.xcb_connect.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        xcb.xcb_connect.restype = ctypes.c_void_p
        xcb.xcb_connection_has_error.argtypes = [ctypes.c_void_p]
        xcb.xcb_connection_has_error.restype = ctypes.c_int
        xcb.xcb_get_geometry.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        xcb.xcb_get_geometry.restype = _XcbGeometryCookie
        xcb.xcb_get_geometry_reply.argtypes = [
            ctypes.c_void_p,
            _XcbGeometryCookie,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        xcb.xcb_get_geometry_reply.restype = ctypes.POINTER(_XcbGeometryReply)
        libc.free.argtypes = [ctypes.c_void_p]

        connection = xcb.xcb_connect(None, None)
        if not connection or xcb.xcb_connection_has_error(connection):
            logger.warning("X11 can't be asked for a window's size")
            return None

        return cls(xcb, libc, connection)

    def size(self, window_id: int) -> tuple[int, int] | None:
        cookie = self._xcb.xcb_get_geometry(self._connection, window_id)
        error = ctypes.c_void_p()
        reply = self._xcb.xcb_get_geometry_reply(
            self._connection, cookie, ctypes.byref(error)
        )

        if error:
            self._libc.free(error)

        if not reply:
            return None

        size = reply.contents.width, reply.contents.height
        self._libc.free(ctypes.cast(reply, ctypes.c_void_p))
        return size


@functools.cache
def _x11_sizes() -> _X11Sizes | None:
    return _X11Sizes.connect()


class _GLWindowPaints(QObject):
    def __init__(self, widget: QWidget, flush):
        super().__init__(widget)

        self._widget = widget
        self._flush = flush
        self._window = None

        # when the window was last put together, see _is_held
        self._last_paint = 0.0
        self._is_now = False
        self._held_paint = QTimer(self)
        self._held_paint.setSingleShot(True)
        self._held_paint.setTimerType(Qt.TimerType.PreciseTimer)
        self._held_paint.timeout.connect(self._paint_held)

        # see _is_x11_ahead
        self._x11 = _x11_sizes() if QGuiApplication.platformName() == "xcb" else None
        self._x11_waiting_since = None
        self._x11_given_up = None

        widget.installEventFilter(self)
        self._follow_window()

    def eventFilter(self, watched, event):
        kind = event.type()

        # Qt's own paint when the window shrinks reaches the window, not the
        # widget; one made anew is followed
        if watched is self._widget and kind == QEvent.Type.WinIdChange:
            self._follow_window()

        # what Qt asks of the widget, not what the system asks of the window
        if (
            watched is self._widget
            and kind == QEvent.Type.UpdateRequest
            and not self._is_now
            and self._is_held()
        ):
            return True

        if kind in _PAINTS and self._flush is not None and self._is_behind():
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

    def _is_held(self) -> bool:
        """Less than a refresh since the last paint, or X11 ahead of Qt: this
        one is held till then. X11 is asked only of a paint due."""

        # not monotonic(): on Windows before Python 3.13, 15.6 ms steps
        now = time.perf_counter()
        wait_s = self._last_paint + paint_interval_s(self._widget.screen()) - now

        if wait_s > 0:
            self._hold(math.ceil(wait_s * 1000))
            return True

        if self._is_x11_ahead(now):
            self._hold(X11_RETRY_MS)
            return True

        self._last_paint = now
        return False

    def _hold(self, wait_ms: int) -> None:
        if not self._held_paint.isActive():
            self._held_paint.start(wait_ms)

    def _is_x11_ahead(self, now: float) -> bool:
        """X11 has the window at a size Qt hasn't taken yet, or Qt at one X11
        hasn't: the paint waits, for X11_CATCH_UP_MS at most. A size given up
        on isn't waited for again."""

        if self._x11 is None:
            return False

        x11_size = self._x11.size(int(self._widget.winId()))

        if (
            x11_size is None
            or x11_size == self._x11_given_up
            or self._is_qt_at(x11_size)
        ):
            self._x11_waiting_since = None
            return False

        if self._x11_waiting_since is None:
            self._x11_waiting_since = now
        elif now - self._x11_waiting_since > X11_CATCH_UP_MS / 1000:
            # never caught up with: the size as it is from now on
            self._x11_waiting_since = None
            self._x11_given_up = x11_size
            return False

        return True

    def _is_qt_at(self, x11_size: tuple[int, int]) -> bool:
        ratio = self._widget.devicePixelRatioF()
        own_size = (self._widget.width() * ratio, self._widget.height() * ratio)

        return all(
            abs(x11 - own) <= X11_ROUNDING_PX for x11, own in zip(x11_size, own_size)
        )

    @contextlib.contextmanager
    def now(self):
        self._is_now = True
        try:
            yield
        finally:
            self._is_now = False

    def _paint_held(self) -> None:
        # Qt asks for no other until this one is done. PyQt6 takes the
        # priority as an int only.
        QCoreApplication.postEvent(
            self._widget,
            QEvent(QEvent.Type.UpdateRequest),
            Qt.EventPriority.LowEventPriority.value,
        )


def set_up_gl_window(widget: QWidget) -> None:
    """This window, drawn with GL from now on: see above. Set up once."""

    if getattr(widget, "_gl_window_paints", None) is None:
        widget._gl_window_paints = _GLWindowPaints(widget, _qt_flush())


def repaint_now(widget: QWidget) -> None:
    """widget.repaint(), painted now in a window drawn with GL as well: what
    is painted before something that holds the GUI up."""

    paints = getattr(widget.window(), "_gl_window_paints", None)

    if not isinstance(paints, _GLWindowPaints):
        widget.repaint()
        return

    with paints.now():
        widget.repaint()
