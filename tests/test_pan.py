from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QWidget

import gridplayer.player.managers.pan as pan_module
from gridplayer.params.static import PanTrigger, VideoShift
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
        self._left_over = left_over

    def pan_by(self, moved_x, moved_y):
        self.pans.append((moved_x, moved_y))
        return self._left_over

    def set_shift(self, shift, is_silent=False):
        self.shifts.append((shift, is_silent))


_TRIGGER = {"value": PanTrigger.MIDDLE}


def _trigger(trigger):
    _TRIGGER["value"] = trigger


@pytest.fixture(autouse=True)
def _pointer(monkeypatch):
    _Cursor.at = QPoint(100, 100)
    _trigger(PanTrigger.MIDDLE)
    monkeypatch.setattr(pan_module, "QCursor", _Cursor)
    monkeypatch.setattr(pan_module, "is_modal_open", lambda: False)
    monkeypatch.setattr(
        pan_module,
        "Settings",
        lambda: SimpleNamespace(get=lambda _key: _TRIGGER["value"]),
    )
    monkeypatch.setattr(QApplication, "queryKeyboardModifiers", lambda: Qt.NoModifier)
    monkeypatch.setattr(QApplication, "widgetAt", lambda *_: None)

    yield

    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def _manager(block):
    context = SimpleNamespace(
        commands=SimpleNamespace(get_video_block_under_mouse=lambda: block)
    )
    return PanManager(context=context)


def _event(kind, button=Qt.MiddleButton, buttons=Qt.MiddleButton, keys=Qt.NoModifier):
    return QMouseEvent(kind, QPointF(0, 0), button, buttons, keys)


def _press(manager, button=Qt.MiddleButton, keys=Qt.NoModifier):
    return manager.mouse_press(_event(QEvent.MouseButtonPress, button, button, keys))


def _move_to(manager, x, y, buttons=Qt.MiddleButton):
    _Cursor.at = QPoint(x, y)
    return manager.mouse_move(_event(QEvent.MouseMove, Qt.NoButton, buttons))


def _release(manager, button=Qt.MiddleButton):
    return manager.mouse_release(_event(QEvent.MouseButtonRelease, button, Qt.NoButton))


def test_a_drag_takes_the_picture_along():
    block = _Block()
    manager = _manager(block)

    _press(manager)

    assert _move_to(manager, 130, 90) is True
    assert _move_to(manager, 140, 95) is True

    # from where the button went down
    assert block.pans == [(30, -10), (10, 5)]
    assert QApplication.overrideCursor().shape() == Qt.ClosedHandCursor


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

    _press(manager, Qt.LeftButton)

    assert _move_to(manager, 200, 100, buttons=Qt.LeftButton) is None
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

    assert _move_to(manager, 170, 100, buttons=Qt.NoButton) is None
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
        self.seen.append(QEvent.MouseMove)

    def mouseReleaseEvent(self, event):
        self.seen.append(QEvent.MouseButtonRelease)


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
            Qt.NoModifier,
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
    manager = _manager(block)
    QApplication.instance().installEventFilter(manager)

    try:
        _to_window(
            player, QEvent.MouseButtonPress, 50, 50, Qt.MiddleButton, Qt.MiddleButton
        )
        _to_window(player, QEvent.MouseMove, 90, 50, Qt.NoButton, Qt.MiddleButton)
        _to_window(
            player, QEvent.MouseButtonRelease, 90, 50, Qt.MiddleButton, Qt.NoButton
        )

        _to_window(overlay, QEvent.MouseMove, 20, 160, Qt.NoButton, Qt.NoButton)
    finally:
        QApplication.instance().removeEventFilter(manager)
        player.close()
        overlay.close()

    assert block.pans == [(40, 0)]
    # the drag and its release are the picture's, never the video's
    assert video.seen == []
    assert bar.seen == [QEvent.MouseMove]


