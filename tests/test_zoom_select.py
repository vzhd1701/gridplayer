from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt
from PyQt5.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QWindow
from PyQt5.QtWidgets import QApplication, QWidget

import gridplayer.player.managers.zoom_select as zoom_select_module
from gridplayer.params.static import PanTrigger, ZoomSelectTrigger
from gridplayer.player.managers.zoom_select import ZoomSelectManager


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Cursor:
    """Where the pointer is, as the manager reads it."""

    at = QPoint(100, 100)

    @classmethod
    def pos(cls):
        return QPoint(cls.at)


class _Block(QWidget):
    """A video with a picture over all of it, at the screen's corner."""

    def __init__(self, parent):
        super().__init__(parent)

        self.area = QRect(0, 0, 900, 600)
        self.is_control_pressed = False
        self.overlay = SimpleNamespace(
            is_control_at=lambda _pos: self.is_control_pressed
        )

        self.shown = []
        self.zooms = []
        self.hints = []

    def mapFromGlobal(self, pos):
        return QPoint(pos)

    def zoom_selection_area(self):
        return self.area

    def show_zoom_selection(self, selection):
        self.shown.append(selection)

    def zoom_to_selection(self, selection):
        self.zooms.append(selection)

    def show_zoom_hint(self, is_shown):
        self.hints.append(is_shown)


_SETTINGS = {}


def _trigger(trigger, pan=PanTrigger.MIDDLE):
    _SETTINGS["player/zoom_select_trigger"] = trigger
    _SETTINGS["player/pan_trigger"] = pan


@pytest.fixture(autouse=True)
def _pointer(monkeypatch):
    _Cursor.at = QPoint(100, 100)
    _trigger(ZoomSelectTrigger.CTRL)
    monkeypatch.setattr(zoom_select_module, "QCursor", _Cursor)
    monkeypatch.setattr(zoom_select_module, "is_modal_open", lambda: False)
    monkeypatch.setattr(
        zoom_select_module,
        "Settings",
        lambda: SimpleNamespace(get=_SETTINGS.__getitem__),
    )
    monkeypatch.setattr(QApplication, "queryKeyboardModifiers", lambda: Qt.NoModifier)

    yield

    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


@pytest.fixture
def player():
    player = QWidget()

    yield player

    player.deleteLater()


@pytest.fixture
def block(player):
    return _Block(player)


@pytest.fixture
def manager(player, block):
    under_mouse = {"block": block}
    context = SimpleNamespace(
        commands=SimpleNamespace(
            get_video_block_under_mouse=lambda: under_mouse["block"],
        ),
        under_mouse=under_mouse,
        active_block=block,
    )
    return ZoomSelectManager(context=context, parent=player)


def _window_move(manager, x, y, buttons=Qt.NoButton):
    """A move as the window has it, before Qt picks a widget for it."""

    _Cursor.at = QPoint(x, y)

    return manager.eventFilter(
        QWindow(), _event(QEvent.MouseMove, Qt.NoButton, buttons)
    )


def _event(kind, button, buttons, keys=Qt.NoModifier):
    return QMouseEvent(kind, QPointF(0, 0), button, buttons, keys)


def _press(manager, pressed, button=Qt.LeftButton, keys=Qt.ControlModifier):
    event = _event(QEvent.MouseButtonPress, button, button, keys)

    return manager.mouse_press(event, pressed)


def _move_to(manager, x, y, buttons=Qt.LeftButton):
    _Cursor.at = QPoint(x, y)

    return manager.mouse_move(_event(QEvent.MouseMove, Qt.NoButton, buttons))


def _release(manager, button=Qt.LeftButton):
    """As Qt has it: to the window first, then to the widget, if any."""

    event = _event(QEvent.MouseButtonRelease, button, Qt.NoButton)
    manager.window_release(event)

    return manager.mouse_release(event)


def _key(manager, kind, key=Qt.Key_Escape):
    event = QKeyEvent(kind, key, Qt.NoModifier)

    if kind == QEvent.ShortcutOverride:
        event.ignore()
        return manager.shortcut_override(event), event.isAccepted()

    return manager.key_press(event)


