from collections.abc import Callable, Mapping

from PyQt5.QtCore import QEvent, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPainter
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.models.settings_draft import (
    FieldDraft,
    ResetValue,
    SettingsMode,
    SetValue,
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
from gridplayer.params.theme import set_secondary
from gridplayer.utils.qt import translate
from gridplayer.widgets.settings_controls import theme_color
from gridplayer.widgets.settings_editors import Editor, make_editor

RESET_ICON_PX = 14

# a row of a card: its height, and how far what is in it keeps from the edges
ROW_HEIGHT = 40
ROW_MARGINS = (14, 6, 10, 6)
# a field under its label: a little more room above and below the two lines
STACKED_MARGINS = (14, 9, 10, 10)
STACKED_SPACING = 6
# a sub-option, kept close under the one it belongs to
SUB_ROW_HEIGHT = 34

CARD_RADIUS = 6

# the bar on the left edge of a changed row
MARK_WIDTH = 3
MARK_INSET = 6

# between the heading of a section and its card, and the card and a note
SECTION_SPACING = 8
# between one section and the next
SECTIONS_SPACING = 20


def bold(label: QLabel) -> QLabel:
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _put_away(widget: QWidget) -> bool:
    """Hidden on purpose, rather than not shown yet: one just put in a
    layout is shown only once the event loop comes round to it."""

    return widget.isHidden() and widget.testAttribute(Qt.WA_WState_ExplicitShowHide)


class _Shown(QWidget):
    """Shown while anything it watches is, so that a card or a section with
    nothing left in it does not stay behind as an empty box."""

    def __init__(self):
        super().__init__()
        self._watched: list[QWidget] = []

    def watch(self, widget: QWidget):
        self._watched.append(widget)
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in {QEvent.ShowToParent, QEvent.HideToParent}:
            self.follow()
        return super().eventFilter(obj, event)

    def follow(self):
        # only once it is in the page: shown with no parent, it is a window
        self.setVisible(not all(_put_away(widget) for widget in self._watched))
        self.update()


class _FormRow(_Shown):
    """A setting, or a few on one line: the label on the left, what edits it
    on the right, and a bar on the left edge while it is changed.

    A row of nothing but slots watches them, and goes when they all do.
    """

    def __init__(self, *, joined: bool):
        super().__init__()

        # a sub-option, read as one block with the row above it
        self.joined = joined
        self.is_marked = False
        # takes the page: a list or a table, out of the card
        self.fills = False
        self.watches_slots = False

        lay = QVBoxLayout(self)
        lay.setSpacing(STACKED_SPACING)
        self._set_margins(ROW_MARGINS)

        # the line the label and the fields are on, or the fields alone,
        # under the label, for a field that takes the width of the row
        self.line = QHBoxLayout()
        self.line.setSpacing(8)
        lay.addLayout(self.line)

        # through the size hints, not a minimum height, which would be taken
        # over the layout's and let a row of two lines be squeezed into one
        self._height = SUB_ROW_HEIGHT if joined else ROW_HEIGHT

    def _set_margins(self, margins):
        left, top, right, bottom = margins
        self.layout().setContentsMargins(left, 0 if self.joined else top, right, bottom)

    def put_above(self, label: QWidget):
        """The label on a line of its own, over the fields."""

        self.layout().insertWidget(0, label)
        self._set_margins(STACKED_MARGINS)

    def make_bare(self):
        """Out of the card: a list or a table has edges of its own."""

        self.layout().setContentsMargins(0, 0, 0, 0)
        self._height = 0
        self.updateGeometry()

    def sizeHint(self):
        return super().sizeHint().expandedTo(QSize(0, self._height))

    def minimumSizeHint(self):
        return super().minimumSizeHint().expandedTo(QSize(0, self._height))

    def set_marked(self, is_marked: bool):
        if is_marked != self.is_marked:
            self.is_marked = is_marked
            self.update()

    def paintEvent(self, event):
        if not self.is_marked:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme_color(self, "text"))
        # half of it past the edge, for the round end to be only on the right
        bar = QRectF(
            -MARK_WIDTH, MARK_INSET, 2 * MARK_WIDTH, self.height() - 2 * MARK_INSET
        )
        painter.drawRoundedRect(bar, MARK_WIDTH / 2, MARK_WIDTH / 2)


