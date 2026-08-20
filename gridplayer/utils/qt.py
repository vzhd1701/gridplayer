from abc import ABCMeta
from types import MappingProxyType

from PyQt5.QtCore import QCoreApplication, QObject, Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import VideoAspect

QT_ASPECT_MAP = MappingProxyType(
    {
        VideoAspect.FIT: Qt.KeepAspectRatioByExpanding,
        VideoAspect.STRETCH: Qt.IgnoreAspectRatio,
        VideoAspect.NONE: Qt.KeepAspectRatio,
    }
)
QT_LOG_IGNORED = ("requestActivate() called for",)


class QABC(type(QObject), ABCMeta):
    """Meta for abstract classes derived from QObject"""


def is_modal_open():
    return bool(QApplication.activeModalWidget() or QApplication.activePopupWidget())


def qt_connect(*connections):
    for c_sig, c_slot in connections:
        c_sig.connect(c_slot)


def tr(text):
    return QCoreApplication.translate("@default", text)


def translate(context, text, disambiguation=None):
    return QCoreApplication.translate(context, text, disambiguation)


def is_qt_log_ignored(message):
    for ignored in QT_LOG_IGNORED:
        if ignored in message:
            return True

    return False
