"""Drop-replace modifier state.

Internal drags use Qt's keyboard state (and a grab on Linux). External file
drops on GNOME/XWayland never include keys — Files encodes Shift as Move.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.params.static import DropAction, DropModifier

_FILE_DROP_FORMATS = (
    "text/uri-list",
    "application/vnd.portal.filetransfer",
    "application/vnd.portal.files",
    "application/x-gtk-local-dnd",
)

_DROP_MODIFIERS = {
    DropModifier.SHIFT: Qt.ShiftModifier,
    DropModifier.CTRL: Qt.ControlModifier,
    DropModifier.ALT: Qt.AltModifier,
}


def drop_is_replace(qt_modifiers, action, modifier) -> bool:
    if modifier == DropModifier.NONE:
        return action == DropAction.REPLACE

    held = bool(qt_modifiers & _DROP_MODIFIERS[modifier])
    if action == DropAction.REPLACE:
        return not held
    return held


def modifiers_from_event(event) -> Qt.KeyboardModifiers:
    if event is None:
        return Qt.NoModifier
    keyboard_modifiers = getattr(event, "keyboardModifiers", None)
    if keyboard_modifiers is not None:
        return keyboard_modifiers()
    modifiers = getattr(event, "modifiers", None)
    if modifiers is not None:
        return modifiers()
    return Qt.NoModifier


def _mime_formats(md) -> list[str]:
    try:
        return [str(fmt) for fmt in md.formats()]
    except Exception:
        return []


def _is_external_file_drop(event) -> bool:
    get_md = getattr(event, "mimeData", None)
    if get_md is None:
        return False
    try:
        md = get_md()
    except Exception:
        return False
    if md is None:
        return False
    formats = _mime_formats(md)
    if "application/x-gridplayer-video" in formats or md.hasFormat(
        "application/x-gridplayer-video"
    ):
        return False
    if md.hasUrls():
        return True
    return any(
        fmt in formats or md.hasFormat(fmt) or any(f.startswith(fmt) for f in formats)
        for fmt in _FILE_DROP_FORMATS
    )


def modifiers_from_dnd_action(event) -> Qt.KeyboardModifiers:
    """Map file-manager drop action to Shift when keys are not available.

    GNOME Files on XWayland: Shift → proposed Move (often Move-only).
    """
    if event is None or not _is_external_file_drop(event):
        return Qt.NoModifier
    get_proposed = getattr(event, "proposedAction", None)
    if get_proposed is None:
        return Qt.NoModifier
    try:
        proposed = int(get_proposed())
    except Exception:
        return Qt.NoModifier

    mods = Qt.NoModifier
    if proposed & int(Qt.MoveAction):
        mods |= Qt.ShiftModifier
    elif proposed & int(Qt.LinkAction):
        mods |= Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier
    return mods


def query_drop_modifiers(event=None) -> Qt.KeyboardModifiers:
    mods = QApplication.queryKeyboardModifiers()
    mods |= modifiers_from_event(event)
    mods |= modifiers_from_dnd_action(event)
    return mods
