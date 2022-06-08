import re
from abc import ABCMeta
from multiprocessing.process import active_children

from PyQt5.QtCore import QCoreApplication, QObject
from PyQt5.QtWidgets import QApplication


class QABC(type(QObject), ABCMeta):  # noqa: WPS606
    """Meta for abstract classes derived from QObject"""


def is_modal_open():
    return bool(QApplication.activeModalWidget() or QApplication.activePopupWidget())


def qt_connect(*connections):
    for c_sig, c_slot in connections:
        c_sig.connect(c_slot)


def force_terminate_children():
    for p in active_children():
        p.terminate()


def tr(text):
    return QCoreApplication.translate("@default", text)


def translate(context, text):
    return QCoreApplication.translate(context, text)


def is_url(s) -> bool:
    return bool(re.match("^[a-z]+://", s))
