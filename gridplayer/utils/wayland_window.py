from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication


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
        window.setFlags(flags | Qt.FramelessWindowHint)
        window.setFlags(flags)


def _has_client_frame(window) -> bool:
    if not window.isVisible():
        return False

    if window.flags() & Qt.FramelessWindowHint:
        return False

    # a frame the compositor draws (KDE), or none at all (fullscreen),
    # leaves no margins; Qt makes a new one on leaving fullscreen anyway
    return not window.frameMargins().isNull()
