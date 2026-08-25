from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.utils import drag_n_drop as km


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_modifiers_from_event_keyboard_modifiers():
    event = SimpleNamespace(keyboardModifiers=lambda: Qt.ShiftModifier)
    assert km.modifiers_from_event(event) == Qt.ShiftModifier


def test_modifiers_from_event_qt5_mouse_modifiers():
    event = SimpleNamespace(modifiers=lambda: Qt.ControlModifier)
    assert km.modifiers_from_event(event) == Qt.ControlModifier


def test_modifiers_from_event_none():
    assert km.modifiers_from_event(None) == Qt.NoModifier


class _FileMime:
    def hasFormat(self, fmt):
        return fmt == "text/uri-list"

    def hasUrls(self):
        return True

    def formats(self):
        return ["text/uri-list"]


class _GnomePortalMime:
    """Formats from Ubuntu Files → XWayland Qt (probe dump)."""

    def hasFormat(self, fmt):
        return fmt in self.formats()

    def hasUrls(self):
        return False

    def formats(self):
        return [
            "application/x-gtk-local-dnd",
            "application/vnd.portal.filetransfer",
            "application/vnd.portal.files",
            "text/uri-list",
            "text/plain;charset=utf-8",
        ]


class _VideoMime:
    def hasFormat(self, fmt):
        return fmt == "application/x-gridplayer-video"

    def hasUrls(self):
        return False

    def formats(self):
        return ["application/x-gridplayer-video"]


def _dnd_event(proposed, possible, mime):
    return SimpleNamespace(
        proposedAction=lambda: proposed,
        possibleActions=lambda: possible,
        mimeData=lambda: mime,
    )


def test_modifiers_from_dnd_action_shift_is_move_when_copy_offered():
    event = _dnd_event(Qt.MoveAction, Qt.CopyAction | Qt.MoveAction, _FileMime())
    assert km.modifiers_from_dnd_action(event) == Qt.ShiftModifier


def test_modifiers_from_dnd_action_copy_is_not_shift():
    event = _dnd_event(Qt.CopyAction, Qt.CopyAction | Qt.MoveAction, _FileMime())
    assert km.modifiers_from_dnd_action(event) == Qt.NoModifier


def test_modifiers_from_dnd_action_file_move_only_is_shift():
    event = _dnd_event(Qt.MoveAction, Qt.MoveAction, _FileMime())
    assert km.modifiers_from_dnd_action(event) == Qt.ShiftModifier


def test_modifiers_from_dnd_action_gnome_portal_move_is_shift():
    event = _dnd_event(
        Qt.MoveAction, Qt.MoveAction | Qt.TargetMoveAction, _GnomePortalMime()
    )
    assert km.modifiers_from_dnd_action(event) == Qt.ShiftModifier


def test_modifiers_from_dnd_action_internal_video_move_is_not_shift():
    event = _dnd_event(Qt.MoveAction, Qt.MoveAction, _VideoMime())
    assert km.modifiers_from_dnd_action(event) == Qt.NoModifier


def test_modifiers_from_dnd_action_link_counts_as_shift():
    event = _dnd_event(
        Qt.LinkAction, Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, _FileMime()
    )
    assert km.modifiers_from_dnd_action(event) & Qt.ShiftModifier


def test_query_drop_modifiers_ors_event_and_query(mocker):
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.NoModifier
    )
    event = SimpleNamespace(keyboardModifiers=lambda: Qt.ShiftModifier)
    assert km.query_drop_modifiers(event) == Qt.ShiftModifier
