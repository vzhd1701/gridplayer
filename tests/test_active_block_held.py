from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.player.managers import active_block
from gridplayer.player.managers.active_block import ActiveBlockManager


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Manager(ActiveBlockManager):
    """The video under the pointer, and the buttons held, as the test puts
    them."""

    def __init__(self):
        super().__init__(context=SimpleNamespace())
        self.under = None

    def get_video_block_under_mouse(self):
        return self.under

    def cmd_active(self, *_args, **_kwargs):
        pass

    def _update_active_block(self, new_active_block):
        self._ctx.active_block = new_active_block


@pytest.fixture
def buttons(mocker):
    held = SimpleNamespace(now=Qt.NoButton)
    mocker.patch.object(active_block, "is_modal_open", return_value=False)
    mocker.patch.object(
        active_block.QApplication, "mouseButtons", side_effect=lambda: held.now
    )
    return held


def _mouse(manager, kind):
    event = QMouseEvent(
        kind, QPointF(1, 1), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
    )
    manager.eventFilter(None, event)


def test_a_double_click_stays_with_the_video_it_was_pressed_on(buttons):
    manager = _Manager()
    small, big = object(), object()

    manager.under = small
    buttons.now = Qt.LeftButton
    _mouse(manager, QEvent.MouseButtonPress)
    assert manager._ctx.active_block is small

    # shown big: the one shown big till now comes under the pointer
    manager.under = big
    manager.update_active_under_mouse()
    _mouse(manager, QEvent.MouseMove)
    assert manager._ctx.active_block is small

    # once the button is let go of
    buttons.now = Qt.NoButton
    manager._check_let_go()
    assert manager._ctx.active_block is big
    assert not manager._let_go_timer.isActive()


def test_a_press_takes_the_video_under_the_pointer(buttons):
    manager = _Manager()
    first, second = object(), object()

    manager.under = first
    manager.update_active_under_mouse()

    # come to it with no move seen
    manager.under = second
    buttons.now = Qt.LeftButton
    _mouse(manager, QEvent.MouseButtonPress)
    assert manager._ctx.active_block is second
