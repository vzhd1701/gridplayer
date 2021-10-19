import logging
import platform

from PyQt5.QtGui import QPalette

SYSTEM = platform.system()

logger = logging.getLogger(__name__)

# Doesn't work by itself, need to implement dark mode in app
# if SYSTEM == "Windows":
#     from PyQt5.QtCore import QSettings
#     def is_dark_mode():
#         settings = QSettings(
#             "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion"
#             "\\Themes\\Personalize",
#             QSettings.NativeFormat,
#         )
#         return settings.value("AppsUseLightTheme", 1) == 0

if SYSTEM == "Darwin":
    from Foundation import NSUserDefaults as NSUD

    def is_dark_mode():
        style = NSUD.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
        return style == "Dark"


else:

    def is_dark_mode():
        return QPalette().color(QPalette.Window).lightness() < 128
