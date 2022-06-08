import platform
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QStyleFactory

from gridplayer.main.init_icons import init_icon, switch_icon_theme
from gridplayer.main.init_resources import init_resources
from gridplayer.main.init_translator import init_translator


def init_app():
    app = QApplication(sys.argv)

    app.paletteChanged.connect(switch_icon_theme)

    init_resources()

    if platform.system() == "Linux":
        app.setStyle(QStyleFactory.create("Fusion"))

    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    switch_icon_theme()

    init_icon(app)

    font_size = app.font().pointSize() if platform.system() == "Darwin" else 9
    app.setFont(QFont("Hack", font_size, QFont.Normal))

    init_translator(app)

    return app
