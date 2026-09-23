import logging
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication

_GNOME_INTERFACE = "org.gnome.desktop.interface"


def follow_desktop_cursor() -> None:
    """Draw the cursor from the theme the desktop uses.

    On Wayland the client draws its own cursor, and Qt 5 takes the theme
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