class _Card(_Shown):
    """The rows of a section on the base colour, with a line between them
    and none above a sub-option."""

    def __init__(self):
        super().__init__()

        self._rows: list[_FormRow] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

    def add(self, row: _FormRow):
        self._rows.append(row)
        self.layout().addWidget(row)
        self.watch(row)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(theme_color(self, "highlight"))
        painter.setBrush(theme_color(self, "base"))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            CARD_RADIUS,
            CARD_RADIUS,
        )

        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(theme_color(self, "window"))
        shown = [row for row in self._rows if not _put_away(row)]
        for row in shown[1:]:
            if not row.joined:
                top = row.geometry().top()
                painter.drawLine(1, top, self.width() - 2, top)


class _Section(_Shown):
    """A heading, if it has one, and the cards, notes and lists under it."""

    def __init__(self, title: str | None):
        super().__init__()

        self.title = title
        # takes what the page has left, for a list or a table in it
        self.fills = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SECTION_SPACING)

        if title:
            header = QLabel(title)
            header.setOpenExternalLinks(True)
            header.setContentsMargins(2, 0, 0, 0)
            lay.addWidget(bold(header))

    def add(self, widget: QWidget, *, fills: bool = False):
        self.layout().addWidget(widget, 1 if fills else 0)
        self.fills = self.fills or fills
        self.watch(widget)


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
        mode: SettingsMode = SettingsMode.OVERRIDES,
        slots: Mapping[str, Callable[[], QWidget]] | None = None,
    ):
        super().__init__()

        self._reset_to = reset_to
        self._mode = mode
        self._slots = slots or {}

        self._editors: dict[str, Editor] = {}
        self._rows: dict[str, QWidget] = {}
        self._reset_btns: dict[str, QToolButton] = {}
        # out of reach on this system, for good
        self._unavailable: set[str] = set()
        self._hidden: set[str] = set()
        # out of reach for now, by the dialog's say
        self._locked: set[str] = set()
        self._drafts: dict[str, FieldDraft] = {}
        # as of the last sync
        self._modified: set[str] = set()
        self._updating = False
        self._fills = False

        # where rows go as the page is built: the section, and its card
        self._section: _Section | None = None
        self._card: _Card | None = None
        # the sections with a heading, in order, for links to them
        self._titled: list[tuple[str, QWidget]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SECTIONS_SPACING)

        self._add_items(items, joined=False)
        self._close_section()

        if not self._fills:
            root.addStretch(1)

        # what is modified waits for the values
        self._sync(keys=())

    # building

    def _add_items(self, items, joined):
        for item in items:
            if isinstance(item, Section):
                self._close_section()
                self._section = _Section(item.title)
                self._add_items(item.items, joined)
                self._close_section()
            elif isinstance(item, Indented):
                # under the row they belong to, on the same edge as the rest
                self._add_items(item.items, joined=True)
            elif isinstance(item, Row):
                self._place(self._add_row(item.items, joined))
            elif isinstance(item, Note):
                # under the card, which goes on after it as a new one
                self._card = None
                self._in_section().add(self._note(item))
            else:
                self._place(self._add_row((item,), joined))

    def _close_section(self):
        if self._section is None:
            return

        self.layout().addWidget(self._section, 1 if self._section.fills else 0)
        self._section.follow()
        if self._section.title:
            self._titled.append((self._section.title, self._section))
        self._fills = self._fills or self._section.fills
        self._section = self._card = None

    def _in_section(self) -> _Section:
        """The section open, or one with no heading for rows outside any."""

        if self._section is None:
            self._section = _Section(None)
        return self._section

    def _place(self, row: _FormRow):
        section = self._in_section()

        if row.fills:
            row.make_bare()
            self._card = None
            section.add(row, fills=True)
        else:
            if self._card is None:
                self._card = _Card()
                section.add(self._card)
            self._card.add(row)

        if row.watches_slots:
            # gone with what is in it, as a slot can hide itself
            row.follow()
        if self._card is not None:
            self._card.follow()

    @staticmethod
    def _note(note: Note):
        label = QLabel(note.text)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)
        label.setContentsMargins(2, 0, 0, 0)
        set_secondary(label)
        return label

    def _add_row(self, entries, joined) -> _FormRow:
        row = _FormRow(joined=joined)
        lay = row.line

        editors = []
        # a field's reset button, held back past the slots right after it:
        # a button there (a help, say) goes with the field, inside its reset
        held_reset = None
        for entry in entries:
            if isinstance(entry, Slot):
                widget = self._slots[entry.name]()
                lay.addWidget(widget, 1 if entry.fills else 0)
                row.fills = row.fills or entry.fills
                if not editors:
                    row.watch(widget)
                    row.watches_slots = True
                continue

            self._add_reset(lay, held_reset)

            editor = self._add_editor(entry, row, is_first=not editors)
            self._rows[editor.spec.settings_key] = row
            editors.append(editor)
            row.fills = row.fills or editor.fills

            held_reset = self._reset_btns.get(editor.spec.settings_key)

        self._add_reset(lay, held_reset)

        if not editors and not row.fills:
            # a button or a line of text, on the left with the labels
            lay.addStretch(1)

        if len(editors) == 1 and editors[0].tooltip:
            row.setToolTip(editors[0].tooltip)
        else:
            for editor in editors:
                if editor.tooltip:
                    editor.set_tooltip(editor.tooltip)

        return row

    def _add_editor(self, entry, row, is_first) -> Editor:
        spec = entry if isinstance(entry, SettingField) else FIELDS[entry]
        key = spec.settings_key

        editor = make_editor(spec)
        editor.changed.connect(lambda *_, key=key: self._on_edited(key))

        self._editors[key] = editor
        self._drafts[key] = FieldDraft()

        lay = row.line

        if editor.label is not None:
            if editor.stacked and is_first:
                row.put_above(editor.label)
            else:
                # the label takes the room between, and the field is on the
                # right; one that grows takes the room itself
                lay.addWidget(editor.label, 0 if editor.grows else 1)

        for widget in editor.parts():
            lay.addWidget(widget, 1 if editor.fills or editor.grows else 0)

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

            row = self._rows[key]
            # a sub-option is there only while the one it belongs to lets it
            # be changed, rather than there and greyed out
            rules = [editor.spec.shown_when]
            if row.joined:
                rules.append(editor.spec.enabled_when)
            rules = [rule for rule in rules if rule is not None]

            if key in self._hidden:
                row.setVisible(False)
            elif rules:
                row.setVisible(all(self._is_met(rule, is_on) for rule in rules))

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

            row = self._rows[key]
            row.set_marked(not self._modified.isdisjoint(self._keys_on(row)))

            reset = self._reset_btns.get(key)
            if reset is not None:
                reset.setVisible(is_modified)

    def _keys_on(self, row):
        return (key for key, on in self._rows.items() if on is row)

    def _refresh(self, keys=None):
        self._sync(keys)
        self.values_changed.emit()

    def _on_edited(self, key):
        if self._updating:
            return

        self._drafts[key].edit()
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

    def sections(self) -> list[tuple[str, QWidget]]:
        """The sections with a heading, and the heading, in order."""

        return list(self._titled)

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
            self._drafts = {}
            for key, editor in self._editors.items():
                displayed = editor.value()
                self._drafts[key] = FieldDraft(
                    values.get(key, displayed), displayed, key in (overridden or ())
                )
        finally:
            self._updating = False
        self._sync()

    def is_default(self, key: str) -> bool:
        """Has the stored value a reset would give, before presentation loss."""

        return self._value_for_save(key) == self._reset_to(key)

    def _value_for_save(self, key):
        editor = self._editors[key]
        if editor.means_default():
            return self._reset_to(key)
        return self._drafts[key].value_for_save(
            editor.value(),
            self._reset_to(key),
            preserve_original=editor.preserve_original,
        )

    def _is_modified(self, key):
        if self._out_of_reach(key):
            return False

        if self._mode is SettingsMode.OVERRIDES or self._reset_to is None:
            return self._drafts[key].is_overridden

        return not self.is_default(key)

    def is_modified(self, key: str) -> bool:
        return key in self._modified

    def is_marked(self, key: str) -> bool:
        """Its row has the bar a changed setting has."""

        return self._rows[key].is_marked

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
        self._updating = True
        try:
            if self._reset_to is not None:
                self._put(key, self._reset_to(key))
            self._drafts[key].reset(self.value(key))
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

    def persistence_result(self) -> dict[str, SetValue | ResetValue]:
        """Writes and removals; absent keys keep their stored values."""

        result = {}
        for key, draft in self._drafts.items():
            if self._out_of_reach(key):
                continue
            if (
                self._mode is SettingsMode.DEFAULTS
                and not self.is_enabled(key)
                and not draft.is_reset
            ):
                continue
            result[key] = draft.result(
                self._value_for_save(key),
                self._reset_to(key),
                self._mode,
            )
        return result

    def overridden_keys(self) -> set[str]:
        return {key for key, draft in self._drafts.items() if draft.is_overridden}