@pytest.mark.parametrize(
    ("trigger", "keys"),
    [
        (PanTrigger.CTRL, Qt.ControlModifier),
        (PanTrigger.SHIFT, Qt.ShiftModifier),
        (PanTrigger.ALT, Qt.AltModifier),
    ],
)
def test_the_left_button_drags_with_the_key_it_is_set_to(trigger, keys):
    _trigger(trigger)
    block = _Block()
    manager = _manager(block)

    _press(manager, Qt.LeftButton, keys)
    _move_to(manager, 150, 100, buttons=Qt.LeftButton)

    assert block.pans == [(50, 0)]
    assert _release(manager, Qt.LeftButton) is True


def test_without_the_key_the_left_button_is_left_to_moving_the_cell():
    _trigger(PanTrigger.CTRL)
    block = _Block()
    manager = _manager(block)

    assert not manager.is_pan_press(
        _event(QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton)
    )

    _press(manager, Qt.LeftButton, Qt.ShiftModifier)

    assert _move_to(manager, 150, 100, buttons=Qt.LeftButton) is None
    assert block.pans == []


def test_set_to_a_key_the_middle_button_does_nothing():
    _trigger(PanTrigger.CTRL)
    block = _Block()
    manager = _manager(block)

    _press(manager, Qt.MiddleButton, Qt.ControlModifier)

    assert _move_to(manager, 150, 100) is None


def test_a_key_held_down_is_seen_where_the_press_does_not_say(monkeypatch):
    """As a drop sees it: the press into a window that was not focused."""

    _trigger(PanTrigger.CTRL)
    monkeypatch.setattr(
        QApplication, "queryKeyboardModifiers", lambda: Qt.ControlModifier
    )
    block = _Block()
    manager = _manager(block)

    assert manager.is_pan_press(
        _event(QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton)
    )


def test_the_overlay_s_buttons_and_bars_keep_their_left_press(monkeypatch):
    _trigger(PanTrigger.CTRL)
    bar = OverlayBar()
    monkeypatch.setattr(QApplication, "widgetAt", lambda *_: bar)
    manager = _manager(_Block())

    left = _event(QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton)
    left_with_key = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(0, 0),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.ControlModifier,
    )

    assert not manager.is_pan_press(left)
    assert not manager.is_pan_press(left_with_key)


def test_the_middle_button_drags_over_the_overlay_too(monkeypatch):
    """Its buttons and bars only answer the left one."""

    monkeypatch.setattr(QApplication, "widgetAt", lambda *_: OverlayBar())
    manager = _manager(_Block())

    assert manager.is_pan_press(_event(QEvent.MouseButtonPress))


def test_disabled_nothing_drags_the_picture():
    _trigger(PanTrigger.NONE)
    block = _Block()
    manager = _manager(block)

    for button, keys in (
        (Qt.MiddleButton, Qt.NoModifier),
        (Qt.LeftButton, Qt.ControlModifier),
    ):
        _press(manager, button, keys)

        assert _move_to(manager, 150, 100, buttons=button) is None

    assert block.pans == []


def test_it_is_a_player_setting_middle_by_default():
    """The same for every playlist: a way of using the mouse, not a video's."""

    from gridplayer.params.defaults_fields import PLAYLIST_FIELDS
    from gridplayer.settings import _default_settings

    assert _default_settings["player/pan_trigger"] == PanTrigger.MIDDLE
    assert "pan" not in " ".join(spec.settings_key for spec in PLAYLIST_FIELDS)


def test_it_is_chosen_on_the_shortcuts_page(mocker):
    from gridplayer.dialogs.settings import SettingsDialog
    from gridplayer.settings import Settings

    dialog = SettingsDialog(None)
    combo = dialog.playerPanTrigger

    assert combo.parent() is dialog.page_general_shortcuts
    assert [combo.itemData(i) for i in range(combo.count())] == list(PanTrigger)
    assert combo.currentData() == Settings().get("player/pan_trigger")

    combo.setCurrentIndex(combo.findData(PanTrigger.SHIFT))

    written = {}
    mocker.patch.object(
        Settings(),
        "set",
        side_effect=lambda key, value: written.__setitem__(key, value),
    )

    dialog.save_settings()

    assert written["player/pan_trigger"] is PanTrigger.SHIFT
