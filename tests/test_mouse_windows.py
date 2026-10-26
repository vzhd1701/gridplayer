import ctypes
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows messages")


def _move(w_param):
    from ctypes import wintypes

    msg = wintypes.MSG()
    msg.message = 0x0200
    msg.wParam = w_param
    return msg


@pytest.fixture
def qt_buttons(mocker):
    from PyQt5.QtCore import Qt

    from gridplayer.utils import mouse_windows

    # what Qt takes to be held, from the messages before
    return mocker.patch.object(
        mouse_windows.QGuiApplication, "mouseButtons", return_value=Qt.LeftButton
    )


@pytest.fixture
def user32(mocker, qt_buttons):
    from gridplayer.utils import mouse_windows

    user32 = mocker.patch.object(mouse_windows.ctypes, "windll").user32
    user32.GetSystemMetrics.return_value = 0
    user32.GetAsyncKeyState.side_effect = lambda key: 0x8000 if key == 0x01 else 0
    return user32


def _filtered(msg):
    from gridplayer.utils.mouse_windows import _HeldButtonsFilter

    _HeldButtonsFilter().nativeEventFilter(
        b"windows_generic_MSG", ctypes.addressof(msg)
    )
    return msg.wParam


def test_a_move_saying_no_button_is_held_is_given_the_ones_held(user32):
    # the left button down, Ctrl too
    assert _filtered(_move(0x0008)) == 0x0009


def test_a_move_saying_a_button_is_held_is_left_as_it_is(user32):
    assert _filtered(_move(0x0002)) == 0x0002
    user32.GetAsyncKeyState.assert_not_called()


def test_no_button_held_before_the_move_is_not_asked_about(user32, qt_buttons):
    from PyQt5.QtCore import Qt

    qt_buttons.return_value = Qt.NoButton

    assert _filtered(_move(0)) == 0
    user32.GetAsyncKeyState.assert_not_called()


def test_the_left_button_swapped_is_the_right_ones_key(user32):
    user32.GetSystemMetrics.return_value = 1
    user32.GetAsyncKeyState.side_effect = lambda key: 0x8000 if key == 0x02 else 0

    assert _filtered(_move(0)) == 0x0001
