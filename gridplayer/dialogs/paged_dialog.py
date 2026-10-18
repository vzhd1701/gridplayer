"""A dialog of pages picked from an index on its left: the Settings dialog
and the Playlist window; with a search over the index, in the first."""

from collections.abc import Callable

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QIcon, QKeySequence, QPainter
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QShortcut,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.params.settings_fields.kinds import Page
from gridplayer.params.theme import set_secondary
from gridplayer.utils.qt import translate
from gridplayer.utils.text_search import Query
from gridplayer.widgets.section_links import SectionLinks
from gridplayer.widgets.settings_current_page_stack import CurrentPageStackedWidget
from gridplayer.widgets.settings_form import Found, SettingsForm
from gridplayer.widgets.settings_index import SettingsIndex
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea

# where each entry in the section index keeps the page it opens
SECTION_PAGE_ROLE = Qt.UserRole

# a page with this many sections or more has links to them under its title
SECTION_LINKS_MIN = 5

PAGE_TITLE_PX = 16
SCROLL_BAR_GAP = 8
# under the last card, for the end of the page to look like an end
PAGE_END_GAP = 12
# the size the index shows the page's icon at, so it is as sharp here
PAGE_TITLE_ICON_PX = 24
NOTE_ICON_PX = 16

# between the search box and the index under it
SEARCH_SPACING = 6
# how long typing rests before the pages are searched
SEARCH_DELAY_MS = 150


class Icon(QWidget):
    """An icon of the theme, drawn as the theme is now, light or dark."""

    def __init__(self, name: str, size: int):
        super().__init__()
        self._icon = QIcon.fromTheme(name)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        self._icon.paint(QPainter(self), self.rect())


class PageNote(QWidget):
    """Something said at the top of a page, after an icon.

    Not a tooltip on any one row, because what it says is true of the
    whole page. At the top rather than the bottom because the page is
    longer than it is tall and the bottom of it is behind a scroll.
    """

    def __init__(self, text: str):
        super().__init__()

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setOpenExternalLinks(True)
        set_secondary(self._label)

        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addWidget(Icon("information", NOTE_ICON_PX), 0, Qt.AlignTop)
        line.addWidget(self._label, 1)

    def text(self) -> str:
        return self._label.text()

    def setText(self, text: str):
        self._label.setText(text)


def with_note(form, text) -> tuple[QWidget, PageNote]:
    """A page with something said at the top of it, and what says it."""

    page = QWidget()

    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    note = PageNote(text)
    layout.addWidget(note)
    layout.addWidget(form)

    return page, note


class _PageTitle(QWidget):
    """The page's icon and title, and the page's Reset at the right of it
    while that page is shown."""

    def __init__(self, page: Page):
        super().__init__()

        title = QLabel(page.title)
        font = title.font()
        font.setPixelSize(PAGE_TITLE_PX)
        font.setBold(True)
        title.setFont(font)

        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(2, 0, 0, 0)
        self._line.setSpacing(8)
        if page.icon is not None:
            self._line.addWidget(Icon(page.icon, PAGE_TITLE_ICON_PX))
        self._line.addWidget(title, 1)

    def take(self, button):
        self._line.addWidget(button, 0, Qt.AlignVCenter)


class _TextToolButton(QToolButton):
    """An icon and words, as wide as they are.

    Qt makes a tool button room for a space either side of its words and a
    little more, and draws them from the left: what was left over was all
    on the right, where the words seemed to stop short."""

    def sizeHint(self):
        hint = super().sizeHint()
        frame = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth, None, self)
        words = self.fontMetrics().horizontalAdvance(self.text())
        # Qt draws the icon with 2 px either side of it, and the words
        # right after: as much after them, and the frame
        pad = 2
        hint.setWidth(2 * frame + pad + self.iconSize().width() + pad + words + pad)
        return hint

    def minimumSizeHint(self):
        return self.sizeHint()


