import sys

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from gridplayer.utils.qt import CAPTION_AS_BACKGROUND

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows' DWM")


@pytest.fixture
def win32_window(mocker):
    from gridplayer.utils import win32_window

    mocker.patch.object(win32_window, "_is_windows_11", return_value=True)
    mocker.patch.object(win32_window, "_load_dwmapi")
    mocker.patch.object(win32_window, "_dwm_set")
    return win32_window


def _caption(win32_window):
    return [
        c.args[2]
        for c in win32_window._dwm_set.call_args_list
        if c.args[1] == win32_window._DWMWA_CAPTION_COLOR
    ]


def _player_window():
    widget = QWidget()
    widget.setProperty(CAPTION_AS_BACKGROUND, True)
    return widget


def test_nothing_before_windows_11(mocker, win32_window):
    mocker.patch.object(win32_window, "_is_windows_11", return_value=False)

    win32_window.apply_native_background(QWidget())

    win32_window._dwm_set.assert_not_called()


@pytest.mark.parametrize(
    "flags",
    [
        Qt.WindowType.Popup,
        Qt.WindowType.ToolTip,
        Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint,
    ],
)
def test_nothing_for_a_window_without_a_title_bar(win32_window, flags):
    win32_window.apply_native_background(QWidget(None, flags))

    win32_window._dwm_set.assert_not_called()


def test_a_dialogs_title_bar_stands_apart(mocker, win32_window):
    mocker.patch.object(
        win32_window,
        "current_colors",
        return_value={"caption": "#123456", "border": "#000000"},
    )

    win32_window.apply_native_background(QDialog())

    assert _caption(win32_window) == [0x563412]


def test_the_players_of_the_application_palette(mocker, win32_window):
    """Not the window's own, which takes the new theme's only in an event
    yet to come."""

    widget = _player_window()
    app_palette = QPalette(QApplication.palette(widget))
    app_palette.setColor(widget.backgroundRole(), QColor(0x11, 0x22, 0x33))
    mocker.patch.object(win32_window.QApplication, "palette", return_value=app_palette)

    win32_window.apply_native_background(widget)

    assert _caption(win32_window) == [0x332211]


def test_the_players_of_a_palette_of_its_own(win32_window):
    widget = _player_window()
    own = QPalette(widget.palette())
    own.setColor(widget.backgroundRole(), QColor(0x44, 0x55, 0x66))
    widget.setPalette(own)

    win32_window.apply_native_background(widget)

    assert _caption(win32_window) == [0x665544]


def test_coloured_as_a_window_is_shown(mocker, win32_window):
    apply = mocker.patch.object(win32_window, "apply_native_background")
    title_bars = win32_window._TitleBars()
    window = QDialog()
    child = QWidget(window)
    shown = QEvent(QEvent.Type.Show)

    title_bars.eventFilter(child, shown)
    title_bars.eventFilter(window, QEvent(QEvent.Type.Resize))
    apply.assert_not_called()

    title_bars.eventFilter(window, shown)
    apply.assert_called_once_with(window)
