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


def bold(label: QLabel) -> QLabel:
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


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
    ):
        super().__init__()

        self._reset_to = reset_to
        self._track_edits = track_edits
        self._slots = slots or {}

        self._editors: dict[str, Editor] = {}
        self._rows: dict[str, QWidget] = {}
        self._reset_btns: dict[str, QToolButton] = {}
        # out of reach on this system, for good
        self._unavailable: set[str] = set()
        self._hidden: set[str] = set()
        # out of reach for now, by the dialog's say
        self._locked: set[str] = set()
        self._overridden: set[str] = set()
        # as of the last sync
        self._modified: set[str] = set()
        # what each editor was given, as it is stored (or will be, once reset)
        self._stored: dict = {}
        # reset since the values were set, to be saved even if greyed out
        self._reset_keys: set[str] = set()
        self._updating = False
        self._fills = False

        # labels lined up together, with how far each is pushed in, a list
        # for each section
        self._label_columns: list[list[tuple[QWidget, int]]] = [[]]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._add_items(root, items, indent=0)

        if not self._fills:
            root.addStretch(1)

        self._line_up_labels()
        # what is modified waits for the values
        self._sync(keys=())

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
            else:
                self._add_row(layout, (item,), indent)

    @staticmethod
    def _header(title):
        header = QLabel(title)
        header.setOpenExternalLinks(True)
        return bold(header)

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
        # a field's reset button, held back past the slots right after it:
        # a button there (a help, say) goes with the field, inside its reset
        held_reset = None
        for entry in entries:
            if isinstance(entry, Slot):
                lay.addWidget(self._slots[entry.name](), 1 if entry.fills else 0)
                fills = fills or entry.fills
                continue

            self._add_reset(lay, held_reset)

            # the first label, or a checkbox labelling the rest of the row,
            # goes in the column; a checkbox on its own spans the row
            in_column = not editors
            editor = self._add_editor(entry, lay, in_column, len(entries) > 1, indent)
            self._rows[editor.spec.settings_key] = holder
            editors.append(editor)
            fills = fills or editor.fills
            grows = grows or editor.grows

            held_reset = self._reset_btns.get(editor.spec.settings_key)

        self._add_reset(lay, held_reset)

        if not (fills or grows):
            lay.addStretch(1)

        if len(editors) == 1 and editors[0].tooltip:
            holder.setToolTip(editors[0].tooltip)
        else:
            for editor in editors:
                if editor.tooltip:
                    editor.set_tooltip(editor.tooltip)

        self._fills = self._fills or fills
        layout.addWidget(holder, 1 if fills else 0)

    def _add_editor(self, entry, lay, in_column, is_in_row, indent) -> Editor:
        spec = entry if isinstance(entry, SettingField) else FIELDS[entry]
        key = spec.settings_key

        editor = make_editor(spec)
        editor.changed.connect(lambda *_, key=key: self._on_edited(key))

        self._editors[key] = editor

        if editor.is_checkbox:
            column_widget = editor.widget if is_in_row else None
        else:
            column_widget = editor.label
        if column_widget is not None and in_column:
            self._label_columns[-1].append((column_widget, indent))

        if editor.label is not None:
            lay.addWidget(editor.label)
        for widget in editor.parts():
            lay.addWidget(widget, 1 if editor.fills else 0)

        if self._reset_to is not None and not editor.fills:
            self._reset_button(key)

        self._check_available(spec)

        return editor

    @staticmethod
    def _add_reset(lay, reset):
        if reset is not None:
            lay.addWidget(reset, alignment=Qt.AlignVCenter)

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
            self._editors[key].set_tooltip(reason)

    def _line_up_labels(self):
        """Labels of a section in a column, as a form layout would have them.

        Lined up by where their fields start: one pushed in is that much
        shorter.
        """

        for column in self._label_columns:
            if len(column) < 2:
                continue
            width = max(widget.sizeHint().width() + indent for widget, indent in column)
            for widget, indent in column:
                widget.setMinimumWidth(width - indent)

    # what is on and what is shown

    def _sync(self, keys=None):
        """What is on and shown, all of it; and what is modified, of these
        keys or all of them."""

        enabled = {}

        def is_on(key):
            if key not in enabled:
                enabled[key] = False  # what names itself is off
                enabled[key] = self._is_on(key, is_on)
            return enabled[key]

        for key, editor in self._editors.items():
            editor.set_enabled(is_on(key))

            if key in self._hidden:
                self._rows[key].setVisible(False)
            elif editor.spec.shown_when is not None:
                self._rows[key].setVisible(self._is_met(editor.spec.shown_when, is_on))

        self._sync_modified(keys)

    def _out_of_reach(self, key) -> bool:
        return key in self._unavailable or key in self._locked

    def _is_on(self, key, is_on) -> bool:
        if self._out_of_reach(key):
            return False

        spec = self._editors[key].spec
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

    def _sync_modified(self, keys=None):
        # worked out only where it may have changed, and kept: a value can be
        # slow to read (the keymap, the resolver patterns)
        for key in self._editors if keys is None else keys:
            is_modified = self._is_modified(key)
            if is_modified:
                self._modified.add(key)
            else:
                self._modified.discard(key)

            if self._reset_to is None:
                continue

            editor = self._editors[key]

            if editor.marked is not None:
                font = editor.marked.font()
                font.setItalic(is_modified)
                editor.marked.setFont(font)

            reset = self._reset_btns.get(key)
            if reset is not None:
                reset.setVisible(is_modified)

    def _refresh(self, keys=None):
        self._sync(keys)
        self.values_changed.emit()

    def _on_edited(self, key):
        if self._updating:
            return

        self._overridden.add(key)
        self._refresh((key,))

    def _shown(self, key, value):
        """A stored value as its editor shows it."""

        to_editor = self._editors[key].spec.to_editor
        return value if to_editor is None else to_editor(value)

    def _put(self, key, value):
        """A stored value into its editor."""

        self._editors[key].set_value(self._shown(key, value))

    # for the dialogs

    def keys(self) -> list[str]:
        return list(self._editors)

    def editor(self, key: str) -> Editor:
        return self._editors[key]

    def widget(self, key: str) -> QWidget:
        return self._editors[key].widget

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
            self._stored = {key: values[key] for key in self._editors if key in values}
            self._overridden = set(overridden or [])
            self._reset_keys = set()
        finally:
            self._updating = False
        self._sync()

    def default_shown(self, key: str):
        """What a reset would show."""

        return self._editors[key].normalize(self._shown(key, self._reset_to(key)))

    def is_default(self, key: str) -> bool:
        """Has what a reset would give.

        Behind a stand-in, by what it stands in for: the default may stand
        in as the very value something else saved does.
        """

        editor = self._editors[key]

        if editor.means_default():
            return True

        if self.shows_stand_in(key):
            return self._stored[key] == self._reset_to(key)

        return editor.value() == self.default_shown(key)

    def shows_stand_in(self, key: str) -> bool:
        """Shows, unchanged, what stands in for a stored value it can't show.

        Saving that back would lose the stored one, for when it can be shown.
        """

        editor = self._editors[key]
        return (
            editor.spec.to_editor is not None
            and key in self._stored
            and editor.value() == self._shown(key, self._stored[key])
        )

    def _is_modified(self, key):
        if self._out_of_reach(key):
            return False

        if self._track_edits or self._reset_to is None:
            return key in self._overridden

        return not self.is_default(key)

    def is_modified(self, key: str) -> bool:
        return key in self._modified

    def has_modified(self) -> bool:
        return bool(self._modified)

    def reset(self, key: str):
        self._reset_one(key)
        self._refresh((key,))

    def reset_all(self):
        """Every field that can be reset, as one change."""

        for key in self._editors:
            if not self._out_of_reach(key):
                self._reset_one(key)
        self._refresh()

    def _reset_one(self, key):
        self._overridden.discard(key)
        self._reset_keys.add(key)

        if self._reset_to is None:
            return

        self._stored[key] = self._reset_to(key)

        self._updating = True
        try:
            self._put(key, self._stored[key])
        finally:
            self._updating = False

    def lock(self, key: str, locked: bool):
        """Greyed out and not saved, whatever the rules say, until unlocked."""

        if locked == (key in self._locked):
            return

        if locked:
            self._locked.add(key)
        else:
            self._locked.discard(key)
        self._sync((key,))

    def is_enabled(self, key: str) -> bool:
        editor = self._editors.get(key)
        return editor is not None and editor.widget.isEnabled()

    def is_available(self, key: str) -> bool:
        return key in self._editors and key not in self._unavailable

    def should_save(self, key: str) -> bool:
        """A greyed out field is not one to save over, unless it was reset."""

        if key not in self._editors or self._out_of_reach(key):
            return False

        return self.is_enabled(key) or key in self._reset_keys

    def overridden_keys(self) -> set[str]:
        return set(self._overridden)
