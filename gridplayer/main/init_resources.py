from PyQt5.QtCore import QDir, QDirIterator
from PyQt5.QtGui import QFontDatabase


def init_resources():
    # noinspection PyUnresolvedReferences
    from gridplayer import resources_bin  # noqa:F401,WPS433

    fonts = QDirIterator(":/fonts", ("*.ttf",), QDir.Files)

    while fonts.hasNext():
        font = fonts.next()  # noqa: B305
        QFontDatabase.addApplicationFont(font)
