import platform
import sys

from PyQt5.QtCore import QDir, QDirIterator, QLibraryInfo, QLocale, Qt, QTranslator
from PyQt5.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PyQt5.QtWidgets import QApplication, QStyleFactory

from gridplayer.settings import Settings

if platform.system() == "Windows":
    from PyQt5.QtWinExtras import QtWin  # noqa: WPS433

from gridplayer.utils.darkmode import is_dark_mode
from gridplayer.version import (
    __app_id__,
    __app_name__,
    __author_name__,
    __display_name__,
    __version__,
)


def setup_app_env():
    if platform.system() == "Windows":
        QtWin.setCurrentProcessExplicitAppUserModelID(__app_id__)

    QApplication.setApplicationName(__app_name__)
    QApplication.setApplicationDisplayName(__display_name__)
    QApplication.setOrganizationName(__author_name__)
    QApplication.setApplicationVersion(__version__)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def init_app():
    app = QApplication(sys.argv)

    app.paletteChanged.connect(_switch_icon_theme)

    _init_resources()

    if platform.system() == "Linux":
        app.setStyle(QStyleFactory.create("Fusion"))

    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    _switch_icon_theme()

    _init_icon(app)

    font_size = app.font().pointSize() if platform.system() == "Darwin" else 9
    app.setFont(QFont("Hack", font_size, QFont.Normal))

    _init_translator(app)

    return app


def _init_icon(app):
    if platform.system() == "Darwin":
        app.setWindowIcon(QIcon(":/icons/main_ico_mac.icns"))
    elif platform.system() == "Windows":
        app.setWindowIcon(QIcon(":/icons/main_ico_win.ico"))
    elif app.desktop().devicePixelRatio() == 1:
        app.setWindowIcon(QIcon(":/icons/main_ico_48.png"))
    else:
        app.setWindowIcon(QIcon(":/icons/main_ico_svg.svg"))


def _switch_icon_theme():
    if is_dark_mode():
        QIcon.setThemeName("dark")
    else:
        QIcon.setThemeName("light")


def _init_resources():
    # noinspection PyUnresolvedReferences
    from gridplayer import resources_bin  # noqa:F401,WPS433

    fonts = QDirIterator(":/fonts", ("*.ttf",), QDir.Files)

    while fonts.hasNext():
        font = fonts.next()  # noqa: B305
        QFontDatabase.addApplicationFont(font)


def _init_translator(app):
    lang = Settings().get("player/language")
    if lang == "en_US":
        return

    qt_translations_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)

    translator_qt = QTranslator(app)
    if translator_qt.load(QLocale(lang), "qtbase_", "", qt_translations_path):
        app.installTranslator(translator_qt)

    translator = QTranslator(app)
    if translator.load(lang, ":/translations/"):
        app.installTranslator(translator)
