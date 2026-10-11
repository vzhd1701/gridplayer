from abc import ABCMeta

from PyQt5.QtCore import QCoreApplication, QLocale, QObject, Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication, QWidget

QT_LOG_IGNORED = ("requestActivate() called for",)

# What a signal carrying milliseconds has to be declared as. PyQt maps a
# plain int to a 32-bit one, which runs out after 24.8 days and wraps
# without raising, quietly turning a time into a negative number. A live
# stream whose clock is counted from the epoch, as DASH manifests have
# it, is three orders of magnitude past that on its first frame.
MILLISECONDS = "qint64"

# Qt's xcb plugin writes a window's _NET_WM_WINDOW_TYPE from this property of
# its QWindow. 1 is QXcbWindowFunctions::Normal.
XCB_WM_WINDOW_TYPE = "_q_xcb_wm_window_type"
XCB_WM_WINDOW_TYPE_NORMAL = 0x000001


class QABC(type(QObject), ABCMeta):
    """Meta for abstract classes derived from QObject"""


def is_modal_open():
    return bool(QApplication.activeModalWidget() or QApplication.activePopupWidget())


def detach_modal_dialog(dialog: QWidget):
    """Let a modal dialog be moved apart from the window it belongs to.

    GNOME attaches a modal dialog to its window: it is pinned under that
    window's title bar, dragged along with it, and can't be moved on its own.
    It only does that to dialogs, so the dialog is called a normal window
    instead, which still stays above its window and keeps it blocked. Only
    X11 (Xwayland too) has the type. Goes before the dialog is first shown.
    """

    if QGuiApplication.platformName() != "xcb":
        return

    # Qt writes the type from the property when it makes the native window,
    # or when the window's flags change. The QWindow to hold the property
    # only comes with the native window, so that is made here, as showing
    # would, not shown yet, and the flags changed back and forth with one
    # that X11 has no use for. Not with winId() or WA_NativeWindow: those
    # make every other child of the dialog's parent native too.
    dialog.create()

    window = dialog.windowHandle()
    window.setProperty(XCB_WM_WINDOW_TYPE, XCB_WM_WINDOW_TYPE_NORMAL)

    flags = window.flags()
    window.setFlags(flags ^ Qt.WindowContextHelpButtonHint)
    window.setFlags(flags)


def qt_connect(*connections):
    for c_sig, c_slot in connections:
        c_sig.connect(c_slot)


def tr(text):
    return QCoreApplication.translate("@default", text)


def translate(context, text, disambiguation=None):
    return QCoreApplication.translate(context, text, disambiguation)


def count_txt(count: int) -> str:
    """A number as the viewer's language writes it: 40,000 in English."""

    return QLocale().toString(count)


def fit_height(window: QWidget) -> None:
    """A window as tall as its words need at the width it is.

    Qt sizes a window at its size hint's width, where wrapped lines wrap
    more, and only then widens it to its minimum width: the height left
    over is spread between its rows, as gaps."""

    height = window.heightForWidth(window.width())

    if height > 0:
        window.resize(window.width(), height)


def is_qt_log_ignored(message):
    for ignored in QT_LOG_IGNORED:
        if ignored in message:
            return True

    return False
