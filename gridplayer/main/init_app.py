import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QStyleFactory

from gridplayer.main.init_icons import init_icon
from gridplayer.main.init_resources import init_resources
from gridplayer.main.init_translator import init_translator
from gridplayer.params import env
from gridplayer.params.static import FONT_SIZE_MAIN
from gridplayer.params.theme import apply_theme, on_system_theme_changed
from gridplayer.utils.darkmode import watch_system_theme


def init_app():
    # Wayland doesnt work with libVLC, forcing xcb
    if env.IS_LINUX:
        sys.argv += ["-platform", "xcb"]

    app = QApplication(sys.argv)

    init_resources()

    app.setStyle(QStyleFactory.create("Fusion"))

    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    apply_theme(app)
    app.paletteChanged.connect(lambda: on_system_theme_changed(app))
    watch_system_theme(lambda: on_system_theme_changed(app), app)

    init_icon(app)

    app.setFont(QFont("Hack", FONT_SIZE_MAIN))

    init_translator(app)

    return app
