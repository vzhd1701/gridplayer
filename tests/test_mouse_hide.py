"""The pointer hidden over the videos once it rests, not over a window that
is over them."""

from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog, QWidget

from gridplayer.player.managers.mouse_hide import MouseHideManager


@pytest.fixture
def manager():
    player = QWidget()
    manager = MouseHideManager(
        context=SimpleNamespace(video_blocks=[object()]), parent=player
    )
    manager.player = player

    yield manager

    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def test_hidden_resting_over_the_videos(manager, mocker):
    mocker.patch.object(QApplication, "topLevelAt", return_value=manager.player)

    manager.hide_cursor()

    assert QApplication.overrideCursor().shape() == Qt.BlankCursor


def test_left_on_show_resting_over_the_list_window(manager, mocker):
    mocker.patch.object(
        QApplication, "topLevelAt", return_value=QDialog(manager.player)
    )

    manager.hide_cursor()

    assert QApplication.overrideCursor() is None
