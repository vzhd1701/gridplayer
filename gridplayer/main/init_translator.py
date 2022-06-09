import logging
import platform

from PyQt5.QtCore import QLibraryInfo, QLocale, QTranslator

from gridplayer import params_env
from gridplayer.settings import Settings


def init_translator(app):
    lang = Settings().get("player/language")
    if lang == "en_US":
        return

    logger = logging.getLogger("INIT")
    logger.debug(f"Loading translation for {lang}")

    if params_env.IS_PYINSTALLER and platform.system() == "Windows":
        qt_translations_path = str(
            params_env.PYINSTALLER_LIB_ROOT / "PyQt5" / "Qt5" / "translations"
        )
    else:
        qt_translations_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    logger.debug(f"QT translations path: {qt_translations_path}")

    translator_qt = QTranslator(app)
    if translator_qt.load(QLocale(lang), "qtbase_", "", qt_translations_path):
        app.installTranslator(translator_qt)
    else:
        logger.warning(f"Failed to load QT translation for {lang}")

    translator = QTranslator(app)
    if translator.load(lang, ":/translations/"):
        app.installTranslator(translator)
    else:
        logger.warning(f"Failed to load translation for {lang}")
