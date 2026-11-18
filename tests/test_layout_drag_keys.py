"""The keys while a line or a tile is dragged (LayoutDragManager): Alt or
Shift counts at once, held still, and Esc puts it back."""

from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent

from gridplayer.player.managers.layout_drag import LayoutDragManager


def _manager(is_dragging=True):
    manager = SimpleNamespace(
        _drag=object() if is_dragging else None, moves=[], cancels=[], _key_seen=None
    )
    manager._move_to = lambda _pos, modifiers: manager.moves.append(modifiers)
    manager._cancel = lambda: manager.cancels.append(True)
    manager.key_release = lambda event: LayoutDragManager.key_release(manager, event)
    return manager


def _key(kind, key, modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(kind, key, modifiers)


def test_alt_pressed_and_let_go_of_drags_it_again_where_it_is():
    manager = _manager()

    LayoutDragManager.key_press(manager, _key(QEvent.Type.KeyPress, Qt.Key.Key_Alt))
    LayoutDragManager.key_release(
        manager,
        _key(QEvent.Type.KeyRelease, Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier),
    )

    assert [bool(m & Qt.KeyboardModifier.AltModifier) for m in manager.moves] == [
        True,
        False,
    ]


def test_a_key_seen_again_on_its_way_up_counts_once():
    manager = _manager()
    alt = _key(QEvent.Type.KeyPress, Qt.Key.Key_Alt)

    # at the widget it is for, then at its parents
    for _widget in range(3):
        LayoutDragManager.key_press(manager, alt)

    assert len(manager.moves) == 1


def test_a_key_held_down_counts_once():
    manager = _manager()

    LayoutDragManager.key_press(manager, _key(QEvent.Type.KeyPress, Qt.Key.Key_Shift))
    LayoutDragManager.key_press(
        manager,
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Shift,
            Qt.KeyboardModifier.ShiftModifier,
            "",
            True,
        ),
    )

    assert len(manager.moves) == 1


@pytest.mark.parametrize("is_dragging", [True, False])
def test_other_keys_or_no_drag_move_nothing(is_dragging):
    manager = _manager(is_dragging)

    LayoutDragManager.key_press(manager, _key(QEvent.Type.KeyPress, Qt.Key.Key_A))
    if not is_dragging:
        LayoutDragManager.key_press(manager, _key(QEvent.Type.KeyPress, Qt.Key.Key_Alt))

    assert manager.moves == []


def test_esc_puts_it_back():
    manager = _manager()

    assert LayoutDragManager.key_press(
        manager, _key(QEvent.Type.KeyPress, Qt.Key.Key_Escape)
    )
    assert manager.cancels == [True]
    assert manager.moves == []
