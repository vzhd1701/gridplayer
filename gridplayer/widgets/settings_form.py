from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from PyQt5.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import QIcon, QPainter
from PyQt5.QtWidgets import (
    QAbstractButton,
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QScrollBar,
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
from gridplayer.utils.qt import bold, translate
from gridplayer.utils.text_search import Query, plain_text
from gridplayer.widgets.settings_controls import fit_fields, paint_card, theme_color
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

# the bar on the left edge of a changed row
MARK_WIDTH = 3

# rows shown when a setting is changed: how far from the edge of the page
# they are scrolled to, and how quickly
REVEAL_MARGIN = 12
SCROLL_MS = 200

# between the heading of a section and its card, and the card and a note
SECTION_SPACING = 8
# between one section and the next
SECTIONS_SPACING = 20

# a drop-down with more options than this (the fonts) isn't searched by them:
# among so many, some would have every word typed
SEARCHED_OPTIONS_MAX = 20

# a default not looked up yet, as None can be one
_NOT_LOOKED_UP = object()


def _scroll_by(bar: QScrollBar, step: int):
    """Down a little, smoothly, for the eye to follow where it went."""

    animation = QVariantAnimation(bar)
    animation.setStartValue(bar.value())
    animation.setEndValue(min(bar.value() + step, bar.maximum()))
    animation.setDuration(SCROLL_MS)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.valueChanged.connect(bar.setValue)
    animation.start(QAbstractAnimation.DeleteWhenStopped)


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
        # only once it is in the page: shown with no parent, it is a window,
        # and flashes up on the desktop; it follows when it is put in one
        if self.parentWidget() is None:
            return

        self.setVisible(not all(_put_away(widget) for widget in self._watched))
        self.update()


class _FormRow(QWidget):
    """A setting, or a few on one line: the label on the left, what edits it
    on the right, and a bar on the left edge while it is changed."""

    def __init__(self, *, joined: bool):
        super().__init__()

        # a sub-option, read as one block with the row above it
        self.joined = joined
        self.is_marked = False
        # the settings on it, in order
        self.keys: list[str] = []
        # takes the page: a list or a table, out of the card
        self.fills = False
        # why a search found it, when its name doesn't say
        self.hint: QLabel | None = None
        # why it can't be changed, said under it
        self.note: QLabel | None = None

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

    def _grey_line(self, text="") -> QLabel:
        line = QLabel(text)
        set_secondary(line)
        self.layout().addWidget(line)
        return line

    def set_hint(self, text: str | None):
        """A grey line under the row for a search, or none."""

        if text is None:
            if self.hint is not None:
                self.hint.hide()
            return

        if self.hint is None:
            self.hint = self._grey_line()

        self.hint.setText(text)
        self.hint.show()

    def add_note(self, text: str):
        """A grey line under the row for good."""

        self.note = self._grey_line(text)

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
        # a list or a table says itself what is changed in it, and the bar
        # down the whole of its side would be a black stripe
        if self.fills:
            is_marked = False

        if is_marked != self.is_marked:
            self.is_marked = is_marked
            self.update()

    def mark_bar(self) -> QRectF:
        """Along what is in the row, which a sub-option has nearer its top
        than its bottom; half of it past the edge, for the round end to be
        only on the right."""

        content = self.layout().contentsRect()
        return QRectF(-MARK_WIDTH, content.top(), 2 * MARK_WIDTH, content.height())

    def paintEvent(self, event):
        if not self.is_marked:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme_color(self, "text"))
        painter.drawRoundedRect(self.mark_bar(), MARK_WIDTH / 2, MARK_WIDTH / 2)


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
        fit_fields(self)

    def changeEvent(self, event):
        if event.type() == QEvent.PaletteChange:
            fit_fields(self)
        super().changeEvent(event)

    def paintEvent(self, event):
        painter = paint_card(self)

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
        self.header: QLabel | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SECTION_SPACING)

        if title:
            self.header = QLabel(title)
            self.header.setOpenExternalLinks(True)
            self.header.setContentsMargins(2, 0, 0, 0)
            bold(self.header)
            lay.addWidget(self.header)

    def add(self, widget: QWidget, *, fills: bool = False):
        self.layout().addWidget(widget, 1 if fills else 0)
        self.fills = self.fills or fills
        self.watch(widget)