def _context_menu(manager):
    return manager.context_menu(QContextMenuEvent(QContextMenuEvent.Mouse, QPoint()))


def _cursor_shape():
    cursor = QApplication.overrideCursor()

    return None if cursor is None else cursor.shape()


class TestWithTheKey:
    def test_a_drag_selects_and_letting_go_zooms_to_it(self, manager, block):
        assert _press(manager, block) is True

        assert _move_to(manager, 300, 250) is True
        assert _move_to(manager, 400, 300) is True
        assert _cursor_shape() == Qt.CrossCursor

        assert _release(manager) is True

        assert block.shown == [
            QRect(100, 100, 200, 150),
            QRect(100, 100, 300, 200),
            None,
        ]
        assert block.zooms == [QRect(100, 100, 300, 200)]
        assert _cursor_shape() is None

    def test_dragged_up_and_left_it_is_the_same(self, manager, block):
        _press(manager, block)
        _move_to(manager, 40, 20)
        _release(manager)

        assert block.zooms == [QRect(40, 20, 60, 80)]

    def test_it_is_held_to_the_picture(self, manager, block):
        """Letterboxed: from 150 down to 450."""

        block.area = QRect(0, 150, 900, 300)

        _press(manager, block)
        _move_to(manager, 500, 700)
        _release(manager)

        assert block.zooms == [QRect(100, 150, 400, 300)]

    def test_over_no_picture_at_all_nothing_is_zoomed(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 100)
        _release(manager)

        assert block.zooms == []

    def test_a_click_without_a_drag_is_left_to_the_keymap(self, manager, block):
        _press(manager, block)
        # jitter within the drag distance, which is not the video's to drag
        assert _move_to(manager, 101, 101) is True

        assert _release(manager) is None
        assert block.shown == []
        assert block.zooms == []

    @pytest.mark.parametrize(
        ("trigger", "keys"),
        [
            (ZoomSelectTrigger.CTRL, Qt.ControlModifier),
            (ZoomSelectTrigger.SHIFT, Qt.ShiftModifier),
            (ZoomSelectTrigger.ALT, Qt.AltModifier),
        ],
    )
    def test_the_left_button_selects_with_the_key_it_is_set_to(
        self, manager, block, trigger, keys
    ):
        _trigger(trigger)

        assert _press(manager, block, keys=keys) is True

    def test_without_the_key_a_press_is_left_alone(self, manager, block):
        assert _press(manager, block, keys=Qt.ShiftModifier) is None
        assert _move_to(manager, 300, 300) is None

    def test_a_key_held_down_is_seen_where_the_press_does_not_say(
        self, manager, block, monkeypatch
    ):
        monkeypatch.setattr(
            QApplication, "queryKeyboardModifiers", lambda: Qt.ControlModifier
        )

        assert _press(manager, block, keys=Qt.NoModifier) is True

    def test_set_to_the_middle_button_it_selects_with_that(self, manager, block):
        _trigger(ZoomSelectTrigger.MIDDLE, pan=PanTrigger.CTRL)

        assert _press(manager, block, Qt.LeftButton, Qt.ControlModifier) is None
        assert _press(manager, block, Qt.MiddleButton, Qt.NoModifier) is True

        _move_to(manager, 300, 300, buttons=Qt.MiddleButton)

        assert _release(manager, Qt.MiddleButton) is True
        assert block.zooms == [QRect(100, 100, 200, 200)]

    def test_off_by_default_nothing_selects(self, manager, block):
        from gridplayer.settings import _default_settings

        _trigger(_default_settings["player/zoom_select_trigger"])

        assert _default_settings["player/zoom_select_trigger"] is (
            ZoomSelectTrigger.NONE
        )
        assert _press(manager, block) is None
        assert _press(manager, block, Qt.MiddleButton, Qt.NoModifier) is None

    def test_what_moves_the_picture_about_does_not_select(self, manager, block):
        """The settings do not let the two be the same; set so anyway, the
        picture is moved, as it was before there was a selection."""

        _trigger(ZoomSelectTrigger.CTRL, pan=PanTrigger.CTRL)

        assert _press(manager, block) is None

    def test_the_overlay_s_controls_keep_their_press(self, manager, block):
        block.is_control_pressed = True

        assert _press(manager, block) is None

    def test_nothing_is_selected_where_there_is_no_picture(self, manager, block):
        block.area = None

        assert _press(manager, block) is None

    def test_nothing_is_selected_where_there_is_no_video(self, manager, block):
        manager._ctx.under_mouse["block"] = None

        assert _press(manager, block) is None

    def test_nothing_is_selected_under_a_dialog(self, manager, block, monkeypatch):
        monkeypatch.setattr(zoom_select_module, "is_modal_open", lambda: True)

        assert _press(manager, block) is None

    def test_a_window_over_the_video_keeps_its_press(self, manager, block, player):
        """Such as the bookmarks of the video, which belong to it."""

        window = QWidget(block, Qt.Window)

        assert _press(manager, window) is None

    def test_the_overlay_s_own_window_is_the_video_s(self, manager, block):
        overlay = QWidget(block, Qt.Window)
        block.overlay.is_control_at = lambda _pos: False
        inside = QWidget(overlay)
        block.overlay = overlay
        overlay.is_control_at = lambda _pos: False

        assert _press(manager, inside) is True

    def test_the_same_press_seen_again_does_not_start_over(self, manager, block):
        _press(manager, block)
        _move_to(manager, 200, 200)

        assert _press(manager, block) is True

        _move_to(manager, 300, 300)
        _release(manager)

        assert block.zooms == [QRect(100, 100, 200, 200)]

    def test_qt_s_own_move_to_a_widget_is_no_letting_go(self, manager, block):
        """The chrome hidden from under the pointer as the selecting starts,
        Qt tells the widget under it with a move with no button held."""

        _press(manager, block)
        _move_to(manager, 300, 300)

        made_up = _event(QEvent.MouseMove, Qt.NoButton, Qt.NoButton)

        assert manager.eventFilter(block, made_up) is True

        _move_to(manager, 400, 300)
        _release(manager)

        assert block.zooms == [QRect(100, 100, 300, 200)]

    def test_let_go_of_with_the_widget_pressed_on_gone_it_zooms(self, manager, block):
        """The overlay's chrome is hidden for the selecting: pressed on it,
        Qt hands the release to no widget at all, only to the window."""

        _press(manager, block)
        _move_to(manager, 300, 300)

        manager.window_release(
            _event(QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton)
        )

        assert block.zooms == [QRect(100, 100, 200, 200)]
        assert _cursor_shape() is None

        # nor is the next click lost to it
        _press(manager, block, keys=Qt.NoModifier)

        assert _release(manager) is None

    def test_a_release_that_never_came_ends_it(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 300)

        assert _move_to(manager, 350, 350, buttons=Qt.NoButton) is None
        assert block.shown[-1] is None
        assert block.zooms == []
        assert _cursor_shape() is None

    def test_a_video_gone_meanwhile_is_let_go_of(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 300)

        sip.delete(block)

        assert _cursor_shape() is None
        assert _move_to(manager, 350, 350) is None
        assert _release(manager) is None


