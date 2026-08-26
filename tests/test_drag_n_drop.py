from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.params.static import DropAction, DropModifier
from gridplayer.player.managers.drag_n_drop import DragNDropManager
from gridplayer.utils.drag_n_drop import drop_is_replace


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _mouse_move():
    return QMouseEvent(
        QEvent.MouseMove,
        QPoint(1, 1),
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


def _key_press(key, modifiers=Qt.NoModifier):
    return QKeyEvent(QEvent.KeyPress, key, modifiers)


def test_drop_is_replace_insert_default_shift():
    action = DropAction.INSERT
    modifier = DropModifier.SHIFT
    assert drop_is_replace(Qt.NoModifier, action, modifier) is False
    assert drop_is_replace(Qt.ShiftModifier, action, modifier) is True
    assert drop_is_replace(Qt.ControlModifier, action, modifier) is False
    assert (
        drop_is_replace(Qt.ShiftModifier | Qt.ControlModifier, action, modifier) is True
    )


def test_drop_is_replace_insert_ctrl_or_alt():
    action = DropAction.INSERT
    assert drop_is_replace(Qt.ControlModifier, action, DropModifier.CTRL) is True
    assert drop_is_replace(Qt.ShiftModifier, action, DropModifier.CTRL) is False
    assert drop_is_replace(Qt.AltModifier, action, DropModifier.ALT) is True
    assert drop_is_replace(Qt.ShiftModifier, action, DropModifier.ALT) is False


def test_drop_is_replace_replace_default_inverts_modifier():
    action = DropAction.REPLACE
    modifier = DropModifier.SHIFT
    assert drop_is_replace(Qt.NoModifier, action, modifier) is True
    assert drop_is_replace(Qt.ShiftModifier, action, modifier) is False


def test_drop_is_replace_none_ignores_keys():
    assert (
        drop_is_replace(Qt.ShiftModifier, DropAction.INSERT, DropModifier.NONE) is False
    )
    assert drop_is_replace(Qt.NoModifier, DropAction.REPLACE, DropModifier.NONE) is True
    assert (
        drop_is_replace(Qt.ControlModifier, DropAction.REPLACE, DropModifier.NONE)
        is True
    )


class _Ctx:
    def __init__(self):
        self.is_drag_ui = False
        self.commands = SimpleNamespace(
            get_video_block_at=lambda *_a, **_k: None,
            update_active_under_mouse=lambda: None,
            activate_window=lambda: None,
        )


def _make_manager():
    parent = QWidget()
    manager = DragNDropManager(context=_Ctx(), parent=parent)
    return manager, parent


def test_linux_uses_fake_drag_by_default(mocker):
    manager, _parent = _make_manager()
    mocker.patch("gridplayer.player.managers.drag_n_drop.env.IS_LINUX", True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
    )
    mocker.patch.object(manager, "_is_drag_started", return_value=True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.Settings"
    ).return_value.get.return_value = False
    start_fake = mocker.patch.object(manager, "_start_fake_drag")
    make_qdrag = mocker.patch.object(manager, "_make_qdrag")

    assert manager.mouseMoveEvent(_mouse_move()) is True
    start_fake.assert_called_once()
    make_qdrag.assert_not_called()


def test_linux_force_native_drag_uses_qdrag(mocker):
    manager, _parent = _make_manager()
    manager._ctx.active_block = object()
    mocker.patch("gridplayer.player.managers.drag_n_drop.env.IS_LINUX", True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
    )
    mocker.patch.object(manager, "_is_drag_started", return_value=True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.Settings"
    ).return_value.get.return_value = True
    start_fake = mocker.patch.object(manager, "_start_fake_drag")
    drag = mocker.Mock()
    mocker.patch.object(manager, "_make_qdrag", return_value=drag)
    mocker.patch.object(manager, "_ensure_drag_ui")
    mocker.patch.object(manager, "_set_source")
    mocker.patch.object(manager, "_end_drag_ui")

    manager.mouseMoveEvent(_mouse_move())

    start_fake.assert_not_called()
    drag.exec.assert_called_once()


def test_fake_drag_mouse_move_does_not_use_event_keyboard_modifiers(mocker):
    """Qt5 QMouseEvent has modifiers(), not keyboardModifiers() — that used to crash."""
    manager, _parent = _make_manager()
    manager._is_fake_drag_active = True
    manager._ctx.is_drag_ui = True
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.ShiftModifier
    )

    assert manager.mouseMoveEvent(_mouse_move()) is True


