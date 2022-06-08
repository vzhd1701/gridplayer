import platform

from PyQt5.QtGui import QIcon

from gridplayer.utils.darkmode import is_dark_mode


def init_icon(app):
    if platform.system() == "Darwin":
        app.setWindowIcon(QIcon(":/icons/main_ico_mac.icns"))
    elif platform.system() == "Windows":
        app.setWindowIcon(QIcon(":/icons/main_ico_win.ico"))
    elif app.desktop().devicePixelRatio() == 1:
        app.setWindowIcon(QIcon(":/icons/main_ico_48.png"))
    else:
        app.setWindowIcon(QIcon(":/icons/main_ico_svg.svg"))


def switch_icon_theme():
    if is_dark_mode():
        QIcon.setThemeName("dark")
    else:
        QIcon.setThemeName("light")
