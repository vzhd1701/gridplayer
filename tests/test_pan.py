from operator import attrgetter
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QWidget

import gridplayer.player.managers.pan as pan_module
import gridplayer.utils.keymap as keymap_module
from gridplayer.models.keymap_overrides import KeymapOverrides
from gridplayer.params.gestures import GESTURE_PAN
from gridplayer.params.static import VideoShift
from gridplayer.player.managers.pan import PanManager
from gridplayer.widgets.video_overlay_elements import OverlayBar


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Cursor:
    """Where the pointer is, as the manager reads it."""

    at = QPoint(100, 100)

    @classmethod
    def pos(cls):
        return QPoint(cls.at)


class _Block:
    def __init__(self, left_over=(0.0, 0.0)):
        self.is_video_initialized = True
        self.video_tracks = {1: object()}
        self.video_params = SimpleNamespace(shift=VideoShift(0, 0))

        self.pans = []
        self.shifts = []
        self.synced = []
        self._left_over = left_over
        # the block's view part, done by the fake itself
        self.view = self

    def manual_view(self, command, *args):
        # as VideoBlock does, the others following where their views are synced
        self.synced.append(command)
        return attrgetter(command)(self)(*args)

    def pan_by(self, moved_x, moved_y):
        self.pans.append((moved_x, moved_y))
        return self._left_over

    def set_shift(self, shift, is_silent=False):
        self.shifts.append((shift, is_silent))


_TRIGGER = {"value": ["Middle-Drag"]}


def _trigger(*drags):
    _TRIGGER["value"] = list(drags)


@pytest.fixture(autouse=True)
def _pointer(monkeypatch):
    _Cursor.at = QPoint(100, 100)
    _trigger("Middle-Drag")
    monkeypatch.setattr(pan_module, "QCursor", _Cursor)
    monkeypatch.setattr(pan_module, "is_modal_open", lambda: False)
    monkeypatch.setattr(
        keymap_module,
        "Settings",
        lambda: SimpleNamespace(
            get=lambda _key: KeymapOverrides({GESTURE_PAN: _TRIGGER["value"]})
        ),
    )
    monkeypatch.setattr(
        QApplication, "queryKeyboardModifiers", lambda: Qt.KeyboardModifier.NoModifier
    )
    monkeypatch.setattr(QApplication, "widgetAt", lambda *_: None)

    yield

    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def _manager(block, player=None):
    context = SimpleNamespace(
        commands=SimpleNamespace(get_video_block_under_mouse=lambda: block)
    )
    return PanManager(context=context, parent=player)


def _event(
    kind,
    button=Qt.MouseButton.MiddleButton,
    buttons=Qt.MouseButton.MiddleButton,
    keys=Qt.KeyboardModifier.NoModifier,
):
    return QMouseEvent(kind, QPointF(0, 0), button, buttons, keys)


def _press(
    manager, button=Qt.MouseButton.MiddleButton, keys=Qt.KeyboardModifier.NoModifier
):
    return manager.mouse_press(
        _event(QEvent.Type.MouseButtonPress, button, button, keys)
    )


def _move_to(manager, x, y, buttons=Qt.MouseButton.MiddleButton):
    _Cursor.at = QPoint(x, y)
    return manager.mouse_move(
        _event(QEvent.Type.MouseMove, Qt.MouseButton.NoButton, buttons)
    )


def _release(manager, button=Qt.MouseButton.MiddleButton):
    return manager.mouse_release(
        _event(QEvent.Type.MouseButtonRelease, button, Qt.MouseButton.NoButton)
    )


def test_a_drag_takes_the_picture_along():
    block = _Block()
    manager = _manager(block)

    _press(manager)

    assert _move_to(manager, 130, 90) is True
    assert _move_to(manager, 140, 95) is True

    # from where the button went down
    assert block.pans == [(30, -10), (10, 5)]
    assert QApplication.overrideCursor().shape() == Qt.CursorShape.ClosedHandCursor
    # each move for the others to follow, where their views are synced
    assert block.synced == ["view.pan_by", "view.pan_by"]


def test_what_is_left_over_goes_on_to_the_next_move():
    block = _Block(left_over=(0.5, -0.25))
    manager = _manager(block)

    _press(manager)
    _move_to(manager, 120, 100)
    _move_to(manager, 121, 100)

    assert block.pans == [(20, 0), (1.5, -0.25)]


def test_letting_go_says_where_the_picture_is_and_is_not_a_click():
    block = _Block()
    block.video_params.shift = VideoShift(-40, 12)
    manager = _manager(block)

    _press(manager)
    _move_to(manager, 150, 100)

    assert _release(manager) is True
    assert block.shifts == [(VideoShift(-40, 12), False)]
    assert QApplication.overrideCursor() is None


def test_a_click_without_a_drag_is_left_to_the_keymap():
    block = _Block()
    manager = _manager(block)

    _press(manager)
    # jitter within the drag distance
    _move_to(manager, 101, 101)

    assert _release(manager) is None
    assert block.pans == []
    assert block.shifts == []