class TestLettingGo:
    def test_esc_lets_go_of_it_rather_than_what_it_is_bound_to(self, manager, block):
        """Esc minimizes the window otherwise."""

        _press(manager, block)
        _move_to(manager, 300, 300)

        assert _key(manager, QEvent.ShortcutOverride) == (True, True)
        assert _key(manager, QEvent.KeyPress) is True

        assert block.shown[-1] is None
        assert _cursor_shape() is None

        # nor is letting go of the button a click
        assert _release(manager) is True
        assert block.zooms == []

    def test_other_keys_are_left_alone(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 300)

        assert _key(manager, QEvent.ShortcutOverride, Qt.Key_Space) == (None, False)
        assert _key(manager, QEvent.KeyPress, Qt.Key_Space) is None

    def test_esc_with_nothing_going_on_is_left_alone(self, manager):
        assert _key(manager, QEvent.ShortcutOverride) == (None, False)
        assert _key(manager, QEvent.KeyPress) is None

    def test_the_right_button_lets_go_of_it_with_no_menu(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 300)

        assert _press(manager, block, Qt.RightButton, Qt.NoModifier) is True
        assert block.shown[-1] is None

        assert _release(manager, Qt.RightButton) is True
        assert _context_menu(manager) is True
        assert _release(manager) is True
        assert block.zooms == []

        # the next one is a menu again
        assert _context_menu(manager) is None
        assert _release(manager) is None

    def test_a_release_let_go_of_elsewhere_is_not_waited_for(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 300)
        _key(manager, QEvent.KeyPress)

        # the left button's release never came: it is up at the next press
        _press(manager, block, Qt.RightButton, Qt.NoModifier)

        assert _release(manager) is None


