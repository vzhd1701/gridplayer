import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QStyleFactory

from gridplayer.main.init_icons import init_icon
from gridplayer.main.init_resources import init_resources
from gridplayer.main.init_translator import init_translator
from gridplayer.params.static import FONT_SIZE_MAIN
from gridplayer.params.theme import apply_theme


def init_app():
    app = QApplication(sys.argv)

    init_resources()

    app.setStyle(QStyleFactory.create("Fusion"))

    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    apply_theme(app)
    app.paletteChanged.connect(lambda: apply_theme(app))

    init_icon(app)

    app.setFont(QFont("Hack", FONT_SIZE_MAIN))

    init_translator(app)

    return app