def test_other_buttons_are_left_alone():
    block = _Block()
    manager = _manager(block)

    _press(manager, Qt.MouseButton.LeftButton)

    assert _move_to(manager, 200, 100, buttons=Qt.MouseButton.LeftButton) is None
    assert block.pans == []


@pytest.mark.parametrize(
    "block",
    [
        None,
        _Block(),
    ],
)
def test_nothing_is_dragged_where_there_is_no_picture(block):
    if block is not None:
        block.video_tracks = {}

    manager = _manager(block)

    _press(manager)

    assert _move_to(manager, 200, 100) is None


def test_nothing_is_dragged_under_a_dialog(monkeypatch):
    monkeypatch.setattr(pan_module, "is_modal_open", lambda: True)
    block = _Block()
    manager = _manager(block)

    _press(manager)

    assert _move_to(manager, 200, 100) is None
    assert block.pans == []


def test_a_release_that_never_came_ends_the_drag():
    block = _Block()
    manager = _manager(block)

    _press(manager)
    _move_to(manager, 150, 100)

    assert _move_to(manager, 170, 100, buttons=Qt.MouseButton.NoButton) is None
    assert QApplication.overrideCursor() is None
    assert block.pans == [(50, 0)]


def test_the_same_press_seen_again_does_not_start_over():
    """The filter sees a press once for every widget it is passed up to."""

    block = _Block()
    manager = _manager(block)

    _press(manager)
    _move_to(manager, 150, 100)
    _press(manager)
    _move_to(manager, 160, 100)

    assert block.pans == [(50, 0), (10, 0)]


class _Recorder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.seen = []

    def mouseMoveEvent(self, event):
        self.seen.append(QEvent.Type.MouseMove)

    def mouseReleaseEvent(self, event):
        self.seen.append(QEvent.Type.MouseButtonRelease)


