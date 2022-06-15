from PyQt5.QtGui import QPalette

from gridplayer.params import env

if env.IS_MACOS:
    from Foundation import NSUserDefaults as NSUD

    def is_dark_mode():
        style = NSUD.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
        return style == "Dark"


else:

    def is_dark_mode():
        brightness_threshold = 128

        return QPalette().color(QPalette.Window).lightness() < brightness_threshold
