import logging
import os

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

_GNOME_INTERFACE = "org.gnome.desktop.interface"


def follow_desktop_cursor() -> None:
    """Draw the cursor from the theme the desktop uses.

    On Wayland the client draws its own cursor, and Qt takes the theme
    from XCURSOR_THEME and XCURSOR_SIZE, falling back to "default" when
    unset -- on Ubuntu, the white DMZ theme. GNOME keeps its cursor in
    its own settings and exports neither, so they are read off the
    desktop portal, which also answers from inside a Flatpak.

    Qt reads the variables once, the first time a window sets a cursor,
    so this has to run before anything is shown. Ones already set, by
    the session (KDE, sway) or by hand, are left as they are.
    """

    if QGuiApplication.platformName() != "wayland":
        return

    from gridplayer.utils.darkmode_linux import portal_read

    if not os.environ.get("XCURSOR_THEME"):
        theme = portal_read(_GNOME_INTERFACE, "cursor-theme")
        if isinstance(theme, str) and theme:
            os.environ["XCURSOR_THEME"] = theme

    if not os.environ.get("XCURSOR_SIZE"):
        size = portal_read(_GNOME_INTERFACE, "cursor-size")
        if isinstance(size, int) and size > 0:
            os.environ["XCURSOR_SIZE"] = str(size)

    logging.getLogger(__name__).debug(
        "Wayland cursor: theme=%s size=%s",
        os.environ.get("XCURSOR_THEME"),
        os.environ.get("XCURSOR_SIZE"),
    )


class _HeaderLine(QWidget):
    """A line in the theme's border colour along the top of a window's
    content. On GNOME, Qt 6 draws the window's header with its own colours
    (the adwaita plugin's, after GNOME's light or dark, not the app's) and
    puts no line between the header and the content."""

    def __init__(self, window: QWidget):
        super().__init__(window)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def paintEvent(self, event):
        from gridplayer.params.theme import current_colors

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(current_colors()["border"]))


class _HeaderLines(QObject):
    """Gives each window with a header Qt draws a line under it, kept over
    the window's other children."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # The header is there only once the window is on screen: looked at
        # when the events of the moment are through, once however many came.
        # By address, found again among the windows there are then: one Qt
        # made itself (a combo box's list) may be gone by then, which its
        # Python wrapper can't tell.
        self._due: set[int] = set()
        self._place = QTimer(self)
        self._place.setSingleShot(True)
        self._place.setInterval(0)
        self._place.timeout.connect(self._place_due)

    def _place_due(self):
        due, self._due = self._due, set()
        for window in QApplication.topLevelWidgets():
            if sip.unwrapinstance(window) in due:
                _place_header_line(window)

    def eventFilter(self, watched, event):
        kind = event.type()

        if kind in _WINDOW_CHANGES:
            if isinstance(watched, QWidget) and watched.isWindow():
                self._due.add(sip.unwrapinstance(watched))
                if not self._place.isActive():
                    self._place.start()

        # a child raised or added over the line
        elif kind == QEvent.Type.ZOrderChange:
            line = _header_line(_parent_window(watched))
            if line is not None and watched is not line and line.isVisible():
                line.raise_()

        elif kind == QEvent.Type.ChildAdded:
            line = _header_line(watched)
            if line is not None and event.child() is not line and line.isVisible():
                line.raise_()

        return False


_WINDOW_CHANGES = frozenset(
    {QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.WindowStateChange}
)


def draw_header_lines(app) -> None:
    """On Wayland, where the compositor leaves the window's header to Qt
    (GNOME), a line between it and each window's content."""

    if QGuiApplication.platformName() != "wayland":
        return

    from gridplayer.utils.wayland_frames import compositor_draws_frames

    if compositor_draws_frames():
        return

    app._header_lines = _HeaderLines(app)
    app.installEventFilter(app._header_lines)


def _parent_window(widget) -> QWidget | None:
    if not isinstance(widget, QWidget) or widget.isWindow():
        return None

    parent = widget.parentWidget()

    return parent if parent is not None and parent.isWindow() else None


def _header_line(window) -> "_HeaderLine | None":
    if not isinstance(window, QWidget):
        return None

    return getattr(window, "_header_line", None)


def _place_header_line(window: QWidget) -> None:
    handle = window.windowHandle()
    has_header = handle is not None and _has_client_frame(handle)

    line = _header_line(window)

    if not has_header:
        if line is not None:
            line.hide()
        return

    if line is None:
        line = window._header_line = _HeaderLine(window)

    line.setGeometry(0, 0, window.width(), 1)
    line.show()
    line.raise_()


def refresh_window_frames() -> None:
    """Have the frames Qt draws itself on Wayland take the current palette.

    Where the compositor leaves the frame to the client (GNOME), Qt draws
    it with a decoration plugin that reads the palette once, as the frame
    is made. Taking the frame off and putting it straight back makes a new
    one; done on the QWindow, the widget is not hidden and recreated the
    way QWidget.setWindowFlags would.
    """

    if QGuiApplication.platformName() != "wayland":
        return

    for window in QGuiApplication.topLevelWindows():
        if not _has_client_frame(window):
            continue

        flags = window.flags()
        window.setFlags(flags | Qt.WindowType.FramelessWindowHint)
        window.setFlags(flags)

    # the lines under the headers, in the theme's colour now
    for widget in QApplication.topLevelWidgets():
        line = _header_line(widget)
        if line is not None:
            line.update()


def _has_client_frame(window) -> bool:
    if not window.isVisible():
        return False

    if window.flags() & Qt.WindowType.FramelessWindowHint:
        return False

    # a frame the compositor draws (KDE), or none at all (fullscreen),
    # leaves no margins; Qt makes a new one on leaving fullscreen anyway
    return not window.frameMargins().isNull()
