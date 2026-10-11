import functools
import logging

from gridplayer.params import env
from gridplayer.params.static import ColorScheme
from gridplayer.settings import Settings


def is_dark_mode() -> bool:
    try:
        scheme = Settings().get("player/color_scheme")
    except RuntimeError:
        return is_system_dark_mode()

    if scheme == ColorScheme.LIGHT:
        return False
    if scheme == ColorScheme.DARK:
        return True

    return is_system_dark_mode()


# Asked once, until the theme is applied again (apply_theme forgets it):
# the colours are read on every paint of some widgets, and asking is a
# registry read on Windows and a D-Bus call to the portal on Linux.
@functools.cache
def is_system_dark_mode() -> bool:
    if env.IS_MACOS:
        return _macos_is_dark()
    if env.IS_WINDOWS:
        from gridplayer.utils.darkmode_windows import windows_is_dark

        return windows_is_dark()

    from gridplayer.utils.darkmode_linux import linux_is_dark

    return linux_is_dark()


def watch_system_theme(callback, parent=None):
    """Call *callback* when the OS color scheme changes."""
    try:
        if env.IS_LINUX:
            from gridplayer.utils.darkmode_linux import LinuxThemeWatcher

            return LinuxThemeWatcher(callback, parent)
        if env.IS_WINDOWS:
            from gridplayer.utils.darkmode_windows import WindowsThemeWatcher

            return WindowsThemeWatcher(callback, parent)
    except Exception:
        logging.getLogger(__name__).exception("Could not watch system theme")
        return None

    return None


def _macos_is_dark() -> bool:
    from Foundation import NSUserDefaults as NSUD

    style = NSUD.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
    return style == "Dark"
