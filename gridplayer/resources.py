from PyQt5.QtCore import QDir, QDirIterator
from PyQt5.QtGui import QFontDatabase


class QDirIteratorPy(QDirIterator):
    def __iter__(self):
        return self

    def __next__(self):
        if not self.hasNext():
            raise StopIteration

        return self.next()


def init_resources():
    # noinspection PyUnresolvedReferences
    from gridplayer import resources_bin

    fonts = QDirIteratorPy(":/fonts", ("*.ttf",), QDir.Files)

    for font in fonts:
        QFontDatabase.addApplicationFont(font)
