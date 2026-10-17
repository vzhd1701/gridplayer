import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.settings import SECTION_PAGE_ROLE, SettingsDialog
from gridplayer.params.settings_pages import PAGES as SETTINGS_PAGES
from gridplayer.params.theme import apply_theme, current_colors
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea

# the index as it is meant to read, group heading by group heading
SECTIONS = (
    ("General", ("Player", "Subtitle Style", "Shortcuts", "Language")),
    ("Defaults", ("Playlist", "Video")),
    ("Streaming", ("Link Resolution", "SponsorBlock", "Cookies", "Network")),
    ("Advanced", ("Video Decoder", "Logging")),
)

# which page each entry has to open, named independently of the binding
# so that a mis-ordered list of pages cannot agree with itself
PAGES = {
    "Player": "page_player",
    "Subtitle Style": "page_subtitle_style",
    "Shortcuts": "page_shortcuts",
    "Language": "page_language",
    "Playlist": "page_playlist",
    "Video": "page_video",
    "Link Resolution": "page_resolution",
    "SponsorBlock": "page_sponsorblock",
    "Cookies": "page_cookies",
    "Network": "page_network",
    "Video Decoder": "page_decoder",
    "Logging": "page_logging",
}


@pytest.fixture
def dialog():
    dialog = SettingsDialog(None)

    yield dialog

    # the app always gives this dialog a parent to own it; one made here has
    # nothing to, so it has to be taken down on the spot rather than left for
    # the garbage collector to drop in the middle of some later test
    dialog.close()
    dialog.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _rows(dialog):
    index = dialog.section_index

    return [index.item(row) for row in range(index.count())]


def _is_heading(item):
    return not (item.flags() & Qt.ItemIsSelectable)


def _as_groups(dialog):
    groups = []

    for item in _rows(dialog):
        if _is_heading(item):
            groups.append((item.text(), []))
        else:
            groups[-1][1].append(item.text())

    return tuple((heading, tuple(entries)) for heading, entries in groups)


class TestHowTheIndexReads:
    def test_it_is_grouped_the_way_it_is_meant_to_be(self, dialog):
        assert _as_groups(dialog) == SECTIONS

    def test_a_group_heading_cannot_be_picked(self, dialog):
        headings = [item.text() for item in _rows(dialog) if _is_heading(item)]

        assert headings == [heading for heading, _ in SECTIONS]

    def test_the_first_entry_is_not_a_heading(self, dialog):
        """Opening on a heading would leave the dialog showing nothing."""

        assert not _is_heading(dialog.section_items[0])


class TestEverySectionOpensItsPage:
    def test_each_one_opens_the_page_it_is_named_after(self, dialog):
        opened = {}

        for item in dialog.section_items:
            dialog.section_index.setCurrentItem(item)
            opened[item.text()] = dialog.section_page.currentWidget().objectName()

        assert opened == PAGES

    def test_none_of_them_is_bound_to_nothing(self, dialog):
        unbound = [
            item.text()
            for item in dialog.section_items
            if item.data(SECTION_PAGE_ROLE) is None
        ]

        assert unbound == []

    def test_no_page_is_left_with_no_way_in(self, dialog):
        stack = dialog.section_page
        pages = {stack.widget(i) for i in range(stack.count())}
        reachable = {item.data(SECTION_PAGE_ROLE) for item in dialog.section_items}

        assert not [page.objectName() for page in pages - reachable]

    def test_it_opens_on_the_first_section(self, dialog):
        dialog.switch_page(None)

        assert dialog.section_index.currentItem() is dialog.section_items[0]
        assert dialog.section_page.currentWidget() is dialog.pages["player"]

    def test_the_player_page_scrolls_rather_than_make_the_dialog_taller(self, dialog):
        page = dialog.pages["player"]
        wanted = page.widget().sizeHint().height()
        resolution = dialog.pages["resolution"].minimumSizeHint().height()

        assert isinstance(page, PageScrollArea)
        assert dialog.section_page.sizeHint().height() == resolution < wanted


class TestKeepingTheTwoSidesInStep:
    def test_the_index_is_made_from_the_pages(self, dialog):
        """An entry and the page it opens are one thing in settings_pages,
        so neither can be added without the other."""

        titles = [page.title for group in SETTINGS_PAGES for page in group.pages]

        assert [item.text() for item in dialog.section_items] == titles

    def test_headings_are_not_counted_as_sections(self, dialog):
        entries = sum(len(entries) for _, entries in SECTIONS)

        assert len(dialog.section_items) == entries


@pytest.fixture
def themed():
    """The app as the theme leaves it, put back after."""

    app = QApplication.instance()
    style_sheet, palette = app.styleSheet(), app.palette()

    apply_theme(app)

    yield

    app.setStyleSheet(style_sheet)
    app.setPalette(palette)


def _darkest(widget, rect):
    image = widget.grab(rect).toImage()

    return min(
        image.pixelColor(x, y).lightness()
        for x in range(image.width())
        for y in range(image.height())
    )


@pytest.mark.usefixtures("themed")
def test_headings_are_drawn_as_text_not_greyed_out(dialog):
    """They can't be picked, so they are disabled items, which the theme
    draws in the text colour rather than as something switched off."""

    index = dialog.section_index
    dialog.show()
    QApplication.processEvents()

    text = QColor(current_colors()["text"]).lightness()
    greyed = QColor(current_colors()["text_disabled"]).lightness()

    heading = _darkest(index.viewport(), index.visualItemRect(_rows(dialog)[0]))

    assert abs(heading - text) < abs(heading - greyed)


@pytest.fixture(params=[None, 14], ids=["default font", "larger font"])
def font_size(request):
    app = QApplication.instance()
    font = app.font()

    if request.param is not None:
        larger = app.font()
        larger.setPointSize(request.param)
        app.setFont(larger)

    yield request.param

    app.setFont(font)


@pytest.mark.usefixtures("font_size")
def test_no_page_is_cut_off_at_the_narrowest(dialog):
    """Nothing scrolls sideways, so a page wider than the room it is given
    loses its right end: the dialog can't be made narrower than that."""

    dialog.show()
    dialog.resize(dialog.minimumSize())
    QApplication.processEvents()

    for page_id, page in dialog.pages.items():
        dialog.show_page(page_id)
        QApplication.processEvents()

        if isinstance(page, PageScrollArea):
            content, room = page.widget(), page.viewport().width()
        else:
            content, room = page, page.width()

        assert content.minimumSizeHint().width() <= room, page_id


def test_a_sub_option_starts_on_the_same_edge_as_the_rest(dialog):
    """No step in: it goes right under the row it belongs to instead."""

    dialog.show()
    dialog.show_page_of("misc/mouse_hide_timeout")
    QApplication.processEvents()

    form = dialog.form_of("misc/mouse_hide_timeout")

    def left(key):
        widget = form.editor(key).label or form.widget(key)
        return widget.mapTo(form, QPoint()).x()

    assert left("misc/mouse_hide_timeout") == left("player/video_init_timeout")
    assert left("misc/mouse_hide_timeout") == left("misc/mouse_hide")
