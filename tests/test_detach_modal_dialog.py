"""A modal dialog GNOME is not to attach to its window.

Mutter pins a modal dialog to the window it belongs to, so the dialog is
called a normal window on X11. Qt writes the type from a property of the
dialog's QWindow, and only when it makes the native window or the flags
change, so the property has to land on a window that has not been shown.
"""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QWidget

from gridplayer.utils import qt as qt_utils
from gridplayer.utils.qt import (
    XCB_WM_WINDOW_TYPE,
    XCB_WM_WINDOW_TYPE_NORMAL,
    detach_modal_dialog,
)


def _on(monkeypatch, platform):
    class _FakeApp:
        @staticmethod
        def platformName():
            return platform

    monkeypatch.setattr(qt_utils, "QGuiApplication", _FakeApp)


@pytest.fixture
def window():
    window = QWidget()
    yield window
    window.deleteLater()


def test_normal_window_on_x11(monkeypatch, window):
    _on(monkeypatch, "xcb")

    dialog = QDialog(window)
    flags = dialog.windowFlags()

    detach_modal_dialog(dialog)

    handle = dialog.windowHandle()
    assert handle.property(XCB_WM_WINDOW_TYPE) == XCB_WM_WINDOW_TYPE_NORMAL
    assert not dialog.isVisible()

    # the flags changed only to have the type written, and back
    assert handle.flags() == flags
    assert dialog.windowFlags() == flags


def test_leaves_the_windows_children_alien(monkeypatch, window):
    """WA_NativeWindow would have made every other child of the dialog's
    window native too, the grid's cells among them."""

    _on(monkeypatch, "xcb")

    cell = QWidget(window)
    dialog = QDialog(window)

    detach_modal_dialog(dialog)

    assert not cell.testAttribute(Qt.WA_NativeWindow)
    assert not dialog.testAttribute(Qt.WA_NativeWindow)

    added = QWidget(window)
    assert not added.testAttribute(Qt.WA_NativeWindow)


@pytest.mark.parametrize("platform", ["wayland", "windows", "cocoa", "offscreen"])
def test_untouched_elsewhere(monkeypatch, window, platform):
    _on(monkeypatch, platform)

    dialog = QDialog(window)

    detach_modal_dialog(dialog)

    assert dialog.windowHandle() is None