@dataclass
class _Searched:
    """What a search reads of a row."""

    row: _FormRow
    section: _Section | None
    # its fields' labels, the slots' labels and the options shown as buttons
    names: list[str] = field(default_factory=list)
    # the options of its drop-downs, which aren't in sight but the one picked
    options: list[str] = field(default_factory=list)
    drop_downs: list[QWidget] = field(default_factory=list)
    tooltips: list[str] = field(default_factory=list)
    # what the dialog put in it, read as it is when searched
    slots: list[QWidget] = field(default_factory=list)
    # a list or a table that searches itself
    fill: Editor | None = None


@dataclass
class Found:
    """A row a search found, and how."""

    row: _FormRow
    # by its tooltip alone, which says more than its name, and finds more
    by_tooltip: bool = False
    # the option it was found by, for one found by an option in a drop-down
    option: str | None = None
    # what in it was found: one for a row, as many as a list or a table found
    count: int = 1
    # a list or a table found by what is in it, and filtered to that
    by_content: bool = False


def _slot_texts(widget: QWidget) -> tuple[list[str], list[str]]:
    """What a slot says, and its tooltips: the texts of its buttons and
    labels, and its own."""

    parts = [
        widget,
        *widget.findChildren(QAbstractButton),
        *widget.findChildren(QLabel),
    ]

    texts, tooltips = [], []
    for part in parts:
        if isinstance(part, QAbstractButton | QLabel) and part.text():
            texts.append(plain_text(part.text()))
        if part.toolTip():
            tooltips.append(plain_text(part.toolTip()))
    return texts, tooltips


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
        # the fields another one can force, and the own value of those it
        # does now
        self._forceable: list[str] = []
        self._forced: dict[str, object] = {}
        self._drafts: dict[str, FieldDraft] = {}
        # as of the last sync: what can be changed, and what is changed
        self._enabled: dict[str, bool] = {}
        self._modified: set[str] = set()
        self._updating = False
        self._fills = False

        # where rows go as the page is built: the section, and its card
        self._section: _Section | None = None
        self._card: _Card | None = None
        # the sections with a heading, in order, for links to them
        self._titled: list[tuple[str, QWidget]] = []

        # every row, as a search reads it
        self._searched: list[_Searched] = []
        # the rows a search shows, found or not, or None while not searching
        self._search_shown: set[_FormRow] | None = None
        self._found: list[Found] = []
        # the labels marked where they were found, and what they said
        self._marked_labels: list[tuple[QLabel, str, Qt.TextFormat]] = []
        # away while searching, as the page's own
        self._notes: list[QLabel] = []
        # where the page was as a search began, and what it goes back to
        # after it, once shown again: there, or a field gone to meanwhile
        self._before_search: tuple[int, QWidget | None] | None = None
        self._scroll_back: int | QWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SECTIONS_SPACING)

        self._add_items(items, joined=False)
        self._close_section()

        # the room under the rows; on a page a list or a table fills, only
        # once a search has put it away, rather than the cards stretched
        root.addStretch(0 if self._fills else 1)

        # what is modified waits for the values
        self._sync(keys=())

    def showEvent(self, event):
        super().showEvent(event)

        # rows come back as the page is shown, before it is first painted:
        # the dialog opened with them squeezed, see _settle
        self._settle()

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
                note = self._note(item)
                self._notes.append(note)
                self._in_section().add(note)
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

        searched = _Searched(row, self._section)
        self._searched.append(searched)

        editors = []
        # a field's reset button, held back past the slots right after it:
        # a button there (a help, say) goes with the field, inside its reset
        held_reset = None
        is_labelled = False
        for entry in entries:
            if isinstance(entry, Slot):
                widget = self._slots[entry.name]()
                searched.slots.append(widget)
                if entry.label is not None:
                    lay.addWidget(QLabel(entry.label), 1)
                    searched.names.append(entry.label)
                    is_labelled = True
                lay.addWidget(widget, 1 if entry.fills else 0)
                row.fills = row.fills or entry.fills
                continue

            self._add_reset(lay, held_reset)

            editor = self._add_editor(entry, row, is_first=not editors)
            self._rows[editor.spec.settings_key] = row
            row.keys.append(editor.spec.settings_key)
            editors.append(editor)
            row.fills = row.fills or editor.fills
            self._note_searched(searched, editor)

            held_reset = self._reset_btns.get(editor.spec.settings_key)

        self._add_reset(lay, held_reset)

        if is_labelled and not editors:
            # no reset of its own, but its room: ending where the fields do
            self._add_reset(lay, self._make_reset())
        elif not editors and not row.fills:
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
        if spec.forced_when is not None:
            self._forceable.append(key)

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

        self._check_available(spec, row)

        return editor

    @staticmethod
    def _note_searched(searched: _Searched, editor: Editor):
        if editor.spec.label:
            searched.names.append(editor.spec.label)
        if editor.tooltip:
            searched.tooltips.append(plain_text(editor.tooltip))
        if editor.fills:
            searched.fill = editor

        options = editor.options()
        if editor.drop_down is None:
            searched.names.extend(options)
        else:
            searched.drop_downs.append(editor.drop_down)
            if len(options) <= SEARCHED_OPTIONS_MAX:
                searched.options.extend(options)

    @staticmethod
    def _add_reset(lay, reset):
        if reset is not None:
            lay.addWidget(reset, alignment=Qt.AlignVCenter)

    def _reset_button(self, key):
        reset = self._make_reset()
        reset.clicked.connect(lambda _=False, key=key: self.reset(key))

        self._reset_btns[key] = reset
        return reset

    @staticmethod
    def _make_reset():
        reset = QToolButton()
        reset.setIcon(QIcon.fromTheme("reset"))
        reset.setIconSize(QSize(RESET_ICON_PX, RESET_ICON_PX))
        reset.setAutoRaise(True)
        reset.setToolTip(translate("SettingsDialog", "Reset"))
        reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # taking up its room while hidden, so nothing moves when it shows
        policy = reset.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        reset.setSizePolicy(policy)
        reset.hide()

        return reset

    def _check_available(self, spec, row):
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
            if spec.note_unavailable:
                row.add_note(reason)

    # what is on and what is shown

    def _sync(self, keys=None, *, reveal=True):
        """What is on and shown, all of it; and what is modified, of these
        keys or all of them."""

        enabled = {}

        def is_on(key):
            if key not in enabled:
                enabled[key] = False  # what names itself is off
                enabled[key] = self._is_on(key, is_on)
            return enabled[key]

        forced = self._follow_forced(is_on)
        if keys is not None and forced:
            keys = (*keys, *forced)

        # a row of a few fields is shown while all of them may be
        shown: dict[_FormRow, bool] = {}
        for key, editor in self._editors.items():
            editor.set_enabled(is_on(key))

            row = self._rows[key]
            shown[row] = shown.get(row, True) and self._is_shown(key, is_on)

        self._enabled = enabled

        moved, revealed = False, []
        for row, is_shown in shown.items():
            if is_shown == _put_away(row):
                row.setVisible(is_shown)
                moved = True
                if is_shown:
                    revealed.append(row)

        self._sync_modified(keys)

        if moved and self.isVisible():
            self._settle()
            if reveal:
                self._point_out(revealed)

    def _is_shown(self, key, is_on) -> bool:
        if key in self._hidden:
            return False

        row = self._rows[key]
        spec = self._editors[key].spec

        # a sub-option is there only while the one it belongs to lets it
        # be changed, rather than there and greyed out
        rules = [spec.shown_when]
        if row.joined:
            rules.append(spec.enabled_when)
        rules = [rule for rule in rules if rule is not None]

        is_met = all(self._is_met(rule, is_on) for rule in rules)

        if self._search_shown is None:
            return is_met

        # found, or what it belongs to, greyed out or not
        if row in self._search_shown:
            return True

        # brought by a row the search shows, as it would be without the search
        return is_met and any(
            self._rows.get(rule.key) in self._search_shown for rule in rules
        )

    def _point_out(self, rows):
        """Rows shown just now, scrolled to, so that they are not missed
        below the one that brought them."""

        scroll = self._scroll_area()
        if scroll is None or not rows:
            return

        viewport = scroll.viewport()
        top = rows[0].mapTo(viewport, QPoint(0, 0)).y() - REVEAL_MARGIN
        bottom = (
            rows[-1].mapTo(viewport, QPoint(0, rows[-1].height())).y() + REVEAL_MARGIN
        )

        bar = scroll.verticalScrollBar()
        if bottom > viewport.height():
            # the last of them in view, but never the first out of it
            step = min(bottom - viewport.height(), max(top, 0))
            _scroll_by(bar, step)

    def _scroll_area(self) -> QScrollArea | None:
        scroll = self.parentWidget()
        while scroll is not None and not isinstance(scroll, QScrollArea):
            scroll = scroll.parentWidget()
        return scroll

    def point_to(self, key: str):
        """A setting's row scrolled into view, and its field given the focus,
        for one asked about elsewhere: on a page just shown too, which is
        laid out first for the row to be where it will be."""

        self._settle()

        self._into_view(self._rows[key])
        self._editors[key].widget.setFocus(Qt.OtherFocusReason)

    def _into_view(self, widget: QWidget):
        scroll = self._scroll_area()
        if scroll is not None:
            # in the middle, where the eye is, rather than at an edge
            middle = (scroll.viewport().height() - widget.height()) // 2
            scroll.ensureWidgetVisible(widget, 0, max(middle, REVEAL_MARGIN))

    @staticmethod
    def _settle():
        """The page at its new height before it is painted.

        A row shown lays out the page at once, but in the height it had: in
        a scroll area, the page is made taller only once the event loop comes
        round to it, and a paint already on its way would show every row
        squeezed for a moment.
        """

        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)

    def _out_of_reach(self, key) -> bool:
        return key in self._unavailable

    def _is_forced(self, key, is_on) -> bool:
        rule = self._editors[key].spec.forced_when
        return rule is not None and self._is_met(rule, is_on)

    def _follow_forced(self, is_on) -> list[str]:
        """The forced value shown in a field another one forces, its own
        kept meanwhile and shown again once it isn't. The fields that went
        from one to the other."""

        changed = []
        for key in self._forceable:
            is_forced = self._is_forced(key, is_on)
            if is_forced == (key in self._forced):
                continue

            editor = self._editors[key]
            self._updating = True
            try:
                if is_forced:
                    self._forced[key] = editor.value()
                    editor.set_value(editor.spec.forced_value)
                else:
                    editor.set_value(self._forced.pop(key))
            finally:
                self._updating = False
            changed.append(key)

        return changed

    def _own_value(self, key):
        """What a field has of its own: what its editor shows, unless
        another field forces it."""

        if key in self._forced:
            return self._forced[key]
        return self._editors[key].value()

    def _is_on(self, key, is_on) -> bool:
        if self._out_of_reach(key) or self._is_forced(key, is_on):
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
            row.set_marked(not self._modified.isdisjoint(row.keys))

            reset = self._reset_btns.get(key)
            if reset is not None:
                reset.setVisible(is_modified)

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

    def can_reset(self) -> bool:
        """Has a field with a reset beside it: one that fills the page, as
        the shortcuts do, comes with resets of its own."""

        return bool(self._reset_btns)

    def sections(self) -> list[tuple[str, QWidget]]:
        """The sections with a heading, and the heading, in order."""

        return list(self._titled)

    # searching

    def find(self, query: Query, page_title: str = "") -> list[Found]:
        """The rows the words are in, in order: in a row's names, its
        section's heading or the page's title, or in what can be picked in
        it; in its tooltips, failing that; or found by a list or a table in
        it. Nothing out of sight for good is found."""

        found = []
        for searched in self._searched:
            if not self._can_find(searched):
                continue

            section = searched.section.title if searched.section is not None else None
            names = [page_title, plain_text(section or ""), *searched.names]
            names.extend(combo.currentText() for combo in searched.drop_downs)
            slot_tooltips = []
            for slot in searched.slots:
                texts, tooltips = _slot_texts(slot)
                names.extend(texts)
                slot_tooltips.extend(tooltips)

            # each kind of text read once: the names, then what can be
            # picked, then the tooltips
            words = set(query.words)
            in_names = query.found_in(names)
            in_options = in_names | query.found_in(searched.options)

            if in_names == words:
                found.append(Found(searched.row))
            elif in_options == words:
                option = self._found_option(query, in_names, searched)
                found.append(Found(searched.row, option=option))
            elif (
                in_options | query.found_in(searched.tooltips + slot_tooltips) == words
            ):
                found.append(Found(searched.row, by_tooltip=True))
            elif searched.fill is not None:
                count = searched.fill.count_found(query.text)
                if count:
                    found.append(Found(searched.row, count=count, by_content=True))

        return found

    def _can_find(self, searched: _Searched) -> bool:
        return not searched.row.keys or not all(
            key in self._hidden for key in searched.row.keys
        )

    @staticmethod
    def _found_option(query: Query, in_names, searched: _Searched) -> str | None:
        for option in searched.options:
            if query.found_words(option) - in_names:
                return option
        return None

    def show_found(self, query: Query | None, found: Iterable[Found] = ()):
        """Only the rows found, and what they belong to, with what was found
        in them marked; with no query, every row back as it was."""

        scroll = self._scroll_area()
        bar = None if scroll is None else scroll.verticalScrollBar()
        if bar is not None and query is not None and self._before_search is None:
            # before the rows go, and the room scrolled through with them
            self._before_search = (bar.value(), self.focusWidget())

        self._unmark()

        self._found = [] if query is None else list(found)
        by_row = {found.row: found for found in self._found}

        if query is None:
            self._search_shown = None
        else:
            self._search_shown = set(by_row) | self._belonged_to(by_row)

        for searched in self._searched:
            row = searched.row

            if not row.keys:
                # a row of slots alone, which the rules leave alone
                row.setVisible(self._search_shown is None or row in self._search_shown)

            row_found = by_row.get(row)
            option = None if row_found is None else row_found.option
            row.set_hint(
                None
                if option is None
                else translate("SettingsDialog", "Option: {OPTION}").format(
                    OPTION=option
                )
            )

            if searched.fill is not None:
                is_by_content = row_found is not None and row_found.by_content
                searched.fill.show_found(query.text if is_by_content else None)

            if row_found is not None:
                self._mark(query, searched)

        for note in self._notes:
            note.setVisible(query is None)

        self._sync(keys=(), reveal=False)

        if bar is None:
            return
        if query is None:
            self._scroll_back = self._back_to()
        else:
            bar.setValue(0)

    def _back_to(self) -> int | QWidget | None:
        """Where the page was as the search began, or the row of the field
        gone to in it."""

        if self._before_search is None:
            return None
        value, focused = self._before_search
        self._before_search = None

        now = self.focusWidget()
        if now is None or now is focused or not now.isVisibleTo(self):
            return value
        return next((row for row in self._rows.values() if row.isAncestorOf(now)), now)

    def back_from_search(self):
        """Where the page was before a search, or at the field gone to in
        it, for a page shown: laid out only then."""

        to, self._scroll_back = self._scroll_back, None
        if to is None:
            return

        self._settle()
        if isinstance(to, QWidget):
            self._into_view(to)
        else:
            self._scroll_area().verticalScrollBar().setValue(to)

    def _belonged_to(self, rows) -> set[_FormRow]:
        """The rows of the settings these rows' settings belong to, and theirs."""

        belonged = set()
        keys = [key for row in rows for key in row.keys]
        while keys:
            spec = self._editors[keys.pop()].spec
            for rule in (spec.shown_when, spec.enabled_when):
                row = None if rule is None else self._rows.get(rule.key)
                if row is not None and row not in belonged and row not in rows:
                    belonged.add(row)
                    keys.append(rule.key)
        return belonged

    def _mark(self, query: Query, searched: _Searched):
        labels = [self._editors[key].marked for key in searched.row.keys]
        if searched.section is not None:
            labels.append(searched.section.header)

        for label in labels:
            if label is None or any(label is done for done, *_ in self._marked_labels):
                continue

            text = label.text()
            if not query.spans(plain_text(text)):
                continue

            self._marked_labels.append((label, text, label.textFormat()))
            color = theme_color(label, "highlight").name()
            label.setTextFormat(Qt.RichText)
            label.setText(
                query.marked(
                    text,
                    f'<span style="background-color:{color}">',
                    is_html=plain_text(text) != text,
                )
            )

    def _unmark(self):
        for label, text, text_format in self._marked_labels:
            label.setTextFormat(text_format)
            label.setText(text)
        self._marked_labels = []

    def found_key(self) -> str | None:
        """The first setting found, for the focus to go to."""

        for found in self._found:
            for key in found.row.keys:
                if self.is_enabled(key):
                    return key
        return None

    def editor(self, key: str) -> Editor:
        return self._editors[key]

    def widget(self, key: str) -> QWidget:
        return self._editors[key].widget

    def value(self, key: str):
        return self._editors[key].value()

    def values(self) -> dict:
        return {key: editor.value() for key, editor in self._editors.items()}

    def set_values(self, values: dict, overridden: set[str] | None = None):
        # forced again by the sync below, if still so; one not given keeps
        # its own
        self._forced = {
            key: own for key, own in self._forced.items() if key not in values
        }

        self._updating = True
        try:
            for key in self._editors:
                if key in values:
                    self._put(key, values[key])
            self._drafts = {}
            for key in self._editors:
                displayed = self._own_value(key)
                self._drafts[key] = FieldDraft(
                    values.get(key, displayed), displayed, key in (overridden or ())
                )
        finally:
            self._updating = False
        self._sync()

    def set_mode(self, mode: SettingsMode):
        """What counts as changed from now on: a value of the playlist's
        own, or one other than a reset gives."""

        if mode is self._mode:
            return

        self._mode = mode
        self._refresh()

    def add_mark(self, key: str, mark: QWidget):
        """Something right after a setting's label, as the playlist's own
        value is marked in the Settings dialog."""

        label = self._editors[key].label
        row = self._rows[key]

        if label is None:
            row.line.insertWidget(0, mark)
            return

        lay = row.line
        at = lay.indexOf(label)

        if at < 0:
            # a label on a line of its own, over the fields
            lay = row.layout()
            at = lay.indexOf(label)
            line = QHBoxLayout()
            line.setSpacing(lay.spacing())
            lay.insertLayout(at, line)
            line.addWidget(label)
            at = 0

        # the label as wide as its words, and the room it took after the mark
        lay.setStretch(at, 0)
        lay.insertWidget(at + 1, mark, 0, Qt.AlignVCenter)
        lay.insertStretch(at + 2, 1)

    def text_of(self, key: str, value) -> str | None:
        """A value in words, as its field shows it; None for a field that
        doesn't show it in words (a colour, a crop)."""

        return self._editors[key].text_of(self._shown(key, value))

    def is_default(self, key: str) -> bool:
        """Has the stored value a reset would give, before presentation loss."""

        default = self._reset_to(key)
        return self._value_for_save(key, default) == default

    def _value_for_save(self, key, default=_NOT_LOOKED_UP):
        # what a reset gives, if already looked up: a lookup can be a read
        # of the stored settings
        if default is _NOT_LOOKED_UP:
            default = self._reset_to(key)

        editor = self._editors[key]
        if editor.means_default():
            return default
        return self._drafts[key].value_for_save(
            self._own_value(key), default, preserve_original=editor.preserve_original
        )

    def _is_modified(self, key):
        # forced, it says nothing of its own
        if self._out_of_reach(key) or key in self._forced:
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
                default = self._reset_to(key)
                if key in self._forced:
                    # its own value, shown once it isn't forced
                    self._forced[key] = self._shown(key, default)
                else:
                    self._put(key, default)
            self._drafts[key].reset(self._own_value(key))
        finally:
            self._updating = False

    def is_enabled(self, key: str) -> bool:
        """Can be changed, by the rules and what they name; what is greyed
        out isn't saved in the Settings dialog, unless it was reset."""

        return self._enabled.get(key, False)

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
            default = self._reset_to(key)
            result[key] = draft.result(
                self._value_for_save(key, default), default, self._mode
            )
        return result

    def saved_values(self) -> dict:
        """Every value as it would be saved, changed or not."""

        return {
            key: self._value_for_save(key)
            for key in self._editors
            if not self._out_of_reach(key)
        }

    def overridden_keys(self) -> set[str]:
        return {key for key, draft in self._drafts.items() if draft.is_overridden}
