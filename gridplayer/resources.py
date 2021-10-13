import glob
import os
import sys

from PyQt5.QtCore import QDir, QDirIterator
from PyQt5.QtGui import QFontDatabase, QIcon

ICONS = {"": QIcon()}


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

    icons = QDirIteratorPy(
        ":/icons",
        ("*.ico", "*.svg", "*.png", "*.icns"),
        QDir.Files,
        QDirIterator.Subdirectories,
    )

    for icon in icons:
        icon_name, _ = os.path.splitext(os.path.relpath(icon, ":/icons"))
        icon_name = icon_name.replace("\\", "/")
        ICONS[icon_name] = QIcon(icon)


def load_resources_dbg():
    resource_dir = os.path.join(os.path.dirname(sys.argv[0]), "resources")

    fonts_dir = os.path.join(resource_dir, "fonts")
    icons_dir = os.path.join(resource_dir, "icons")

    for font in glob.glob(os.path.join(fonts_dir, "*.ttf")):
        QFontDatabase.addApplicationFont(font)

    for ext in ("ico", "svg", "png"):
        icons = glob.glob(os.path.join(icons_dir, "**", f"*.{ext}"), recursive=True)

        for icon in icons:
            icon_name, _ = os.path.splitext(os.path.relpath(icon, icons_dir))
            icon_name = icon_name.replace("\\", "/")
            ICONS[icon_name] = QIcon(icon)
