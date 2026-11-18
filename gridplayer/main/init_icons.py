from PyQt6.QtGui import QIcon

from gridplayer.params import env
from gridplayer.utils.darkmode import is_dark_mode


def init_icon(app):
    icons_dir = env.RESOURCES_DIR / "icons"

    if env.IS_MACOS:
        app.setWindowIcon(QIcon(str(icons_dir / "main_ico_mac.icns")))
    elif env.IS_WINDOWS:
        app.setWindowIcon(QIcon(str(icons_dir / "main_ico_win.ico")))
    elif (screen := app.primaryScreen()) is None or screen.devicePixelRatio() == 1:
        app.setWindowIcon(QIcon(str(icons_dir / "main_ico_48.png")))
    else:
        app.setWindowIcon(QIcon(str(icons_dir / "main_ico_svg.svg")))


def switch_icon_theme():
    if is_dark_mode():
        QIcon.setThemeName("dark")
    else:
        QIcon.setThemeName("light")
