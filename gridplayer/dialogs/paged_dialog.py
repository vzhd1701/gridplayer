"""A dialog of pages picked from an index on its left: the Settings dialog
and the Playlist window."""

from collections.abc import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPainter
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.params.settings_fields.kinds import Page
from gridplayer.params.theme import set_secondary
from gridplayer.utils.qt import translate
from gridplayer.widgets.section_links import SectionLinks
from gridplayer.widgets.settings_current_page_stack import CurrentPageStackedWidget
from gridplayer.widgets.settings_form import SettingsForm
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


class Icon(QWidget):
    """An icon of the theme, drawn as the theme is now, light or dark."""

    def __init__(self, name: str, size: int):
        super().__init__()
        self._icon = QIcon.fromTheme(name)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        self._icon.paint(QPainter(self), self.rect())


def with_note(form, text) -> tuple[QWidget, QLabel]:
    """A page with something said at the top of it, and what says it.

    Not a tooltip on any one row, because what it says is true of the
    whole page. At the top rather than the bottom because the page is
    longer than it is tall and the bottom of it is behind a scroll.
    """

    page = QWidget()

    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    note = QLabel(text)
    note.setWordWrap(True)
    note.setOpenExternalLinks(True)
    set_secondary(note)

    line = QHBoxLayout()
    line.setSpacing(8)
    line.addWidget(Icon("information", NOTE_ICON_PX), 0, Qt.AlignTop)
    line.addWidget(note, 1)

    layout.addLayout(line)
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

        # every page by its id, as it sits in the stack, and the form on it
        self.pages: dict[str, QWidget] = {}
        self.forms: dict[str, SettingsForm] = {}
        # what is said at the top of a page, by its id
        self.notes: dict[str, QLabel] = {}
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

    # building

    def build_index(self) -> QHBoxLayout:
        """The index and the pages beside it, and the Reset of the pages."""

        self.section_index = SettingsIndex()

        self.section_page = CurrentPageStackedWidget(min_width=500)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self.section_index)
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

        items = (
            self.section_index.item(row) for row in range(self.section_index.count())
        )

        return [item for item in items if item.flags() & Qt.ItemIsSelectable]

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
        self._titles[page].take(self.resetPage)
        self.update_reset_page()

    def show_page(self, page_id: str):
        self.section_index.setCurrentItem(self._index_items[page_id])

    def show_page_of(self, key: str):
        self.show_page(self._page_id_of[key])

    @property
    def current_form(self) -> SettingsForm | None:
        return self._form_on.get(self.section_page.currentWidget())

    def update_reset_page(self, *_):
        form = self.current_form
        self.resetPage.setVisible(
            form is not None and form.can_reset() and form.has_modified()
        )

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
