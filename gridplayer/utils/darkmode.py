import logging
import platform

from PyQt5.QtGui import QPalette

SYSTEM = platform.system()

logger = logging.getLogger(__name__)

if SYSTEM == "Darwin":
    from Foundation import NSUserDefaults as NSUD

    def is_dark_mode():
        style = NSUD.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
        return style == "Dark"


else:

    def is_dark_mode():
        brightness_threshold = 128

        return QPalette().color(QPalette.Window).lightness() < brightness_threshold
