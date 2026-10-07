"""Drags and the key held through a drop, kept in the keymap with the
shortcuts: see params/gestures.py."""

from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication

import gridplayer.utils.keymap as keymap_module
from gridplayer.models.keymap_overrides import KeymapOverrides
from gridplayer.params.gestures import (
    GESTURE_DROP_SWITCH,
    GESTURE_MOVE_VIDEO,
    GESTURE_PAN,
    GESTURE_ZOOM_SELECT,
)
from gridplayer.utils.keymap import (
    DragProblem,
    MouseButtonSequence,
    default_keymap,
    drag_problem,
    drop_switch_modifier,
    fit_shortcuts,
    gesture_shortcuts,
    is_gesture_press,
    merge_keymap,
    normalize_shortcut,
    sparse_overrides,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_a_drag_is_a_mouse_sequence_of_its_own():
    seq = MouseButtonSequence("Ctrl+Middle-Drag")

    assert seq.is_drag
    assert not seq.is_click
    assert not seq.is_wheel
    assert seq.drag_button == Qt.MiddleButton
    assert seq.modifiers == ["Ctrl"]

    assert MouseButtonSequence("Middle-Click").drag_button is None
    assert MouseButtonSequence("Drag-4").drag_button == Qt.ExtraButton4

    with pytest.raises(ValueError, match="Bad mouse sequence"):
        MouseButtonSequence("Double Drag")


def test_the_keys_are_put_in_one_order():
    assert normalize_shortcut("Shift+Ctrl+Drag") == "Ctrl+Shift+Drag"
    assert normalize_shortcut("Alt+Ctrl+Click") == "Ctrl+Alt+Click"


def test_a_press_makes_the_drag_with_the_keys_held():
    drag = MouseButtonSequence.from_drag_press(
        Qt.BackButton, Qt.ShiftModifier | Qt.ControlModifier
    )

    assert drag.sequence == "Ctrl+Shift+Back-Drag"


def test_a_click_event_is_never_a_drag():
    event = QMouseEvent(
        QEvent.MouseButtonRelease,
        QPointF(0, 0),
        Qt.MiddleButton,
        Qt.NoButton,
        Qt.NoModifier,
    )

    assert MouseButtonSequence.from_event(event).sequence == "Middle-Click"


@pytest.mark.parametrize(
    ("drag", "problem"),
    [
        ("Middle-Drag", None),
        ("Ctrl+Drag", None),
        ("Shift+Back-Drag", None),
        ("Drag", DragProblem.MOVES_VIDEO),
        ("Right-Drag", DragProblem.RIGHT_BUTTON),
        ("Ctrl+Right-Drag", DragProblem.RIGHT_BUTTON),
        ("Meta+Middle-Drag", DragProblem.META),
        ("Middle-Click", DragProblem.NOT_A_DRAG),
        ("Ctrl+D", DragProblem.NOT_A_DRAG),
    ],
)
def test_what_a_drag_cannot_be(drag, problem):
    assert drag_problem(drag) is problem


def test_the_hold_keys_are_kept_as_they_are():
    assert normalize_shortcut("Hold Shift") == "Hold Shift"
    assert normalize_shortcut("Hold Meta") is None


def test_each_takes_only_what_it_can_be_set_to():
    assert fit_shortcuts("Play / Pause", ["P", "Ctrl+Drag", "Hold Alt", "Click"]) == [
        "P",
        "Click",
    ]
    assert fit_shortcuts(GESTURE_PAN, ["Ctrl+Drag", "Drag", "P", "Click"]) == [
        "Ctrl+Drag"
    ]
    assert fit_shortcuts(GESTURE_DROP_SWITCH, ["Hold Alt", "Hold Ctrl", "P"]) == [
        "Hold Alt"
    ]
    assert fit_shortcuts(GESTURE_MOVE_VIDEO, ["Ctrl+Drag"]) == ["Drag"]


def test_the_gestures_have_defaults_in_the_keymap_but_moving_a_video():
    keymap = default_keymap()

    assert keymap[GESTURE_PAN] == ["Middle-Drag"]
    assert keymap[GESTURE_ZOOM_SELECT] == ["Ctrl+Drag"]
    assert keymap[GESTURE_DROP_SWITCH] == ["Hold Shift"]
    assert GESTURE_MOVE_VIDEO not in keymap


def test_they_are_merged_and_saved_with_the_shortcuts():
    overrides = {GESTURE_PAN: ["Shift+Drag"], GESTURE_DROP_SWITCH: []}

    merged = merge_keymap(default_keymap(), overrides)

    assert merged[GESTURE_PAN] == ["Shift+Drag"]
    assert merged[GESTURE_DROP_SWITCH] == []
    assert sparse_overrides(merged).root == overrides


def test_a_default_drag_set_on_another_is_taken_from_its_owner():
    """Ctrl+Drag, the zoom's by default, set for moving the picture about,
    as an old pan_trigger of Ctrl comes over: the zoom is left with none."""

    merged = merge_keymap(default_keymap(), {GESTURE_PAN: ["Ctrl+Drag"]})

    assert merged[GESTURE_PAN] == ["Ctrl+Drag"]
    assert merged[GESTURE_ZOOM_SELECT] == []
    assert sparse_overrides(merged).root == {
        GESTURE_PAN: ["Ctrl+Drag"],
        GESTURE_ZOOM_SELECT: [],
    }


def test_a_drag_set_by_hand_on_an_action_is_dropped():
    merged = merge_keymap(default_keymap(), {"Play / Pause": ["Middle-Drag"]})

    assert merged["Play / Pause"] == []
    assert merged[GESTURE_PAN] == ["Middle-Drag"]


def test_a_drag_two_gestures_claim_goes_to_the_one_set_to_it():
    overrides = KeymapOverrides({GESTURE_ZOOM_SELECT: ["Middle-Drag"]})

    assert gesture_shortcuts(GESTURE_ZOOM_SELECT, overrides) == ["Middle-Drag"]
    assert gesture_shortcuts(GESTURE_PAN, overrides) == []


def test_the_drop_switch_key_is_a_qt_modifier():
    assert drop_switch_modifier(KeymapOverrides({})) == Qt.ShiftModifier
    assert (
        drop_switch_modifier(KeymapOverrides({GESTURE_DROP_SWITCH: ["Hold Ctrl"]}))
        == Qt.ControlModifier
    )
    assert drop_switch_modifier(KeymapOverrides({GESTURE_DROP_SWITCH: []})) is None


def test_gestures_are_read_from_the_settings(monkeypatch):
    monkeypatch.setattr(
        keymap_module,
        "Settings",
        lambda: SimpleNamespace(
            get=lambda _key: KeymapOverrides({GESTURE_PAN: ["Alt+Drag"]})
        ),
    )

    assert gesture_shortcuts(GESTURE_PAN) == ["Alt+Drag"]


@pytest.mark.parametrize(
    ("button", "keys", "is_press"),
    [
        (Qt.LeftButton, Qt.ControlModifier, True),
        (Qt.LeftButton, Qt.ControlModifier | Qt.ShiftModifier, False),
        (Qt.LeftButton, Qt.NoModifier, False),
        (Qt.MiddleButton, Qt.ControlModifier, False),
        (Qt.RightButton, Qt.ControlModifier, False),
    ],
)
def test_a_press_is_a_gesture_with_its_very_keys(monkeypatch, button, keys, is_press):
    monkeypatch.setattr(
        keymap_module,
        "Settings",
        lambda: SimpleNamespace(
            get=lambda _key: KeymapOverrides({GESTURE_PAN: ["Ctrl+Drag"]})
        ),
    )
    monkeypatch.setattr(QApplication, "queryKeyboardModifiers", lambda: Qt.NoModifier)

    event = QMouseEvent(QEvent.MouseButtonPress, QPointF(0, 0), button, button, keys)

    assert is_gesture_press(GESTURE_PAN, event) is is_press


def test_a_playlist_with_its_own_drop_key_still_loads():
    """The key is the app's alone now; one a playlist kept is let go of."""

    from gridplayer.models.playlist import Playlist

    playlist = Playlist.model_validate(
        {"drop_modifier": "ctrl", "drop_action_internal": "replace"}
    )

    assert "drop_modifier" not in playlist.model_dump()
    assert playlist.drop_action_internal.value == "replace"
