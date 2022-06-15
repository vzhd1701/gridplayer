import logging

from PyQt5.QtCore import QLibraryInfo, QLocale, QTranslator

from gridplayer.params import env
from gridplayer.settings import Settings


def init_translator(app):
    log = logging.getLogger(__name__)

    lang = Settings().get("player/language")
    if lang == "en_US":
        return

    log.debug(f"Loading translation for {lang}")

    if env.IS_PYINSTALLER and env.IS_WINDOWS:
        qt_translations_path = str(
            env.PYINSTALLER_LIB_ROOT / "PyQt5" / "Qt5" / "translations"
        )
    else:
        qt_translations_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    log.debug(f"QT translations path: {qt_translations_path}")

    translator_qt = QTranslator(app)
    if translator_qt.load(QLocale(lang), "qtbase_", "", qt_translations_path):
        app.installTranslator(translator_qt)
    else:
        log.warning(f"Failed to load QT translation for {lang}")

    translator = QTranslator(app)
    if translator.load(lang, ":/translations/"):
        app.installTranslator(translator)
    else:
        log.warning(f"Failed to load translation for {lang}")