class TestTheHint:
    """Once picked from the menu, the video says how to select."""

    @pytest.fixture
    def other(self, player):
        return _Block(player)

    def test_picked_the_video_it_was_picked_for_says_how(self, manager, block):
        manager.arm()

        assert block.hints == [True]

    def test_it_goes_to_the_video_the_pointer_goes_to(self, manager, block, other):
        manager.arm()

        manager._ctx.under_mouse["block"] = other

        assert _window_move(manager, 500, 300) is False
        assert block.hints == [True, False]
        assert other.hints == [True]

    def test_off_the_videos_the_last_one_goes_on_saying_it(self, manager, block):
        manager.arm()

        manager._ctx.under_mouse["block"] = None
        _window_move(manager, 2000, 2000)

        assert block.hints == [True]

    def test_a_video_with_no_picture_says_nothing(self, manager, block, other):
        block.area = None

        manager.arm()

        assert block.hints == []

        manager._ctx.under_mouse["block"] = other
        _window_move(manager, 500, 300)

        assert other.hints == [True]

    def test_the_selecting_started_the_outline_says_it(self, manager, block):
        manager.arm()
        _press(manager, block, keys=Qt.NoModifier)

        assert block.hints == [True]

        _move_to(manager, 300, 300)

        assert block.hints == [True, False]
        assert block.shown == [QRect(100, 100, 200, 200)]

    @pytest.mark.parametrize(
        "let_go",
        [
            lambda manager: manager.arm(),
            lambda manager: _key(manager, QEvent.KeyPress),
            lambda manager: _context_menu(manager),
        ],
    )
    def test_let_go_of_it_says_no_more(self, manager, block, let_go):
        manager.arm()

        let_go(manager)

        assert block.hints == [True, False]

    def test_a_video_gone_meanwhile_is_let_go_of(self, manager, block):
        manager.arm()

        sip.delete(block)
        manager.arm()

        assert _cursor_shape() is None

    def test_with_the_key_held_there_is_none(self, manager, block):
        _press(manager, block)
        _move_to(manager, 300, 300)
        _release(manager)

        assert block.hints == []


