from collections.abc import Callable, Mapping

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params.settings_fields.kinds import (
    Indented,
    Note,
    Row,
    Section,
    SettingField,
    Slot,
    When,
)
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.utils.qt import translate
from gridplayer.widgets.settings_editors import Editor, make_editor

# how far the items that belong to the one above them are pushed in
INDENT_PX = 20

RESET_ICON_PX = 14


class SettingsForm(QWidget):
    """A page of settings, built from a layout.

    What a reset goes back to is up to the dialog. The Playlist Settings
    dialog goes back to the global settings, and counts a field as changed
    once it is edited, even back to the same value, since the playlist then
    keeps it. The Settings dialog goes back to the factory defaults, and counts
    a field as changed whenever it differs from them.
    """

    values_changed = pyqtSignal()

    def __init__(
        self,
        items,
        *,
        reset_to: Callable | None = None,
        track_edits: bool = True,
        slots: Mapping[str, Callable[[], QWidget]] | None = None,
        fields: Mapping[str, SettingField] = FIELDS,
    ):
        super().__init__()

        self._reset_to = reset_to
        self._track_edits = track_edits
        self._slots = slots or {}
        self._fields = fields

        self._specs: dict[str, SettingField] = {}
        self._editors: dict[str, Editor] = {}
        self._widgets: dict[str, QWidget] = {}
        self._rows: dict[str, QWidget] = {}
        self._reset_btns: dict[str, QToolButton] = {}
        # out of reach on this system, for good
        self._unavailable: set[str] = set()
        self._hidden: set[str] = set()
        # out of reach for now, by the dialog's say
        self._locked: set[str] = set()
        self._overridden: set[str] = set()
        # reset since the values were set, to be saved even if greyed out
        self._reset_keys: set[str] = set()
        self._updating = False
        self._fills = False

        # labels lined up together, a list for each section
        self._label_columns: list[list[QWidget]] = [[]]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._add_items(root, items, indent=0)

        if not self._fills:
            root.addStretch(1)

        self._line_up_labels()
        self._sync()

    # building

    def _add_items(self, layout, items, indent):
        for item in items:
            if isinstance(item, Section):
                self._label_columns.append([])
                layout.addWidget(self._header(item.title), alignment=Qt.AlignLeft)
                self._add_items(layout, item.items, indent)
                self._label_columns.append([])
            elif isinstance(item, Indented):
                self._add_items(layout, item.items, indent + INDENT_PX)
            elif isinstance(item, Row):
                self._add_row(layout, item.items, indent)
            elif isinstance(item, Note):
                layout.addWidget(self._note(item, indent))
            elif isinstance(item, Slot):
                self._add_row(layout, (item,), indent)
            else:
                self._add_row(layout, (item,), indent)

    @staticmethod
    def _header(title):
        header = QLabel(title)
        header.setOpenExternalLinks(True)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        return header

    @staticmethod
    def _note(note: Note, indent):
        label = QLabel(note.text)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)
        label.setContentsMargins(indent, 0, 0, 0)
        return label

    def _add_row(self, layout, entries, indent):
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(indent, 0, 0, 0)
        lay.setSpacing(8)

        editors = []
        fills = grows = False
        for entry in entries:
            if isinstance(entry, Slot):
                lay.addWidget(self._slots[entry.name](), 1 if entry.fills else 0)
                fills = fills or entry.fills
                continue

            # the first label, or a checkbox labelling the rest of the row,
            # goes in the column; a checkbox on its own spans the row
            in_column = not editors
            editor = self._add_editor(entry, lay, in_column, len(entries) > 1)
            self._rows[editor.spec.settings_key] = holder
            editors.append(editor)
            fills = fills or editor.fills
            grows = grows or editor.grows

        if not (fills or grows):
            lay.addStretch(1)

        if len(editors) == 1 and editors[0].spec.tooltip:
            holder.setToolTip(editors[0].spec.tooltip)
        else:
            for editor in editors:
                if editor.spec.tooltip:
                    for widget in (editor.label, *editor.parts()):
                        if widget is not None:
                            widget.setToolTip(editor.spec.tooltip)

        self._fills = self._fills or fills
        layout.addWidget(holder, 1 if fills else 0)

    def _add_editor(self, entry, lay, in_column, is_in_row) -> Editor:
        spec = entry if isinstance(entry, SettingField) else self._fields[entry]
        key = spec.settings_key

        editor = make_editor(spec)
        editor.changed.connect(lambda *_, key=key: self._on_edited(key))

        self._specs[key] = spec
        self._editors[key] = editor
        self._widgets[key] = editor.widget

        if editor.is_checkbox:
            column_widget = editor.widget if is_in_row else None
        else:
            column_widget = editor.label
        if column_widget is not None and in_column:
            self._label_columns[-1].append(column_widget)

        if editor.label is not None:
            lay.addWidget(editor.label)
        for widget in editor.parts():
            lay.addWidget(widget, 1 if editor.fills else 0)

        if self._reset_to is not None and not editor.fills:
            lay.addWidget(self._reset_button(key), alignment=Qt.AlignVCenter)

        self._check_available(spec)

        return editor

    def _reset_button(self, key):
        reset = QToolButton()
        reset.setIcon(QIcon.fromTheme("reset"))
        reset.setIconSize(QSize(RESET_ICON_PX, RESET_ICON_PX))
        reset.setAutoRaise(True)
        reset.setToolTip(translate("SettingsDialog", "Reset"))
        reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        reset.clicked.connect(lambda _=False, key=key: self.reset(key))

        # taking up its room while hidden, so nothing moves when it shows
        policy = reset.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        reset.setSizePolicy(policy)
        reset.hide()

        self._reset_btns[key] = reset
        return reset

    def _check_available(self, spec):
        key = spec.settings_key

        if spec.shown_if is not None and not spec.shown_if():
            self._unavailable.add(key)
            self._hidden.add(key)
            return

        if spec.unavailable is None:
            return

        reason = spec.unavailable()
        if reason is None:
            return

        self._unavailable.add(key)
        if reason:
            for widget in (self._editors[key].label, *self._editors[key].parts()):
                if widget is not None:
                    widget.setToolTip(reason)

    def _line_up_labels(self):
        """Labels of a section in a column, as a form layout would have them."""

        for column in self._label_columns:
            if len(column) < 2:
                continue
            width = max(widget.sizeHint().width() for widget in column)
            for widget in column:
                widget.setMinimumWidth(width)

    # what is on and what is shown

    def _sync(self):
        enabled = {}

        def is_on(key):
            if key not in enabled:
                enabled[key] = False  # what names itself is off
                enabled[key] = self._is_on(key, is_on)
            return enabled[key]

        for key, editor in self._editors.items():
            editor.set_enabled(is_on(key))

            spec = self._specs[key]
            if key in self._hidden:
                self._rows[key].setVisible(False)
            elif spec.shown_when is not None:
                self._rows[key].setVisible(self._is_met(spec.shown_when, is_on))

        self._sync_modified()

    def _is_on(self, key, is_on) -> bool:
        if key in self._unavailable or key in self._locked:
            return False

        spec = self._specs[key]
        for rule in (spec.shown_when, spec.enabled_when):
            if rule is not None and not self._is_met(rule, is_on):
                return False

        return True

    def _is_met(self, rule: When, is_on) -> bool:
        driver = self._editors.get(rule.key)

        # a form leaves a field alone when what it names isn't there
        if driver is None:
            return True

        return is_on(rule.key) and driver.value() in rule.values

    def _sync_modified(self):
        if self._reset_to is None:
            return

        for key, editor in self._editors.items():
            is_modified = self.is_modified(key)

            if editor.marked is not None:
                font = editor.marked.font()
                font.setItalic(is_modified)
                editor.marked.setFont(font)

            reset = self._reset_btns.get(key)
            if reset is not None:
                reset.setVisible(is_modified)

    def _refresh(self):
        self._sync()
        self.values_changed.emit()

    def _on_edited(self, key):
        if self._updating:
            return

        self._overridden.add(key)
        self._refresh()

    def _put(self, key, value):
        """A stored value into its editor."""

        spec = self._specs[key]
        if spec.to_editor is not None:
            value = spec.to_editor(value)

        self._editors[key].set_value(value)

    # for the dialogs

    def keys(self) -> list[str]:
        return list(self._editors)

    def editor(self, key: str) -> Editor:
        return self._editors[key]

    def widget(self, key: str) -> QWidget:
        return self._widgets[key]

    def spec(self, key: str) -> SettingField:
        return self._specs[key]

    def value(self, key: str):
        return self._editors[key].value()

    def values(self) -> dict:
        return {key: editor.value() for key, editor in self._editors.items()}

    def set_values(self, values: dict, overridden: set[str] | None = None):
        self._updating = True
        try:
            for key in self._editors:
                if key in values:
                    self._put(key, values[key])
            self._overridden = set(overridden or [])
            self._reset_keys = set()
        finally:
            self._updating = False
        self._sync()

    def default_shown(self, key: str):
        """What a reset would show."""

        spec = self._specs[key]
        value = self._reset_to(key)
        if spec.to_editor is not None:
            value = spec.to_editor(value)

        return self._editors[key].normalize(value)

    def is_modified(self, key: str) -> bool:
        if key in self._unavailable or key in self._locked:
            return False

        if self._track_edits or self._reset_to is None:
            return key in self._overridden

        return self._editors[key].value() != self.default_shown(key)

    def has_modified(self) -> bool:
        return any(self.is_modified(key) for key in self._editors)

    def reset(self, key: str):
        self._reset_one(key)
        self._refresh()

    def reset_all(self):
        """Every field that can be reset, as one change."""

        for key in self._editors:
            if key not in self._unavailable and key not in self._locked:
                self._reset_one(key)
        self._refresh()

    def _reset_one(self, key):
        self._overridden.discard(key)
        self._reset_keys.add(key)

        if self._reset_to is None:
            return

        self._updating = True
        try:
            self._put(key, self._reset_to(key))
        finally:
            self._updating = False

    def lock(self, key: str, locked: bool):
        """Greyed out and not saved, whatever the rules say, until unlocked."""

        if locked:
            self._locked.add(key)
        else:
            self._locked.discard(key)
        self._sync()

    def is_enabled(self, key: str) -> bool:
        widget = self._widgets.get(key)
        return widget is not None and widget.isEnabled()

    def is_available(self, key: str) -> bool:
        return key in self._editors and key not in self._unavailable

    def should_save(self, key: str) -> bool:
        """A greyed out field is not one to save over, unless it was reset."""

        if not self.is_available(key) or key in self._locked:
            return False

        return self.is_enabled(key) or key in self._reset_keys

    def overridden_keys(self) -> set[str]:
        return set(self._overridden)

    def mark_all_overridden(self):
        self._overridden = set(self._editors)
        self._sync_modified()

    def clear_overridden(self):
        self._overridden = set()
        self._sync_modified()
