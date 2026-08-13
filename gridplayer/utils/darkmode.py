import logging

from PyQt5.QtGui import QPalette

from gridplayer.params import env


def is_dark_mode() -> bool:
    if env.IS_MACOS:
        return _macos_is_dark()
    if env.IS_WINDOWS:
        return _windows_is_dark()

    from gridplayer.utils.darkmode_linux import linux_is_dark

    return linux_is_dark()


def watch_system_theme(callback, parent=None):
    """Call *callback* when the OS color scheme changes. Linux only for now."""
    if not env.IS_LINUX:
        return None

    from gridplayer.utils.darkmode_linux import LinuxThemeWatcher

    try:
        return LinuxThemeWatcher(callback, parent)
    except Exception:
        logging.getLogger(__name__).exception("Could not watch system theme")
        return None


def _macos_is_dark() -> bool:
    from Foundation import NSUserDefaults as NSUD

    style = NSUD.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
    return style == "Dark"


def _windows_is_dark() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return _palette_is_dark()
    else:
        return value == 0


def _palette_is_dark() -> bool:
    return QPalette().color(QPalette.Window).lightness() < 128
