"""Shortcut / keymap editor widgets for Settings.

Builds a non-editable tree of actions from ``params.menu`` / ``params.actions``,
with filtering, non-default highlighting, and dialogs to add keyboard / mouse
bindings.
"""

from __future__ import annotations

from PyQt5.QtCore import QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal
from PyQt5.QtGui import (
    QIcon,
    QStandardItem,
    QStandardItemModel,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProxyStyle,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.utils.keymap import (
    KeymapOverrides,
    MouseButtonSequence,
    default_shortcuts,
    key_sequence_from_event,
    normalize_shortcut,
    normalize_shortcuts,
    sparse_overrides,
)
from gridplayer.utils.qt import translate
from gridplayer.widgets.custom_menu import ICON_SIZE, CustomMenu

# ---------------------------------------------------------------------------
# Model roles
# ---------------------------------------------------------------------------

DATA_ACTION_ID = Qt.UserRole + 10
DATA_SHORTCUTS = Qt.UserRole + 11  # list[str]
DATA_DEFAULT_SHORTCUTS = Qt.UserRole + 12  # list[str]
DATA_IS_MODIFIED = Qt.UserRole + 13
DATA_IS_ACTION = Qt.UserRole + 14
DATA_PATH = Qt.UserRole + 15  # list[str] breadcrumb titles
DATA_EXPANDED = Qt.UserRole + 16
DATA_SEARCH_TEXT = Qt.UserRole + 17
DATA_HAS_MODIFIED_CHILD = Qt.UserRole + 18

SECTION_TITLES = {
    "video_active": translate("Keymap", "Single video"),
    "video_all": translate("Keymap", "All videos"),
    "program": translate("Keymap", "Program"),
}

# Same theme icons as menu "Video", "[ALL]", and action "Settings"
SECTION_ICONS = {
    "video_active": "video",
    "video_all": "all",
    "program": "settings",
}

# Filter scope for the search field (combo values)
FILTER_SCOPE_ALL = "all"
FILTER_SCOPE_NAME = "name"
FILTER_SCOPE_SHORTCUT = "shortcut"

# Keys hard to capture via QKeySequenceEdit (consumed by the dialog / line edit)
SPECIAL_KEYS = (
    "Enter",
    "Esc",
    "Tab",
    "Ctrl+Tab",
    "Ctrl+Shift+Tab",
    "Shift+Tab",
)

MOUSE_PLACEHOLDER = translate(
    "Keymap",
    "Enter shortcut here: single or double-click, scroll the wheel,"
    " modify with Ctrl, Alt and Shift",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_title(action: dict) -> str:
    title = action["title"]
    if action.get("toggle") and isinstance(title, tuple):
        return "{} / {}".format(*title)
    if isinstance(title, tuple):
        return str(title[0])
    return str(title)


def _action_icon(action: dict) -> str | None:
    icon = action.get("icon")
    if action.get("toggle") and isinstance(icon, tuple):
        return icon[0]
    if isinstance(icon, tuple):
        return icon[0]
    return icon


def _default_shortcuts(action: dict) -> list[str]:
    return default_shortcuts(action)


def _format_shortcuts(shortcuts: list[str] | None) -> str:
    if not shortcuts:
        return ""
    return ", ".join(shortcuts)


def _path_label(path: list[str], action_title: str) -> str:
    """e.g. «Play / Pause» in Single video > Audio"""
    if path:
        location = " > ".join(path)
        return translate("Keymap", "«{action}» in {path}").format(
            action=action_title, path=location
        )
    return translate("Keymap", "«{action}»").format(action=action_title)


# ---------------------------------------------------------------------------
# Small UI pieces
# ---------------------------------------------------------------------------


class KeySequenceCapture(QLineEdit):
    """Single-chord shortcut capture without QKeySequenceEdit's multi-key ``, …`` UI."""

    sequence_text_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._sequence = ""

        self.setReadOnly(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.setClearButtonEnabled(False)
        self.setPlaceholderText(translate("Keymap", "Press a shortcut…"))
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def sequence_text(self) -> str:
        return self._sequence

    def set_sequence_text(self, text: str):
        self._sequence = text or ""
        self.setText(self._sequence)
        self.sequence_text_changed.emit(self._sequence)

    def clear_sequence(self):
        self.set_sequence_text("")

    def keyPressEvent(self, event):
        # Allow dialog Escape / default buttons only when field is empty? Still
        # capture Esc as a bindable key (also available via the + menu).
        text = key_sequence_from_event(event)
        if text is None:
            # Incomplete (modifier-only) — ignore without clearing
            event.accept()
            return

        self.set_sequence_text(text)
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()


class NoFrameFocus(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            return
        super().drawPrimitive(element, option, painter, widget)

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_SmallIconSize:
            return ICON_SIZE
        return super().pixelMetric(metric, option, widget)


class HotkeysWidget(QWidget):
    """Right-aligned shortcut chips for a tree row."""

    style_base = """
        background-color: #777;
        color: #fff;
        border-radius: 6px;
        padding-left: 4px;
        padding-right: 4px;
        """

    style_selected = """
        padding-left: 3px;
        padding-right: 3px;
        border: 1px solid #fff;
        """

    style_modified = """
        color: #000;
        background-color: #fff;
        border: 1px solid #000;
        """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.is_selected = False
        self.is_modified = False
        self._labels: list[QLabel] = []

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 10, 0)
        self._layout.setSpacing(4)
        self._layout.addStretch()

    def set_selected(self, selected: bool):
        if self.is_selected == selected:
            return
        self.is_selected = selected
        self._apply_styles()

    def set_modified(self, modified: bool):
        if self.is_modified == modified:
            return
        self.is_modified = modified
        self._apply_styles()

    def set_keys(self, keys: list[str] | str | None):
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",") if k.strip()] if keys else []
        keys = keys or []

        while self._labels:
            label = self._labels.pop()
            self._layout.removeWidget(label)
            label.deleteLater()

        for key in keys:
            label = QLabel(key, self)
            label.setMaximumHeight(20)
            self._layout.addWidget(label)
            self._labels.append(label)

        self._apply_styles()
        self.setVisible(bool(keys))

    def _apply_styles(self):
        style = self.style_base
        if self.is_modified:
            style += self.style_modified
        if self.is_selected and not self.is_modified:
            style += self.style_selected
        for label in self._labels:
            label.setStyleSheet(style)

    @property
    def is_deleted(self) -> bool:
        try:
            self.objectName()
        except RuntimeError as e:
            if "has been deleted" in str(e):
                return True
            raise
        return False


class TreeItemDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return HotkeysWidget(parent=parent)

    def setEditorData(self, editor: HotkeysWidget, index):
        shortcuts = index.data(DATA_SHORTCUTS) or []
        editor.set_keys(shortcuts)
        editor.set_modified(bool(index.data(DATA_IS_MODIFIED)))

    def paint(self, painter, option, index):
        is_action = bool(index.data(DATA_IS_ACTION))
        view = self.parent()

        if is_action and not view.isPersistentEditorOpen(index):
            view.openPersistentEditor(index)

        is_selected = bool(option.state & QStyle.State_Selected)

        edit_widget = view.indexWidget(index)
        if edit_widget and isinstance(edit_widget, HotkeysWidget):
            if not edit_widget.is_deleted:
                edit_widget.set_selected(is_selected)
                edit_widget.set_modified(bool(index.data(DATA_IS_MODIFIED)))
                # Keep chips in sync when model data changes
                shortcuts = index.data(DATA_SHORTCUTS) or []
                current = [lab.text() for lab in edit_widget._labels]
                if current != list(shortcuts):
                    edit_widget.set_keys(shortcuts)

        return super().paint(painter, option, index)


class FilterProxyModel(QSortFilterProxyModel):
    """Filter by title / path / shortcuts; keep ancestors of matches.

    Uses plain substring match (not regex) so shortcut characters like ``+``
    work as typed. Scope limits which fields are searched.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modified_only = False
        self._needle = ""
        self._scope = FILTER_SCOPE_ALL
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_filter_text(self, text: str):
        self._needle = (text or "").casefold()
        self.invalidateFilter()

    def set_filter_scope(self, scope: str):
        if scope not in (
            FILTER_SCOPE_ALL,
            FILTER_SCOPE_NAME,
            FILTER_SCOPE_SHORTCUT,
        ):
            scope = FILTER_SCOPE_ALL
        if self._scope == scope:
            return
        self._scope = scope
        self.invalidateFilter()

    def set_modified_only(self, enabled: bool):
        self._modified_only = enabled
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)

        if model.hasChildren(idx):
            child_match = any(
                self.filterAcceptsRow(i, idx) for i in range(model.rowCount(idx))
            )
            if child_match:
                return True
            # Section / submenu name itself matches the text filter
            return self._row_matches_filter(idx) and not self._modified_only

        return self._row_matches_filter(idx) and self._row_matches_modified(idx)

    def _row_matches_filter(self, idx: QModelIndex) -> bool:
        if not self._needle:
            return True
        haystack = self._search_haystack(idx)
        return self._needle in haystack

    def _search_haystack(self, idx: QModelIndex) -> str:
        """Build casefolded search text according to the active scope."""
        if self._scope == FILTER_SCOPE_SHORTCUT:
            parts = []
            for role in (DATA_SHORTCUTS, DATA_DEFAULT_SHORTCUTS):
                keys = idx.data(role) or []
                if isinstance(keys, (list, tuple)):
                    parts.extend(str(k) for k in keys)
                elif keys:
                    parts.append(str(keys))
            return " ".join(parts).casefold()

        if self._scope == FILTER_SCOPE_NAME:
            title = idx.data(Qt.DisplayRole) or ""
            path = idx.data(DATA_PATH) or []
            action_id = idx.data(DATA_ACTION_ID) or ""
            parts = [str(title), action_id, *([str(p) for p in path] if path else [])]
            return " ".join(parts).casefold()

        # All: full search blob (title, path, id, shortcuts, defaults)
        search = idx.data(DATA_SEARCH_TEXT) or idx.data(Qt.DisplayRole) or ""
        return str(search).casefold()

    def _row_matches_modified(self, idx: QModelIndex) -> bool:
        if not self._modified_only:
            return True
        return bool(idx.data(DATA_IS_MODIFIED) or idx.data(DATA_HAS_MODIFIED_CHILD))


# ---------------------------------------------------------------------------
# Mouse capture field (used in add-mouse dialog)
# ---------------------------------------------------------------------------


class MouseShortcutField(QFrame):
    """Gray rounded capture area for mouse shortcuts."""

    sequence_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._sequence = ""

        self.setObjectName("MouseShortcutField")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(72)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(MOUSE_PLACEHOLDER)

        self.setStyleSheet(
            """
            QFrame#MouseShortcutField {
                background-color: #6a6a6a;
                border-radius: 10px;
                border: 1px solid #555;
            }
            QFrame#MouseShortcutField:focus {
                border: 1px solid #bbb;
            }
            QLabel {
                color: #eee;
                background: transparent;
                border: none;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self._label = QLabel(MOUSE_PLACEHOLDER, self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("color: #ccc; font-style: italic;")
        layout.addWidget(self._label)

    def sequence(self) -> str:
        return self._sequence

    def set_sequence(self, sequence: str):
        self._sequence = sequence or ""
        if self._sequence:
            self._label.setText(self._sequence)
            self._label.setStyleSheet(
                "color: #fff; font-style: normal; font-weight: bold;"
            )
        else:
            self._label.setText(MOUSE_PLACEHOLDER)
            self._label.setStyleSheet("color: #ccc; font-style: italic;")
        self.sequence_changed.emit(self._sequence)

    def clear(self):
        self.set_sequence("")

    def mousePressEvent(self, event):
        try:
            seq = MouseButtonSequence.from_event(event)
        except ValueError:
            event.accept()
            return
        self.set_sequence(str(seq))
        event.accept()

    def mouseDoubleClickEvent(self, event):
        try:
            seq = MouseButtonSequence.from_event(event)
        except ValueError:
            event.accept()
            return
        self.set_sequence(str(seq))
        event.accept()

    def wheelEvent(self, event):
        try:
            seq = MouseButtonSequence.from_event(event)
        except ValueError:
            event.accept()
            return
        self.set_sequence(str(seq))
        event.accept()


# ---------------------------------------------------------------------------
# Add shortcut dialogs
# ---------------------------------------------------------------------------


class _AddShortcutDialogBase(QDialog):
    """Shared shell for keyboard / mouse add dialogs.

    If another action already uses the chord, a compact warning is shown live;
    on accept the user can reassign (steal) it or cancel.
    """

    def __init__(
        self,
        *,
        action_title: str,
        path: list[str],
        existing_shortcuts: list[str],
        conflict_map: dict[str, list[tuple[str, str]]],
        parent=None,
    ):
        super().__init__(parent)

        self._existing = list(existing_shortcuts)
        self._conflict_map = conflict_map  # shortcut -> [(action_id, display_path)]
        self._action_title = action_title
        self._path = list(path)
        self._result_sequence = ""
        self._conflicts_for_result: list[tuple[str, str]] = []
        self._clear_button: QPushButton | None = None

        self.setWindowTitle(self._window_title())
        self.setMinimumWidth(self._dialog_min_width())

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        path_label = QLabel(_path_label(path, action_title), self)
        path_label.setWordWrap(True)
        font = path_label.font()
        font.setBold(True)
        path_label.setFont(font)
        layout.addWidget(path_label)

        if existing_shortcuts:
            existing_lbl = QLabel(
                translate("Keymap", "Current shortcuts: {keys}").format(
                    keys=_format_shortcuts(existing_shortcuts)
                ),
                self,
            )
            existing_lbl.setWordWrap(True)
            existing_lbl.setStyleSheet("color: #888;")
            layout.addWidget(existing_lbl)

        layout.addWidget(self._create_input_row())

        self._warning_frame = QFrame(self)
        self._warning_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        warning_layout = QVBoxLayout(self._warning_frame)
        warning_layout.setContentsMargins(0, 4, 0, 0)
        warning_layout.setSpacing(2)

        self._warning_title = QLabel(
            translate("Keymap", "This shortcut is already used by:"),
            self._warning_frame,
        )
        self._warning_title.setStyleSheet("color: #c44; font-weight: bold;")
        warning_layout.addWidget(self._warning_title)

        self._conflict_label = QLabel(self._warning_frame)
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._conflict_label.setStyleSheet("color: #c44;")
        warning_layout.addWidget(self._conflict_label)

        # Collapsed by default — height 0 so the dialog can shrink cleanly
        self._set_warning_expanded(False)
        layout.addWidget(self._warning_frame)

        layout.addStretch()

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        for btn in self._buttons.buttons():
            btn.setIcon(QIcon())
        self._ok_button = self._buttons.button(QDialogButtonBox.Ok)
        self._ok_button.setEnabled(False)
        layout.addWidget(self._buttons)

        self._compact_height: int | None = None

    def _dialog_min_width(self) -> int:
        return 480

    def showEvent(self, event):
        super().showEvent(event)
        # Remember height without the conflict panel for reliable shrink-back
        if self._compact_height is None and not self._warning_frame.isVisibleTo(self):
            self._compact_height = self.sizeHint().height()
            self.resize(max(self.width(), self.minimumWidth()), self._compact_height)

    def _window_title(self) -> str:
        raise NotImplementedError

    def _create_input_row(self) -> QWidget:
        raise NotImplementedError

    def _current_sequence(self) -> str:
        raise NotImplementedError

    def _clear_sequence(self):
        raise NotImplementedError

    def _make_clear_button(self, parent: QWidget) -> QPushButton:
        btn = QPushButton(translate("Keymap", "Clear"), parent)
        btn.setToolTip(translate("Keymap", "Clear shortcut"))
        btn.setEnabled(False)
        btn.clicked.connect(self._clear_sequence)
        self._clear_button = btn
        return btn

    def _on_sequence_changed(self, _text: str = ""):
        seq = self._current_sequence()
        has_seq = bool(seq)
        self._ok_button.setEnabled(has_seq)
        if self._clear_button is not None:
            self._clear_button.setEnabled(has_seq)
        self._update_conflicts(seq)

    def _conflicts_for(self, seq: str) -> list[tuple[str, str]]:
        if not seq:
            return []
        normalized = normalize_shortcut(seq) or seq
        return list(self._conflict_map.get(normalized, []))

    def _set_warning_expanded(self, expanded: bool):
        """Show/hide conflict panel and force zero height when collapsed."""
        if expanded:
            self._warning_frame.setMaximumHeight(16777215)
            self._warning_frame.setVisible(True)
        else:
            self._conflict_label.clear()
            self._warning_frame.setVisible(False)
            # Zero max height so layout sizeHint drops even if visibility lags
            self._warning_frame.setMaximumHeight(0)
            self._warning_frame.setMinimumHeight(0)

    def _update_conflicts(self, seq: str):
        conflicts = self._conflicts_for(seq)
        if not conflicts:
            if (
                self._warning_frame.maximumHeight() == 0
                and not self._warning_frame.isVisible()
            ):
                return
            self._set_warning_expanded(False)
            self._relayout_dialog(expanding=False)
            return

        # One shortcut → one action; show a single compact owner line
        _action_id, display = conflicts[0]
        self._conflict_label.setText(display)

        self._set_warning_expanded(True)
        self._relayout_dialog(expanding=True)

    def _relayout_dialog(self, *, expanding: bool):
        """Grow or shrink after the conflict panel toggles."""
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.updateGeometry()

        width = max(self.width(), self.minimumWidth(), self.sizeHint().width())

        if expanding:
            height = self.sizeHint().height()
            self.resize(width, height)
        else:
            # Prefer the measured compact height; fall back to sizeHint
            if self._compact_height is None:
                self._compact_height = self.sizeHint().height()
            height = self._compact_height
            self.resize(width, height)

    def _on_accept(self):
        seq = normalize_shortcut(self._current_sequence())
        if not seq:
            return

        conflicts = self._conflicts_for(seq)
        if conflicts and not self._confirm_reassign(seq, conflicts):
            return

        self._conflicts_for_result = conflicts
        self._result_sequence = seq
        self.accept()

    def _confirm_reassign(self, seq: str, conflicts: list[tuple[str, str]]) -> bool:
        """Ask whether to steal the shortcut from the other action. False = cancel."""
        _action_id, display = conflicts[0]
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle(translate("Keymap", "Shortcut already in use"))
        msg.setText(
            translate(
                "Keymap",
                "The shortcut «{key}» is already assigned to:\n\n"
                "{action}\n\n"
                "Reassign it here and remove it from that action?",
            ).format(key=seq, action=display)
        )

        reassign_btn = msg.addButton(
            translate("Keymap", "Reassign"), QMessageBox.AcceptRole
        )
        msg.addButton(QMessageBox.Cancel)
        for btn in msg.buttons():
            btn.setIcon(QIcon())

        msg.exec_()
        return msg.clickedButton() == reassign_btn

    def result_sequence(self) -> str:
        return self._result_sequence

    def conflicts(self) -> list[tuple[str, str]]:
        return list(self._conflicts_for_result)


class AddKeyboardShortcutDialog(_AddShortcutDialogBase):
    def _window_title(self) -> str:
        return translate("Keymap", "Add keyboard shortcut")

    def _dialog_min_width(self) -> int:
        return 560

    def _create_input_row(self) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._key_edit = KeySequenceCapture(row)
        self._key_edit.sequence_text_changed.connect(self._on_sequence_changed)
        layout.addWidget(self._key_edit, 1)

        layout.addWidget(self._make_clear_button(row))

        self._special_btn = QToolButton(row)
        self._special_btn.setText("+")
        self._special_btn.setToolTip(
            translate("Keymap", "Insert special key (Enter, Esc, Tab, …)")
        )
        self._special_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self._special_btn)
        for key in SPECIAL_KEYS:
            menu.addAction(key, lambda k=key: self._set_special(k))
        self._special_btn.setMenu(menu)
        layout.addWidget(self._special_btn)

        return row

    def _set_special(self, key: str):
        self._key_edit.set_sequence_text(key)

    def _current_sequence(self) -> str:
        return self._key_edit.sequence_text()

    def _clear_sequence(self):
        self._key_edit.clear_sequence()


class AddMouseShortcutDialog(_AddShortcutDialogBase):
    def _window_title(self) -> str:
        return translate("Keymap", "Add mouse shortcut")

    def _create_input_row(self) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._mouse_field = MouseShortcutField(row)
        self._mouse_field.sequence_changed.connect(self._on_sequence_changed)
        layout.addWidget(self._mouse_field, 1)

        layout.addWidget(self._make_clear_button(row))

        return row

    def _current_sequence(self) -> str:
        return self._mouse_field.sequence()

    def _clear_sequence(self):
        self._mouse_field.clear()


# ---------------------------------------------------------------------------
# Tree model fill
# ---------------------------------------------------------------------------


def _search_blob(path: list[str], title: str, *extra: str) -> str:
    parts = [*path, title, *extra]
    return " ".join(p for p in parts if p)


def _set_folder_item(
    item: QStandardItem, title: str, path: list[str], icon: str | None
):
    item.setText(title)
    item.setIcon(QIcon.fromTheme(icon or "empty"))
    item.setEditable(False)
    item.setData(False, DATA_IS_ACTION)
    item.setData(path, DATA_PATH)
    item.setData(_search_blob(path, title), DATA_SEARCH_TEXT)
    item.setData(False, DATA_IS_MODIFIED)
    item.setData(False, DATA_HAS_MODIFIED_CHILD)


def _set_action_item(
    item: QStandardItem,
    action_id: str,
    action: dict,
    path: list[str],
    shortcuts: list[str] | None = None,
):
    title = _action_title(action)
    icon = _action_icon(action)
    defaults = _default_shortcuts(action)
    current = list(defaults if shortcuts is None else shortcuts)
    is_modified = current != defaults

    item.setText(title)
    item.setIcon(QIcon.fromTheme(icon or "empty"))
    item.setEditable(False)
    item.setData(action_id, DATA_ACTION_ID)
    item.setData(current, DATA_SHORTCUTS)
    item.setData(defaults, DATA_DEFAULT_SHORTCUTS)
    item.setData(is_modified, DATA_IS_MODIFIED)
    item.setData(True, DATA_IS_ACTION)
    item.setData(path, DATA_PATH)
    item.setData(
        _search_blob(
            path,
            title,
            action_id,
            _format_shortcuts(current),
            _format_shortcuts(defaults),
        ),
        DATA_SEARCH_TEXT,
    )
    item.setToolTip(_action_tooltip(title, path, current, defaults))
    _apply_modified_font(item, is_modified)


def _action_tooltip(
    title: str, path: list[str], current: list[str], defaults: list[str]
) -> str:
    lines = [_path_label(path, title)]
    lines.append(
        translate("Keymap", "Current: {keys}").format(
            keys=_format_shortcuts(current) or translate("Keymap", "(none)")
        )
    )
    lines.append(
        translate("Keymap", "Default: {keys}").format(
            keys=_format_shortcuts(defaults) or translate("Keymap", "(none)")
        )
    )
    return "\n".join(lines)


def _apply_modified_font(item: QStandardItem, modified: bool):
    font = item.font()
    font.setBold(modified)
    item.setFont(font)
    item.setData(None, Qt.ForegroundRole)


def fill_keymap_model(
    model: QStandardItemModel,
    bindings: dict[str, list[str]] | None = None,
):
    """Populate model from SECTIONS / ACTIONS.

    ``bindings`` maps action_id -> list of shortcut strings. When omitted,
    defaults from ACTIONS are used.
    """
    model.clear()
    bindings = bindings or {}

    for section_id, section_items in SECTIONS.items():
        section_title = SECTION_TITLES.get(section_id, section_id)
        section_root = QStandardItem()
        _set_folder_item(
            section_root,
            section_title,
            [section_title],
            SECTION_ICONS.get(section_id),
        )
        model.appendRow(section_root)
        _add_tree_items(section_root, section_items, [section_title], bindings)

    _refresh_modified_ancestors(model)


def _add_tree_items(
    root: QStandardItem,
    branch_items,
    path: list[str],
    bindings: dict[str, list[str]],
):
    for m_item in branch_items:
        if isinstance(m_item, tuple):
            _add_subtree(m_item, root, path, bindings)
        elif m_item == "---":
            continue  # separators are noise in a shortcut editor
        else:
            action = ACTIONS.get(m_item)
            if not action or action.get("menu_generator"):
                continue
            item = QStandardItem()
            _set_action_item(
                item,
                m_item,
                action,
                path,
                shortcuts=bindings.get(m_item),
            )
            root.appendRow(item)


def _add_subtree(
    subtree,
    root: QStandardItem,
    path: list[str],
    bindings: dict[str, list[str]],
):
    sub = SUBMENUS[subtree[0]]
    sub_items = subtree[1:]
    sub_title = sub["title"]
    sub_path = [*path, sub_title]

    sub_root = QStandardItem()
    _set_folder_item(sub_root, sub_title, sub_path, sub.get("icon"))
    root.appendRow(sub_root)
    _add_tree_items(sub_root, sub_items, sub_path, bindings)


def _refresh_modified_ancestors(model: QStandardItemModel):
    """Mark folders that contain modified actions; bold their labels."""

    def walk(item: QStandardItem) -> bool:
        if item.data(DATA_IS_ACTION):
            return bool(item.data(DATA_IS_MODIFIED))

        has_modified = False
        for row in range(item.rowCount()):
            child = item.child(row)
            if walk(child):
                has_modified = True

        item.setData(has_modified, DATA_HAS_MODIFIED_CHILD)
        _apply_modified_font(item, has_modified)
        return has_modified

    root = model.invisibleRootItem()
    for row in range(root.rowCount()):
        walk(root.child(row))


def _iter_action_items(model: QStandardItemModel):
    def walk(item: QStandardItem):
        if item.data(DATA_IS_ACTION):
            yield item
            return
        for row in range(item.rowCount()):
            yield from walk(item.child(row))

    root = model.invisibleRootItem()
    for row in range(root.rowCount()):
        yield from walk(root.child(row))


def _find_action_item(
    model: QStandardItemModel, action_id: str
) -> QStandardItem | None:
    for item in _iter_action_items(model):
        if item.data(DATA_ACTION_ID) == action_id:
            return item
    return None


def _find_action_items(
    model: QStandardItemModel, action_id: str
) -> list[QStandardItem]:
    return [
        item
        for item in _iter_action_items(model)
        if item.data(DATA_ACTION_ID) == action_id
    ]


# ---------------------------------------------------------------------------
# Tree view
# ---------------------------------------------------------------------------


class KeymapTreeView(QTreeView):
    """Tree of actions with shortcut chips; not rearrangeable."""

    action_menu_requested = pyqtSignal(str, object)  # action_id, global QPoint
    bindings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._source_model = QStandardItemModel(self)

        self.setStyle(NoFrameFocus("Fusion"))
        self.setUniformRowHeights(True)
        self.setHeaderHidden(True)
        self.setIndentation(24)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setExpandsOnDoubleClick(False)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setAnimated(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.setStyleSheet(
            """
            QTreeView::item {
                height: 24px;
                padding-top: 1px;
                padding-bottom: 1px;
            }
            """
        )

        self.setItemDelegate(TreeItemDelegate(self))

        self.proxy_model = FilterProxyModel(self)
        self.proxy_model.setRecursiveFilteringEnabled(True)
        self.proxy_model.setSourceModel(self._source_model)
        self.setModel(self.proxy_model)

        self._is_filter_set = False
        self._filter_text = ""

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        fill_keymap_model(self._source_model)

    # -- public API ---------------------------------------------------------

    def source_model(self) -> QStandardItemModel:
        return self._source_model

    def get_bindings(self) -> dict[str, list[str]]:
        return {
            item.data(DATA_ACTION_ID): list(item.data(DATA_SHORTCUTS) or [])
            for item in _iter_action_items(self._source_model)
        }

    def set_bindings(self, bindings: dict[str, list[str]]):
        fill_keymap_model(self._source_model, bindings)
        self._close_stale_editors()
        self.bindings_changed.emit()

    def reset_all_to_defaults(self):
        fill_keymap_model(self._source_model)
        self._close_stale_editors()
        self.bindings_changed.emit()

    def modified_count(self) -> int:
        seen: set[str] = set()
        for item in _iter_action_items(self._source_model):
            if item.data(DATA_IS_MODIFIED):
                seen.add(item.data(DATA_ACTION_ID))
        return len(seen)

    def build_conflict_map(
        self, exclude_action_id: str | None = None
    ) -> dict[str, list[tuple[str, str]]]:
        """shortcut -> [(action_id, display label), ...]"""
        result: dict[str, list[tuple[str, str]]] = {}
        seen: set[tuple[str, str]] = set()
        for item in _iter_action_items(self._source_model):
            action_id = item.data(DATA_ACTION_ID)
            if action_id == exclude_action_id:
                continue
            path = item.data(DATA_PATH) or []
            title = item.text()
            display = _path_label(path, title)
            for sc in normalize_shortcuts(item.data(DATA_SHORTCUTS) or []):
                key = (sc, action_id)
                if key in seen:
                    continue
                seen.add(key)
                result.setdefault(sc, []).append((action_id, display))
        return result

    def set_action_shortcuts(self, action_id: str, shortcuts: list[str]):
        items = _find_action_items(self._source_model, action_id)
        if not items:
            return

        current = normalize_shortcuts(shortcuts)

        for item in items:
            defaults = item.data(DATA_DEFAULT_SHORTCUTS) or []
            is_modified = current != list(defaults)

            item.setData(current, DATA_SHORTCUTS)
            item.setData(is_modified, DATA_IS_MODIFIED)
            path = item.data(DATA_PATH) or []
            item.setData(
                _search_blob(
                    path,
                    item.text(),
                    action_id,
                    _format_shortcuts(current),
                    _format_shortcuts(defaults),
                ),
                DATA_SEARCH_TEXT,
            )
            item.setToolTip(_action_tooltip(item.text(), path, current, defaults))
            _apply_modified_font(item, is_modified)

            # Refresh persistent editor chips
            proxy_index = self._proxy_index_for_item(item)
            if proxy_index.isValid():
                editor = self.indexWidget(proxy_index)
                if (
                    editor
                    and isinstance(editor, HotkeysWidget)
                    and not editor.is_deleted
                ):
                    editor.set_keys(current)
                    editor.set_modified(is_modified)
                self.update(proxy_index)

        _refresh_modified_ancestors(self._source_model)
        self.bindings_changed.emit()

    def filter_items(self, text: str):
        text = text or ""
        self._filter_text = text

        if text:
            if not self._is_filter_set:
                self._is_filter_set = True
                self.save_expanded_state()
            self.proxy_model.set_filter_text(text)
            self.expandAll()
        else:
            self.proxy_model.set_filter_text("")
            if not self.proxy_model._modified_only:
                self.reset_filter()
            else:
                self._filter_text = ""
                self.expandAll()

    def set_filter_scope(self, scope: str):
        self.proxy_model.set_filter_scope(scope)
        if self._filter_text:
            self.expandAll()

    def set_modified_only(self, enabled: bool):
        if enabled and not self._is_filter_set and not self._filter_text:
            self._is_filter_set = True
            self.save_expanded_state()
            self.expandAll()
        self.proxy_model.set_modified_only(enabled)
        if enabled:
            self.expandAll()
        elif not self._filter_text:
            self.reset_filter()

    def reset_filter(self):
        self.proxy_model.set_filter_text("")
        if self._is_filter_set and not self.proxy_model._modified_only:
            self._is_filter_set = False
            self.collapseAll()
            self.restore_expanded_state()
        self._filter_text = ""

    def expand_all_items(self):
        self.expandAll()

    def collapse_all_items(self):
        self.collapseAll()

    # -- expand state -------------------------------------------------------

    def save_expanded_state(self, index: QModelIndex | None = None):
        if index is None:
            for row in range(self.model().rowCount()):
                self.save_expanded_state(self.model().index(row, 0))
            return

        source = self.proxy_model.mapToSource(index)
        if self.isExpanded(index):
            self._source_model.setData(source, True, DATA_EXPANDED)
            for row in range(self.model().rowCount(index)):
                self.save_expanded_state(self.model().index(row, 0, index))

    def restore_expanded_state(self, index: QModelIndex | None = None):
        if index is None:
            for row in range(self.model().rowCount()):
                self.restore_expanded_state(self.model().index(row, 0))
            return

        source = self.proxy_model.mapToSource(index)
        if self._source_model.data(source, DATA_EXPANDED):
            self._source_model.setData(source, None, DATA_EXPANDED)
            self.expand(index)
            for row in range(self.model().rowCount(index)):
                self.restore_expanded_state(self.model().index(row, 0, index))

    # -- events / menus -----------------------------------------------------

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid() and index.data(DATA_IS_ACTION):
                self._emit_menu_for_index(index, event.globalPos())
                event.accept()
                return
            # Folders: toggle expand/collapse (ExpandsOnDoubleClick is off so
            # action rows can open the context menu instead)
            if index.isValid() and self.model().hasChildren(index):
                self.setExpanded(index, not self.isExpanded(index))
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid() or not index.data(DATA_IS_ACTION):
            return
        self._emit_menu_for_index(index, self.viewport().mapToGlobal(pos))

    def _emit_menu_for_index(self, proxy_index: QModelIndex, global_pos):
        action_id = proxy_index.data(DATA_ACTION_ID)
        if action_id:
            self.action_menu_requested.emit(action_id, global_pos)

    def _proxy_index_for_item(self, item: QStandardItem) -> QModelIndex:
        source_index = self._source_model.indexFromItem(item)
        return self.proxy_model.mapFromSource(source_index)

    def _close_stale_editors(self):
        # Persistent editors are recreated on paint for action rows
        for index in self._all_proxy_indexes():
            if self.isPersistentEditorOpen(index):
                self.closePersistentEditor(index)

    def _all_proxy_indexes(self, parent=None):
        if parent is None:
            parent = QModelIndex()
        model = self.model()
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            yield idx
            if model.hasChildren(idx):
                yield from self._all_proxy_indexes(idx)


# ---------------------------------------------------------------------------
# Composite editor (settings page body)
# ---------------------------------------------------------------------------


class KeymapEditor(QWidget):
    """Full shortcut editor panel as it would appear in Settings."""

    bindings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._build_ui()
        self._connect_signals()
        self._update_status()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Row 1: filter field + scope dropdown + modified toggle
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.filter_edit = QLineEdit(self)
        self.filter_edit.setClearButtonEnabled(True)
        filter_row.addWidget(self.filter_edit, 1)

        self.filter_scope = QComboBox(self)
        self.filter_scope.addItem(translate("Keymap", "All"), FILTER_SCOPE_ALL)
        self.filter_scope.addItem(translate("Keymap", "Action name"), FILTER_SCOPE_NAME)
        self.filter_scope.addItem(
            translate("Keymap", "Shortcut"), FILTER_SCOPE_SHORTCUT
        )
        self.filter_scope.setToolTip(
            translate("Keymap", "Limit search to action names or shortcuts")
        )
        filter_row.addWidget(self.filter_scope)

        self.modified_only_btn = QToolButton(self)
        self.modified_only_btn.setText(translate("Keymap", "Modified"))
        self.modified_only_btn.setCheckable(True)
        self.modified_only_btn.setToolTip(
            translate("Keymap", "Show only actions with non-default shortcuts")
        )
        filter_row.addWidget(self.modified_only_btn)

        root.addLayout(filter_row)

        # Row 2: expand / collapse / reset
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        self.expand_btn = QPushButton(translate("Keymap", "Expand all"), self)
        self.collapse_btn = QPushButton(translate("Keymap", "Collapse all"), self)
        actions_row.addWidget(self.expand_btn)
        actions_row.addWidget(self.collapse_btn)

        actions_row.addStretch(1)

        self.reset_all_btn = QPushButton(translate("Keymap", "Reset all"), self)
        self.reset_all_btn.setToolTip(
            translate("Keymap", "Restore every shortcut to its default")
        )
        actions_row.addWidget(self.reset_all_btn)

        root.addLayout(actions_row)

        self._update_filter_placeholder()

        self.tree = KeymapTreeView(self)
        root.addWidget(self.tree, 1)

        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #888;")
        root.addWidget(self.status_label)

    def _update_filter_placeholder(self):
        scope = self.filter_scope.currentData()
        if scope == FILTER_SCOPE_NAME:
            text = translate("Keymap", "Filter by action name…")
        elif scope == FILTER_SCOPE_SHORTCUT:
            text = translate("Keymap", "Filter by shortcut…")
        else:
            text = translate("Keymap", "Filter by name or shortcut…")
        self.filter_edit.setPlaceholderText(text)

    def _connect_signals(self):
        self.filter_edit.textChanged.connect(self.tree.filter_items)
        self.filter_scope.currentIndexChanged.connect(self._on_filter_scope_changed)
        self.modified_only_btn.toggled.connect(self.tree.set_modified_only)
        self.expand_btn.clicked.connect(self.tree.expand_all_items)
        self.collapse_btn.clicked.connect(self.tree.collapse_all_items)
        self.reset_all_btn.clicked.connect(self._on_reset_all)
        self.tree.action_menu_requested.connect(self._show_action_menu)
        self.tree.bindings_changed.connect(self._on_bindings_changed)

    def _on_filter_scope_changed(self, _index: int = 0):
        self._update_filter_placeholder()
        self.tree.set_filter_scope(self.filter_scope.currentData())

    # -- public API for later Settings integration --------------------------

    def get_bindings(self) -> dict[str, list[str]]:
        return self.tree.get_bindings()

    def get_sparse_bindings(self) -> KeymapOverrides:
        """Deduped overrides only — ready to persist as ``player/keymap``."""
        return sparse_overrides(self.get_bindings())

    def set_bindings(self, bindings: dict[str, list[str]]):
        self.tree.set_bindings(bindings)
        self._update_status()

    def is_modified(self) -> bool:
        return self.tree.modified_count() > 0

    # -- context menu -------------------------------------------------------

    def _show_action_menu(self, action_id: str, global_pos):
        item = _find_action_item(self.tree.source_model(), action_id)
        if item is None:
            return

        shortcuts = list(item.data(DATA_SHORTCUTS) or [])
        defaults = list(item.data(DATA_DEFAULT_SHORTCUTS) or [])
        is_modified = bool(item.data(DATA_IS_MODIFIED))
        path = item.data(DATA_PATH) or []
        title = item.text()

        menu = CustomMenu(parent=self)

        menu.addAction(
            translate("Keymap", "Add keyboard shortcut"),
            lambda: self._add_keyboard(action_id, title, path, shortcuts),
        )
        menu.addAction(
            translate("Keymap", "Add mouse shortcut"),
            lambda: self._add_mouse(action_id, title, path, shortcuts),
        )

        if shortcuts:
            menu.addSeparator()
            for sc in shortcuts:
                menu.addAction(
                    translate("Keymap", "Remove «{key}»").format(key=sc),
                    lambda s=sc: self._remove_shortcut(action_id, shortcuts, s),
                )

        if is_modified:
            menu.addSeparator()
            menu.addAction(
                translate("Keymap", "Reset shortcut"),
                lambda: self._reset_action(action_id, defaults),
            )

        menu.exec_(global_pos)

    def _add_keyboard(
        self, action_id: str, title: str, path: list[str], existing: list[str]
    ):
        dialog = AddKeyboardShortcutDialog(
            action_title=title,
            path=path,
            existing_shortcuts=existing,
            conflict_map=self.tree.build_conflict_map(exclude_action_id=action_id),
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        self._apply_new_shortcut(
            action_id,
            existing,
            dialog.result_sequence(),
            dialog.conflicts(),
        )

    def _add_mouse(
        self, action_id: str, title: str, path: list[str], existing: list[str]
    ):
        dialog = AddMouseShortcutDialog(
            action_title=title,
            path=path,
            existing_shortcuts=existing,
            conflict_map=self.tree.build_conflict_map(exclude_action_id=action_id),
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        self._apply_new_shortcut(
            action_id,
            existing,
            dialog.result_sequence(),
            dialog.conflicts(),
        )

    def _apply_new_shortcut(
        self,
        action_id: str,
        existing: list[str],
        new_seq: str,
        conflicts: list[tuple[str, str]],
    ):
        new_seq = normalize_shortcut(new_seq) if new_seq else None
        if not new_seq:
            return

        # One shortcut → one action: always clear the chord from others first
        for other_id, _display in conflicts:
            other_item = _find_action_item(self.tree.source_model(), other_id)
            if other_item is None:
                continue
            other_shortcuts = [
                s
                for s in normalize_shortcuts(other_item.data(DATA_SHORTCUTS) or [])
                if s != new_seq
            ]
            self.tree.set_action_shortcuts(other_id, other_shortcuts)

        new_list = normalize_shortcuts(existing)
        if new_seq not in new_list:
            new_list.append(new_seq)

        self.tree.set_action_shortcuts(action_id, new_list)

    def _remove_shortcut(self, action_id: str, existing: list[str], shortcut: str):
        new_list = [s for s in existing if s != shortcut]
        self.tree.set_action_shortcuts(action_id, new_list)

    def _reset_action(self, action_id: str, defaults: list[str]):
        self.tree.set_action_shortcuts(action_id, list(defaults))

    def _on_reset_all(self):
        if self.tree.modified_count() == 0:
            return

        answer = QCustomMessageBox.question(
            self,
            translate("Keymap", "Reset all shortcuts"),
            translate(
                "Keymap",
                "Restore every shortcut to its default value?",
            ),
        )
        if answer == QMessageBox.Yes:
            self.tree.reset_all_to_defaults()

    def _on_bindings_changed(self):
        self._update_status()
        self.bindings_changed.emit()

    def _update_status(self):
        count = self.tree.modified_count()
        if count:
            self.status_label.setText(
                translate("Keymap", "{n} action(s) with non-default shortcuts").format(
                    n=count
                )
            )
            self.reset_all_btn.setEnabled(True)
        else:
            self.status_label.setText(
                translate("Keymap", "All shortcuts are at their defaults")
            )
            self.reset_all_btn.setEnabled(False)