class TestPickedFromTheMenu:
    def test_the_next_drag_selects_whatever_is_held(self, manager, block):
        _trigger(ZoomSelectTrigger.NONE)

        manager.arm()

        assert _cursor_shape() == Qt.CrossCursor
        assert _press(manager, block, keys=Qt.NoModifier) is True

        _move_to(manager, 300, 300)

        assert _release(manager) is True
        assert block.zooms == [QRect(100, 100, 200, 200)]
        assert _cursor_shape() is None

    def test_only_the_next_one(self, manager, block):
        _trigger(ZoomSelectTrigger.NONE)

        manager.arm()
        _press(manager, block, keys=Qt.NoModifier)
        _move_to(manager, 300, 300)
        _release(manager)

        assert _press(manager, block, keys=Qt.NoModifier) is None

    def test_over_the_overlay_s_controls_too(self, manager, block):
        block.is_control_pressed = True

        manager.arm()

        assert _press(manager, block, keys=Qt.NoModifier) is True

    def test_a_click_is_not_a_click_then_but_not_a_selection_either(
        self, manager, block
    ):
        manager.arm()
        _press(manager, block, keys=Qt.NoModifier)

        assert _release(manager) is True
        assert block.zooms == []
        assert _cursor_shape() is None

    def test_picked_again_it_is_not_after_all(self, manager):
        manager.arm()
        manager.arm()

        assert _cursor_shape() is None
        assert manager._is_armed is False

    def test_esc_lets_go_of_it(self, manager):
        manager.arm()

        assert _key(manager, QEvent.ShortcutOverride) == (True, True)
        assert _key(manager, QEvent.KeyPress) is True
        assert _cursor_shape() is None

    def test_the_right_button_lets_go_of_it_with_no_menu(self, manager, block):
        manager.arm()

        assert _press(manager, block, Qt.RightButton, Qt.NoModifier) is True
        assert _context_menu(manager) is True
        assert _release(manager, Qt.RightButton) is True
        assert _cursor_shape() is None

    def test_a_press_with_no_picture_lets_go_of_it(self, manager, block):
        block.area = None

        manager.arm()

        assert _press(manager, block, keys=Qt.NoModifier) is True
        assert _release(manager) is True
        assert _cursor_shape() is None

    def test_a_press_in_a_window_over_the_player_goes_to_it(self, manager, block):
        window = QWidget(block, Qt.Window)

        manager.arm()

        assert _press(manager, window, keys=Qt.NoModifier) is None
        assert _cursor_shape() is None

    def test_the_menu_s_key_lets_go_of_it(self, manager):
        manager.arm()

        assert _context_menu(manager) is True
        assert _cursor_shape() is None


class _Recorder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.seen = []

    def mousePressEvent(self, event):
        self.seen.append(QEvent.MouseButtonPress)

    def mouseMoveEvent(self, event):
        self.seen.append(QEvent.MouseMove)

    def mouseReleaseEvent(self, event):
        self.seen.append(QEvent.MouseButtonRelease)


def _to_window(widget, kind, x, y, button, buttons, keys=Qt.NoModifier):
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
            keys,
        ),
    )


class _ThenTheDrag(QObject):
    """The player's filters in their order: the selection's, then the one
    that drags a video to another cell, which sees what the selection lets
    through, at the window as well as at the widget."""

    def __init__(self, manager):
        super().__init__()

        self.manager = manager
        self.drag_saw = []

    def eventFilter(self, event_object, event):
        if self.manager.eventFilter(event_object, event):
            return True

        if event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
            self.drag_saw.append(type(event_object).__name__)

        return False


@pytest.fixture
def real_player():
    """A video in a window, events sent to the window as the platform does."""

    player = QWidget()
    player.setGeometry(0, 0, 400, 400)
    block = _Block(player)
    block.setGeometry(player.rect())
    video = _Recorder(block)
    video.setGeometry(block.rect())

    other = QWidget()
    other.setGeometry(500, 0, 200, 200)
    bar = _Recorder(other)
    bar.setGeometry(0, 150, 200, 20)

    player.show()
    other.show()

    block.mapFromGlobal = lambda pos: QWidget.mapFromGlobal(block, pos)

    context = SimpleNamespace(
        commands=SimpleNamespace(get_video_block_under_mouse=lambda: block)
    )
    manager = ZoomSelectManager(context=context, parent=player)
    filters = _ThenTheDrag(manager)
    QApplication.instance().installEventFilter(filters)

    yield SimpleNamespace(
        player=player,
        block=block,
        video=video,
        other=other,
        bar=bar,
        filters=filters,
    )

    QApplication.instance().removeEventFilter(filters)
    player.close()
    other.close()


def _ctrl_press(player, x, y):
    _to_window(
        player,
        QEvent.MouseButtonPress,
        x,
        y,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.ControlModifier,
    )