def test_fake_drag_key_press_shift_does_not_use_event_keyboard_modifiers(mocker):
    manager, _parent = _make_manager()
    manager._is_fake_drag_active = True
    manager._ctx.is_drag_ui = True
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.ShiftModifier
    )

    assert manager.keyPressEvent(_key_press(Qt.Key_Shift, Qt.ShiftModifier)) is True


def _patch_drop_settings(
    mocker,
    internal=DropAction.INSERT,
    external=DropAction.INSERT,
    modifier=DropModifier.SHIFT,
):
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.Settings"
    ).return_value.get.side_effect = lambda key: {
        "playlist/drop_action_internal": internal,
        "playlist/drop_action_external": external,
        "playlist/drop_modifier": modifier,
    }[key]


def test_is_replace_reads_os_keyboard_state(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(mocker)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.query_drop_modifiers",
        return_value=Qt.NoModifier,
    )
    assert manager._is_replace(True) is False
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.query_drop_modifiers",
        return_value=Qt.ShiftModifier,
    )
    assert manager._is_replace(True) is True


def test_is_replace_uses_dnd_move_action_as_shift(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.NoModifier
    )
    event = SimpleNamespace(
        keyboardModifiers=lambda: Qt.NoModifier,
        proposedAction=lambda: Qt.MoveAction,
        possibleActions=lambda: Qt.CopyAction | Qt.MoveAction,
        mimeData=lambda: SimpleNamespace(
            hasFormat=lambda fmt: fmt == "text/uri-list",
            hasUrls=lambda: True,
        ),
    )
    assert manager._is_replace(False, event) is True


def test_is_replace_uses_event_modifiers_when_query_empty(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.NoModifier
    )
    event = SimpleNamespace(keyboardModifiers=lambda: Qt.ShiftModifier)
    assert manager._is_replace(True, event) is True
    assert manager._is_replace(True) is False


def test_is_replace_internal_and_external_use_separate_defaults(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(
        mocker, internal=DropAction.REPLACE, external=DropAction.INSERT
    )
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.query_drop_modifiers",
        return_value=Qt.NoModifier,
    )
    assert manager._is_replace(True) is True
    assert manager._is_replace(False) is False


def _file_drag_event():
    return SimpleNamespace(
        mimeData=lambda: SimpleNamespace(
            hasFormat=lambda fmt: fmt == "text/uri-list",
            hasUrls=lambda: True,
            urls=lambda: [
                SimpleNamespace(
                    isLocalFile=lambda: False,
                    url=lambda: "http://example.com/video.mp4",
                )
            ],
            hasText=lambda: False,
            formats=lambda: ["text/uri-list"],
        ),
        acceptProposedAction=lambda: None,
        pos=lambda: QPoint(1, 1),
        keyboardModifiers=lambda: Qt.NoModifier,
        proposedAction=lambda: Qt.CopyAction,
        possibleActions=lambda: Qt.CopyAction,
    )


def test_drag_leave_ends_drag_ui_after_event_loop(mocker):
    manager, _parent = _make_manager()
    manager._ctx.is_drag_ui = True
    mocker.patch.object(manager, "_is_pointer_over_player", return_value=False)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))

    assert ended == []
    assert manager._drag_leave_timer.isActive()

    QApplication.processEvents()

    assert ended == [False]
    assert not manager._drag_leave_timer.isActive()


def test_drag_leave_while_over_player_keeps_drag_ui(mocker):
    manager, _parent = _make_manager()
    manager._ctx.is_drag_ui = True
    mocker.patch.object(manager, "_is_pointer_over_player", return_value=True)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))
    QApplication.processEvents()

    assert ended == []


def test_drag_enter_after_leave_keeps_drag_ui(mocker):
    manager, parent = _make_manager()
    manager._ctx.is_drag_ui = True
    _patch_drop_settings(mocker)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))
    assert manager._drag_leave_timer.isActive()

    assert manager.dragEnterEvent(_file_drag_event(), parent) is True
    assert not manager._drag_leave_timer.isActive()

    QApplication.processEvents()

    assert ended == []


def test_fake_drag_leave_does_not_end_drag_ui(mocker):
    manager, _parent = _make_manager()
    manager._ctx.is_drag_ui = True
    manager._is_fake_drag_active = True
    mocker.patch.object(manager, "_is_pointer_over_player", return_value=False)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))
    QApplication.processEvents()

    assert ended == []
    assert not manager._drag_leave_timer.isActive()
