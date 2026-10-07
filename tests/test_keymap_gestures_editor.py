"""The drags and the drop's key on the shortcuts page, in a folder of their
own at the bottom of the tree."""

import pytest
from PyQt5.QtWidgets import QApplication

import gridplayer.widgets.keymap_tree_view as tree_module
from gridplayer.params.gestures import (
    GESTURE_DROP_SWITCH,
    GESTURE_MOVE_VIDEO,
    GESTURE_PAN,
    GESTURE_ZOOM_SELECT,
    GestureKind,
)
from gridplayer.widgets.custom_menu import CustomMenu
from gridplayer.widgets.keymap_tree_view import (
    DATA_ACTION_ID,
    DATA_KIND,
    DATA_SHORTCUTS,
    GESTURES_TITLE,
    AddDragShortcutDialog,
    AddMouseShortcutDialog,
    KeymapEditor,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor():
    # never deleteLater(): a KeymapEditor deleted that way takes the test
    # process down with it, as it did before there were gestures in it
    return KeymapEditor()


def _gestures_folder(editor):
    model = editor.tree.source_model()
    return model.item(model.rowCount() - 1)


def _rows(folder):
    return [folder.child(row) for row in range(folder.rowCount())]


def test_they_are_in_a_folder_at_the_bottom(editor):
    folder = _gestures_folder(editor)

    assert folder.text() == GESTURES_TITLE
    assert [row.data(DATA_ACTION_ID) for row in _rows(folder)] == [
        GESTURE_MOVE_VIDEO,
        GESTURE_DROP_SWITCH,
        GESTURE_PAN,
        GESTURE_ZOOM_SELECT,
    ]
    assert [row.data(DATA_SHORTCUTS) for row in _rows(folder)] == [
        ["Drag"],
        ["Hold Shift"],
        ["Middle-Drag"],
        ["Ctrl+Drag"],
    ]


def test_moving_a_video_is_only_shown(editor, mocker):
    row = _rows(_gestures_folder(editor))[0]
    menu = mocker.patch.object(tree_module, "CustomMenu")

    assert row.data(DATA_KIND) is GestureKind.FIXED
    assert GESTURE_MOVE_VIDEO not in editor.get_bindings()
    assert "Drag" not in editor.tree.build_conflict_map()

    editor._show_action_menu(GESTURE_MOVE_VIDEO, None)

    menu.assert_not_called()


def test_the_drop_key_is_picked_from_the_few_there_are(editor, mocker):
    menus = []
    mocker.patch.object(CustomMenu, "exec_", lambda menu, *_: menus.append(menu))

    editor._show_action_menu(GESTURE_DROP_SWITCH, None)

    choices = [a for a in menus[0].actions() if a.isCheckable()]

    assert [a.text() for a in choices] == ["Shift", "Ctrl", "Alt", "None"]
    assert [a.isChecked() for a in choices] == [True, False, False, False]

    choices[3].trigger()

    assert editor.get_bindings()[GESTURE_DROP_SWITCH] == []
    assert editor.get_sparse_bindings().root == {GESTURE_DROP_SWITCH: []}


def test_a_drag_row_offers_a_drag_not_shortcuts(editor, mocker):
    menus = []
    mocker.patch.object(CustomMenu, "exec_", lambda menu, *_: menus.append(menu))

    editor._show_action_menu(GESTURE_PAN, None)

    texts = [a.text() for a in menus[0].actions() if not a.isSeparator()]

    assert texts == ["Add mouse drag", "Remove «Middle-Drag»"]


def _drag_dialog(hold_key="Hold Shift"):
    return AddDragShortcutDialog(
        action_title="Move picture within its cell",
        path=[GESTURES_TITLE],
        existing_shortcuts=[],
        conflict_map={"Middle-Drag": [(GESTURE_PAN, "pan")]},
        hold_key=hold_key,
    )


@pytest.mark.parametrize("drag", ["Drag", "Right-Drag", "Meta+Back-Drag"])
def test_a_drag_that_cannot_be_is_refused_with_why(drag):
    dialog = _drag_dialog()

    dialog._mouse_field.set_sequence(drag)

    assert not dialog._ok_button.isEnabled()
    assert dialog._note_label.text()


def test_a_drag_another_has_is_told_of():
    dialog = _drag_dialog()

    dialog._mouse_field.set_sequence("Middle-Drag")

    assert dialog._ok_button.isEnabled()
    assert dialog._conflict_label.text() == "pan"


def test_a_drag_with_the_drop_key_alone_is_told_of():
    dialog = _drag_dialog()

    dialog._mouse_field.set_sequence("Shift+Drag")

    assert dialog._ok_button.isEnabled()
    assert "Shift" in dialog._note_label.text()

    # with more keys, or no key to switch with, it is another drag
    dialog._mouse_field.set_sequence("Ctrl+Shift+Drag")
    assert not dialog._note_label.text()

    dialog = _drag_dialog(hold_key=None)
    dialog._mouse_field.set_sequence("Shift+Drag")
    assert not dialog._note_label.text()


@pytest.mark.parametrize(
    "dialog_class", [AddMouseShortcutDialog, AddDragShortcutDialog]
)
@pytest.mark.parametrize("is_linux", [True, False])
def test_alt_is_told_of_on_linux(mocker, dialog_class, is_linux):
    mocker.patch.object(tree_module.env, "IS_LINUX", is_linux)
    dialog = dialog_class(
        action_title="x", path=[], existing_shortcuts=[], conflict_map={}
    )

    sequence = (
        "Alt+Middle-Drag" if dialog_class is AddDragShortcutDialog else ("Alt+Click")
    )
    dialog._mouse_field.set_sequence(sequence)

    assert dialog._ok_button.isEnabled()
    assert bool(dialog._note_label.text()) is is_linux