def test_a_selection_is_nothing_else_s_and_then_the_pointer_is_heard_again(
    real_player,
):
    """Not a press, a drag or a click of the video's, which would move it to
    another cell or pause it; nor still the video's once let go of."""

    r = real_player

    _ctrl_press(r.player, 50, 50)
    _to_window(r.player, QEvent.MouseMove, 52, 51, Qt.NoButton, Qt.LeftButton)
    _to_window(r.player, QEvent.MouseMove, 150, 120, Qt.NoButton, Qt.LeftButton)
    _to_window(
        r.player, QEvent.MouseButtonRelease, 150, 120, Qt.LeftButton, Qt.NoButton
    )

    _to_window(r.other, QEvent.MouseMove, 20, 160, Qt.NoButton, Qt.NoButton)

    assert r.block.zooms == [QRect(50, 50, 100, 70)]
    assert r.video.seen == []
    # the drag saw the press at the window, and would go from there
    assert r.filters.drag_saw == []
    assert r.bar.seen == [QEvent.MouseMove]


def test_let_go_of_the_button_held_is_still_not_a_drag(real_player):
    r = real_player

    _ctrl_press(r.player, 50, 50)
    _to_window(r.player, QEvent.MouseMove, 150, 120, Qt.NoButton, Qt.LeftButton)
    QApplication.sendEvent(
        r.player, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    )
    _to_window(r.player, QEvent.MouseMove, 250, 220, Qt.NoButton, Qt.LeftButton)
    _to_window(
        r.player, QEvent.MouseButtonRelease, 250, 220, Qt.LeftButton, Qt.NoButton
    )

    assert r.block.zooms == []
    assert r.filters.drag_saw == []
    assert r.video.seen == []


class TestTheSetting:
    def test_it_is_chosen_beside_moving_the_picture(self):
        from gridplayer.dialogs.settings import SettingsDialog
        from gridplayer.settings import Settings

        dialog = SettingsDialog(None)
        combo = dialog.playerZoomSelectTrigger

        assert combo.parent() is dialog.page_general_shortcuts
        assert [combo.itemData(i) for i in range(combo.count())] == list(
            ZoomSelectTrigger
        )
        assert combo.currentData() == Settings().get("player/zoom_select_trigger")

    def test_what_one_has_the_other_has_greyed_out(self):
        from gridplayer.dialogs.settings import SettingsDialog

        dialog = SettingsDialog(None)
        pan, zoom = dialog.playerPanTrigger, dialog.playerZoomSelectTrigger

        def enabled(combo):
            return [
                combo.itemData(i).name
                for i in range(combo.count())
                if combo.model().item(i).isEnabled()
            ]

        pan.setCurrentIndex(pan.findData(PanTrigger.MIDDLE))
        zoom.setCurrentIndex(zoom.findData(ZoomSelectTrigger.CTRL))

        assert enabled(zoom) == ["CTRL", "SHIFT", "ALT", "NONE"]
        assert enabled(pan) == ["MIDDLE", "SHIFT", "ALT", "NONE"]

        # off, neither takes anything from the other
        zoom.setCurrentIndex(zoom.findData(ZoomSelectTrigger.NONE))
        pan.setCurrentIndex(pan.findData(PanTrigger.NONE))

        assert enabled(zoom) == [t.name for t in ZoomSelectTrigger]
        assert enabled(pan) == [t.name for t in PanTrigger]

    def test_it_is_saved(self, mocker):
        from gridplayer.dialogs.settings import SettingsDialog
        from gridplayer.settings import Settings

        dialog = SettingsDialog(None)
        combo = dialog.playerZoomSelectTrigger
        combo.setCurrentIndex(combo.findData(ZoomSelectTrigger.SHIFT))

        written = {}
        mocker.patch.object(
            Settings(),
            "set",
            side_effect=lambda key, value: written.__setitem__(key, value),
        )

        dialog.save_settings()

        assert written["player/zoom_select_trigger"] is ZoomSelectTrigger.SHIFT