class PagedDialog(QDialog):
    """The index, the page picked in it under its title, and the Reset of
    the page shown. A page is a SettingsForm, or anything else, made the
    first time it is shown."""

    def __init__(self, parent):
        super().__init__(parent)

        # by name in the theme's style sheet, for its thin scroll bars
        self.setObjectName("settings_dialog")
        self.setSizeGripEnabled(True)
        self.setModal(True)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        # every page by its id, as it sits in the stack, and the form on it
        self.pages: dict[str, QWidget] = {}
        self.forms: dict[str, SettingsForm] = {}
        # what is said at the top of a page, by its id
        self.notes: dict[str, PageNote] = {}
        # the title over each page, by the page
        self._titles: dict[QWidget, _PageTitle] = {}
        # the page each setting is on, by id
        self._page_id_of: dict[str, str] = {}
        self._index_items: dict[str, QListWidgetItem] = {}
        self._form_on: dict[QWidget, SettingsForm] = {}
        # the links to the sections of a long page, by its id
        self.section_links: dict[str, SectionLinks] = {}
        # what makes a page that isn't made yet, by the page
        self._to_make: dict[QWidget, Callable[[], QWidget]] = {}

        # the search box, in a dialog that has one, and what is searched
        # for, while something is
        self.search_box: QLineEdit | None = None
        self._query: Query | None = None

    # building

    def build_index(self, *, search: bool = False) -> QHBoxLayout:
        """The index and the pages beside it, and the Reset of the pages;
        a search box over the index, if asked for."""

        self.section_index = SettingsIndex()

        self.section_page = CurrentPageStackedWidget(min_width=500)

        index = QVBoxLayout()
        index.setSpacing(SEARCH_SPACING)
        if search:
            index.addWidget(self._build_search())
        index.addWidget(self.section_index, 1)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addLayout(index)
        body.addWidget(self.section_page)

        # in the title of the page shown, see switch_page; shown, as the
        # reset beside a field, only while there is something to reset
        self.resetPage = _TextToolButton(self)
        self.resetPage.setIcon(QIcon.fromTheme("reset"))
        self.resetPage.setText(translate("SettingsDialog", "Reset"))
        self.resetPage.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.resetPage.setAutoRaise(True)
        self.resetPage.setToolTip(self.reset_tooltip())
        self.resetPage.hide()

        return body

    def _build_search(self) -> QLineEdit:
        self.search_box = QLineEdit()
        self.search_box.setObjectName("settings_search")
        self.search_box.setPlaceholderText(translate("SettingsDialog", "Search"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.addAction(QIcon.fromTheme("zoom"), QLineEdit.LeadingPosition)
        self.search_box.setFixedWidth(self.section_index.width())
        self.search_box.installEventFilter(self)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self.search_now)
        self.search_box.textChanged.connect(self._search_timer.start)

        find = QShortcut(QKeySequence.Find, self)
        find.activated.connect(self.focus_search)

        # where the rows would be, when nothing is found
        self._nothing_found = QLabel()
        self._nothing_found.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self._nothing_found.setContentsMargins(0, 80, 0, 0)
        self._nothing_found.setWordWrap(True)
        set_secondary(self._nothing_found)
        self.section_page.addWidget(self._nothing_found)

        return self.search_box

    def add_heading(self, title: str):
        self.section_index.add_heading(title)

    def add_form_page(
        self, page: Page, form: SettingsForm, note: str | None = None
    ) -> QWidget:
        """A page of settings; the note, if given, in place of the page's."""

        self.forms[page.id] = form
        for key in form.keys():
            self._page_id_of[key] = page.id

        note = page.note if note is None else note

        content = form
        if note is not None:
            content, self.notes[page.id] = with_note(form, note)

        widget, layout = self._add_page(page)

        if page.scroll:
            # clear of the scroll bar, and room under the end
            content.layout().setContentsMargins(0, 0, SCROLL_BAR_GAP, PAGE_END_GAP)
            scroll = PageScrollArea()
            layout.addWidget(scroll, 1)
            scroll.setWidget(content)

            if len(form.sections()) >= SECTION_LINKS_MIN:
                self.section_links[page.id] = SectionLinks(scroll, form.sections())
                layout.insertWidget(1, self.section_links[page.id])
        else:
            layout.addWidget(content, 1)

        self._form_on[widget] = form

        return widget

    def add_later_page(self, page: Page, make: Callable[[], QWidget]) -> QWidget:
        """A page made only once it is shown: one that is slow to make, or
        that starts work of its own."""

        widget, _layout = self._add_page(page)

        self._to_make[widget] = make

        return widget

    def _add_page(self, page: Page) -> tuple[QWidget, QVBoxLayout]:
        # the title over what scrolls, so it stays in view
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        title = _PageTitle(page)
        layout.addWidget(title)
        self.section_page.addWidget(widget)

        widget.setObjectName(f"page_{page.id}")

        self.pages[page.id] = widget
        self._titles[widget] = title

        item = self.section_index.add_page(page.title, page.icon)
        item.setData(SECTION_PAGE_ROLE, widget)
        self._index_items[page.id] = item

        return widget, layout

    def connect_pages(self):
        self.section_index.currentItemChanged.connect(self.switch_page)
        self.section_index.itemSelectionChanged.connect(self.keep_index_selection)

        self.resetPage.clicked.connect(self.ask_reset_page)

        for form in self.forms.values():
            form.values_changed.connect(self.update_reset_page)

    def fit_to_screen(self):
        """As small as the pages let it be, but taller: the hints are only
        what every page needs, and the long ones show more than a few rows
        at a time."""

        self.adjustSize()
        room = self.screen().availableGeometry().height() * 2 // 3
        self.resize(self.width(), max(self.height(), room))

    # the settings, wherever they are

    def form_of(self, key: str) -> SettingsForm:
        return self.forms[self._page_id_of[key]]

    def widget(self, key: str) -> QWidget:
        """What a setting is edited with."""

        return self.form_of(key).widget(key)

    def value(self, key: str):
        """A setting as the page has it now, saved or not."""

        return self.form_of(key).value(key)

    # pages

    @property
    def section_items(self):
        """The entries that open a page, leaving out the group headings."""

        return self.section_index.page_items()

    def keep_index_selection(self):
        if not self.section_index.selectedItems():
            self.section_index.setCurrentItem(self.section_index.currentItem())

    def switch_page(self, section_item, _previous=None):
        if section_item is None:
            self.section_index.setCurrentItem(self.section_items[0])
            return

        page = section_item.data(SECTION_PAGE_ROLE)

        if page is None:
            return

        make = self._to_make.pop(page, None)
        if make is not None:
            page.layout().addWidget(make(), 1)

        self.section_page.setCurrentWidget(page)
        if page in self._form_on:
            self._form_on[page].back_from_search()
        self._titles[page].take(self.resetPage)
        self.update_reset_page()

    def show_page(self, page_id: str):
        self.section_index.setCurrentItem(self._index_items[page_id])

    def show_page_of(self, key: str):
        # out of a search, which could leave its row out
        self.end_search()
        self.show_page(self._page_id_of[key])

    @property
    def current_form(self) -> SettingsForm | None:
        return self._form_on.get(self.section_page.currentWidget())

    def update_reset_page(self, *_):
        # not while searching: it would reset rows out of sight
        form = self.current_form
        self.resetPage.setVisible(
            self._query is None
            and form is not None
            and form.can_reset()
            and form.has_modified()
        )

    # searching

    def focus_search(self):
        self.search_box.setFocus(Qt.ShortcutFocusReason)
        self.search_box.selectAll()

    def search(self, text: str):
        """The pages searched for the text at once, as if typed."""

        self.search_box.setText(text)
        self.search_now()

    def end_search(self):
        if self.search_box is not None and self.search_box.text():
            self.search_box.clear()
            self.search_now()

    def _search_waiting(self):
        """What is typed searched now, if it isn't yet."""

        if self._search_timer.isActive():
            self.search_now()

    def search_now(self):
        self._search_timer.stop()

        query = Query(self.search_box.text())
        if not query:
            self.show_search(None)
            return

        found = {
            page_id: form.find(query, self._index_items[page_id].text())
            for page_id, form in self.forms.items()
        }

        # a tooltip says more than a name, and finds more: only when no
        # name has the words, whatever a list finds in itself
        if any(
            not f.by_tooltip and not f.by_content
            for page in found.values()
            for f in page
        ):
            found = {
                page_id: [f for f in page if not f.by_tooltip]
                for page_id, page in found.items()
            }

        self.show_search(query, found)

    def show_search(
        self, query: Query | None, found: dict[str, list[Found]] | None = None
    ):
        """Only what was found, on every page, and how much on each; or
        everything back, with no query."""

        if query is None and self._query is None:
            return

        self._query = query
        found = found or {}

        for page_id, form in self.forms.items():
            # the page as it is, only while it is all there: first, for the
            # form to scroll in the room they leave it
            if page_id in self.section_links:
                self.section_links[page_id].setVisible(query is None)
            if page_id in self.notes:
                self.notes[page_id].setVisible(query is None)

            page_found = found.get(page_id, [])
            form.show_found(query, page_found)

            count = None if query is None else sum(f.count for f in page_found)
            self.section_index.set_found(self._index_items[page_id], count)

        if query is None:
            self.switch_page(self.section_index.currentItem())
        else:
            self._show_found_page(query, found)

    def _show_found_page(self, query: Query, found: dict[str, list[Found]]):
        # the page open, if anything was found on it; or the first with a
        # setting found, rather than one with only a list that found its own
        current = self.section_index.currentItem()
        if current is not None and self.section_index.can_pick(current):
            self.switch_page(current)
            return

        def has_settings(page_id):
            return any(not f.by_content for f in found.get(page_id, []))

        page_ids = [page_id for page_id in self._index_items if found.get(page_id)]
        page_ids.sort(key=lambda page_id: not has_settings(page_id))
        if page_ids:
            self.section_index.setCurrentItem(self._index_items[page_ids[0]])
            return

        self._nothing_found.setText(
            translate("SettingsDialog", 'Nothing found for "{TEXT}".').format(
                TEXT=query.text
            )
        )
        self.section_page.setCurrentWidget(self._nothing_found)
        self.update_reset_page()

    def _focus_found(self):
        """The first setting found on the page open, for Enter in the box."""

        form = self.current_form
        key = None if form is None else form.found_key()
        if key is not None:
            form.point_to(key)

    def eventFilter(self, obj, event):
        if obj is self.search_box and event.type() == QEvent.KeyPress:
            key = event.key()
            # Esc empties the box first, and closes the dialog only then
            if key == Qt.Key_Escape and self.search_box.text():
                self.end_search()
                return True
            # not OK, as Enter is anywhere else in the dialog
            if key in {Qt.Key_Return, Qt.Key_Enter}:
                self._search_waiting()
                self._focus_found()
                return True
            if key == Qt.Key_Down:
                self._search_waiting()
                self.section_index.setFocus(Qt.TabFocusReason)
                return True

        return super().eventFilter(obj, event)

    def reset_tooltip(self) -> str:
        return translate(
            "SettingsDialog", "Put the settings on this page back to default"
        )

    def reset_info(self) -> str:
        return translate(
            "SettingsDialog",
            "They go back to their defaults. Nothing is saved until you press OK.",
        )

    def ask_reset_page(self):
        is_reset = QCustomMessageBox.confirm(
            self,
            translate("SettingsDialog", "Reset page"),
            translate("SettingsDialog", "Reset all settings on this page?"),
            translate("SettingsDialog", "Reset"),
            info=self.reset_info(),
            is_destructive=True,
        )
        if is_reset:
            self.reset_page()

    def reset_page(self):
        """The page back to what a reset goes back to, until Cancel."""

        form = self.current_form
        if form is not None:
            form.reset_all()