def _to_window(widget, kind, x, y, button, buttons):
    """As the platform delivers it: to the window, which finds the widget."""

    local = QPoint(x, y)
    _Cursor.at = widget.mapToGlobal(local)

    QApplication.sendEvent(
        widget.windowHandle(),
        QMouseEvent(
            kind,
            QPointF(local),
            QPointF(local),
            QPointF(_Cursor.at),
            button,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def test_after_a_drag_the_pointer_is_heard_where_it_is():
    """Not still by the video pressed on: the overlay's bars, over it in a
    window of their own, would not follow the pointer until the next click."""

    player = QWidget()
    player.setGeometry(0, 0, 200, 200)
    video = _Recorder(player)
    video.setGeometry(player.rect())

    overlay = QWidget()
    overlay.setGeometry(300, 0, 200, 200)
    bar = _Recorder(overlay)
    bar.setGeometry(0, 150, 200, 20)

    player.show()
    overlay.show()

    block = _Block()
    manager = _manager(block, player)
    QApplication.instance().installEventFilter(manager)

    try:
        _to_window(
            player,
            QEvent.Type.MouseButtonPress,
            50,
            50,
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.MiddleButton,
        )
        _to_window(
            player,
            QEvent.Type.MouseMove,
            90,
            50,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.MiddleButton,
        )
        _to_window(
            player,
            QEvent.Type.MouseButtonRelease,
            90,
            50,
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.NoButton,
        )

        _to_window(
            overlay,
            QEvent.Type.MouseMove,
            20,
            160,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
        )
    finally:
        QApplication.instance().removeEventFilter(manager)
        player.close()
        overlay.close()

    assert block.pans == [(40, 0)]
    # the drag and its release are the picture's, never the video's
    assert video.seen == []
    assert bar.seen == [QEvent.Type.MouseMove]


@pytest.mark.parametrize(
    ("trigger", "keys"),
    [
        ("Ctrl+Drag", Qt.KeyboardModifier.ControlModifier),
        ("Shift+Drag", Qt.KeyboardModifier.ShiftModifier),
        ("Alt+Drag", Qt.KeyboardModifier.AltModifier),
    ],
)
def test_the_left_button_drags_with_the_key_it_is_set_to(trigger, keys):
    _trigger(trigger)
    block = _Block()
    manager = _manager(block)

    _press(manager, Qt.MouseButton.LeftButton, keys)
    _move_to(manager, 150, 100, buttons=Qt.MouseButton.LeftButton)

    assert block.pans == [(50, 0)]
    assert _release(manager, Qt.MouseButton.LeftButton) is True


def test_without_the_key_the_left_button_is_left_to_moving_the_cell():
    _trigger("Ctrl+Drag")
    block = _Block()
    manager = _manager(block)

    assert not manager.is_pan_press(
        _event(
            QEvent.Type.MouseButtonPress,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
    )

    _press(manager, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)

    assert _move_to(manager, 150, 100, buttons=Qt.MouseButton.LeftButton) is None
    assert block.pans == []


def test_set_to_a_key_the_middle_button_does_nothing():
    _trigger("Ctrl+Drag")
    block = _Block()
    manager = _manager(block)

    _press(manager, Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.ControlModifier)

    assert _move_to(manager, 150, 100) is None


def test_a_key_held_down_is_seen_where_the_press_does_not_say(monkeypatch):
    """As a drop sees it: the press into a window that was not focused."""

    _trigger("Ctrl+Drag")
    monkeypatch.setattr(
        QApplication,
        "queryKeyboardModifiers",
        lambda: Qt.KeyboardModifier.ControlModifier,
    )
    block = _Block()
    manager = _manager(block)

    assert manager.is_pan_press(
        _event(
            QEvent.Type.MouseButtonPress,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
    )


def test_the_overlay_s_buttons_and_bars_keep_their_left_press(monkeypatch):
    _trigger("Ctrl+Drag")
    bar = OverlayBar()
    monkeypatch.setattr(QApplication, "widgetAt", lambda *_: bar)
    manager = _manager(_Block())

    left = _event(
        QEvent.Type.MouseButtonPress,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
    )
    left_with_key = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
    )

    assert not manager.is_pan_press(left)
    assert not manager.is_pan_press(left_with_key)


def test_the_middle_button_drags_over_the_overlay_too(monkeypatch):
    """Its buttons and bars only answer the left one."""

    monkeypatch.setattr(QApplication, "widgetAt", lambda *_: OverlayBar())
    manager = _manager(_Block())

    assert manager.is_pan_press(_event(QEvent.Type.MouseButtonPress))


def test_disabled_nothing_drags_the_picture():
    _trigger()
    block = _Block()
    manager = _manager(block)

    for button, keys in (
        (Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier),
        (Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier),
    ):
        _press(manager, button, keys)

        assert _move_to(manager, 150, 100, buttons=button) is None

    assert block.pans == []


def test_more_keys_held_than_the_drag_has_are_another_drag():
    _trigger("Ctrl+Drag")
    block = _Block()
    manager = _manager(block)

    _press(
        manager,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    assert _move_to(manager, 150, 100, buttons=Qt.MouseButton.LeftButton) is None
    assert block.pans == []


def test_any_of_the_drags_it_is_set_to_drags_the_picture():
    _trigger("Ctrl+Drag", "Back-Drag")
    manager = _manager(_Block())

    for button, keys in (
        (Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier),
        (Qt.MouseButton.BackButton, Qt.KeyboardModifier.NoModifier),
    ):
        assert manager.is_pan_press(
            _event(QEvent.Type.MouseButtonPress, button, button, keys)
        )

    assert not manager.is_pan_press(_event(QEvent.Type.MouseButtonPress))


def test_it_is_set_in_the_keymap_middle_by_default():
    """The same for every playlist: a way of using the mouse, not a video's."""

    from gridplayer.params.settings_fields.playlist import PLAYLIST_FIELDS
    from gridplayer.utils.keymap import default_keymap

    assert default_keymap()[GESTURE_PAN] == ["Middle-Drag"]
    assert "pan" not in " ".join(spec.settings_key for spec in PLAYLIST_FIELDS)


def test_it_is_set_on_the_shortcuts_page(mocker):
    from gridplayer.dialogs.settings import SettingsDialog
    from gridplayer.settings import Settings

    dialog = SettingsDialog(None)
    editor = dialog.widget("player/keymap")

    assert dialog.pages["shortcuts"].isAncestorOf(editor)
    assert editor.get_bindings()[GESTURE_PAN] == ["Middle-Drag"]

    editor.tree.set_action_shortcuts(GESTURE_PAN, ["Middle-Drag", "Shift+Drag"])

    written = {}
    mocker.patch.object(
        Settings(),
        "set",
        side_effect=lambda key, value: written.__setitem__(key, value),
    )

    dialog.save_settings()

    assert written["player/keymap"].get(GESTURE_PAN) == ["Middle-Drag", "Shift+Drag"]


class TestAWindowOverThePlayer:
    """The List window, open beside the player and over a video: a drag
    there is its own."""

    def _manager(self, block):
        self.player = QWidget()
        return _manager(block, self.player)

    def test_nothing_is_dragged_from_it(self):
        block = _Block()
        manager = self._manager(block)
        over = QLineEdit(QDialog(self.player))

        manager.eventFilter(over, _event(QEvent.Type.MouseButtonPress))
        _Cursor.at = QPoint(200, 100)
        manager.eventFilter(
            over, _event(QEvent.Type.MouseMove, Qt.MouseButton.NoButton)
        )

        assert block.pans == []

    def test_the_player_s_own_still_drags(self):
        block = _Block()
        manager = self._manager(block)
        cell = QWidget(self.player)

        manager.eventFilter(cell, _event(QEvent.Type.MouseButtonPress))
        _Cursor.at = QPoint(200, 100)
        manager.eventFilter(
            cell, _event(QEvent.Type.MouseMove, Qt.MouseButton.NoButton)
        )

        assert block.pans == [(100, 0)]
