import sys
from unittest.mock import Mock

from PyQt6.QtWidgets import QWidget

from gridplayer.utils.macos_window import without_window_animation


def test_a_window_not_on_cocoa_is_left_alone(monkeypatch):
    # offscreen's window id isn't an NSView: read as one, it crashed the
    # tests on macOS
    objc = Mock()
    monkeypatch.setitem(sys.modules, "objc", objc)

    widget = QWidget()
    without_window_animation(widget)

    objc.objc_object.assert_not_called()
