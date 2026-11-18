from PyQt6.QtCore import QDir, QDirIterator
from PyQt6.QtGui import QFontDatabase, QIcon

from gridplayer.params import env


def init_resources():
    icon_theme_dir = env.RESOURCES_DIR / "icons"
    theme_paths = [*QIcon.themeSearchPaths(), str(icon_theme_dir)]
    QIcon.setThemeSearchPaths(theme_paths)

    fonts_dir = env.RESOURCES_DIR / "fonts"
    fonts = QDirIterator(
        str(fonts_dir),
        ("*.ttf",),
        QDir.Filter.Files,
        QDirIterator.IteratorFlag.Subdirectories,
    )

    while fonts.hasNext():
        font = fonts.next()
        QFontDatabase.addApplicationFont(font)
