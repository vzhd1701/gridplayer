"""Drop-replace modifier state.

Internal drags use Qt's keyboard state (and a grab on Linux). External file
drops on GNOME/XWayland never include keys — Files encodes Shift as Move.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from gridplayer.params.static import DropAction

_FILE_DROP_FORMATS = (
    "text/uri-list",
    "application/vnd.portal.filetransfer",
    "application/vnd.portal.files",
    "application/x-gtk-local-dnd",
)


def drop_is_replace(qt_modifiers, action, modifier) -> bool:
    """Whether a drop replaces, ``modifier`` the key held to switch, if any."""

    if modifier is None:
        return action == DropAction.REPLACE

    held = bool(qt_modifiers & modifier)
    if action == DropAction.REPLACE:
        return not held
    return held


def modifiers_from_event(event) -> Qt.KeyboardModifier:
    if event is None:
        return Qt.KeyboardModifier.NoModifier
    return event.modifiers()


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


def modifiers_from_dnd_action(event) -> Qt.KeyboardModifier:
    """Map file-manager drop action to Shift when keys are not available.

    GNOME Files on XWayland: Shift → proposed Move (often Move-only).
    """
    if event is None or not _is_external_file_drop(event):
        return Qt.KeyboardModifier.NoModifier
    get_proposed = getattr(event, "proposedAction", None)
    if get_proposed is None:
        return Qt.KeyboardModifier.NoModifier
    try:
        proposed = get_proposed()
    except Exception:
        return Qt.KeyboardModifier.NoModifier

    mods = Qt.KeyboardModifier.NoModifier
    if proposed & Qt.DropAction.MoveAction:
        mods |= Qt.KeyboardModifier.ShiftModifier
    elif proposed & Qt.DropAction.LinkAction:
        mods |= (
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
        )
    return mods


def query_drop_modifiers(event=None) -> Qt.KeyboardModifier:
    mods = QApplication.queryKeyboardModifiers()
    mods |= modifiers_from_event(event)
    mods |= modifiers_from_dnd_action(event)
    return mods
