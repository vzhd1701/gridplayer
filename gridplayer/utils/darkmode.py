import functools
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

from gridplayer.params import env
from gridplayer.params.static import ColorScheme
from gridplayer.settings import Settings


def app_color_scheme() -> ColorScheme | None:
    """The colour scheme setting, None while the settings can't be read."""

    try:
        return Settings().get("player/color_scheme")
    except RuntimeError:
        return None


def is_dark_mode() -> bool:
    scheme = app_color_scheme()

    if scheme == ColorScheme.LIGHT:
        return False
    if scheme == ColorScheme.DARK:
        return True

    return is_system_dark_mode()


# Asked once, until the theme is applied again (apply_theme forgets it):
# the colours are read on every paint of some widgets, and asking is a
# D-Bus call to the portal on Linux.
@functools.cache
def is_system_dark_mode() -> bool:
    """The system's, asked only while the app follows it."""

    if not env.IS_LINUX:
        # Qt is told no scheme of its own then (theme._tell_qt_the_scheme),
        # so it says the system's, in step with the system's own switch
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    from gridplayer.utils.darkmode_linux import linux_is_dark

    return linux_is_dark()


def watch_system_theme(callback, parent=None):
    """Call *callback* when the OS color scheme changes, on Linux.

    Qt 6.12 doesn't know it on every Linux desktop: Unknown on sway and other
    window managers, and Light at the start on a GNOME that is dark by its
    colour scheme alone (without a dark GTK theme). Elsewhere Qt's
    colorSchemeChanged says it (None here)."""

    if not env.IS_LINUX:
        return None

    try:
        from gridplayer.utils.darkmode_linux import LinuxThemeWatcher

        return LinuxThemeWatcher(callback, parent)
    except Exception:
        logging.getLogger(__name__).exception("Could not watch system theme")
        return None
