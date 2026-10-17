import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.widgets.keymap_tree_view import KeymapEditor
from gridplayer.widgets.settings_controls import Switch, ToggleLabel


@pytest.fixture
def editor():
    editor = KeymapEditor()

    yield editor

    editor.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _folders_shown(editor):
    return editor.tree.proxy_model.rowCount()


def test_it_is_a_switch_as_in_the_settings_rows(editor):
    assert isinstance(editor.modified_only_switch, Switch)
    assert not editor.modified_only_switch.isChecked()


def test_on_it_leaves_only_what_is_changed(editor):
    everything = _folders_shown(editor)
    editor.tree.set_action_shortcuts("Stop", ["Ctrl+Shift+P"])

    editor.modified_only_switch.setChecked(True)

    assert _folders_shown(editor) == 1

    editor.modified_only_switch.setChecked(False)

    assert _folders_shown(editor) == everything


def test_its_words_flip_it_too(editor):
    label = next(
        label
        for label in editor.findChildren(ToggleLabel)
        if label.text() == "Only changed"
    )

    QTest.mouseClick(label, Qt.LeftButton)

    assert editor.modified_only_switch.isChecked()
