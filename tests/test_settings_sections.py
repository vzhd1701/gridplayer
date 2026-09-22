import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.settings import SECTION_PAGE_ROLE, SettingsDialog

# the index as it is meant to read, group heading by group heading
SECTIONS = (
    ("General", ("Player", "Subtitle Style", "Shortcuts", "Language")),
    ("Defaults", ("Playlist", "Video")),
    ("Streaming", ("Link Resolution", "Cookies", "Network")),
    ("Advanced", ("Video Decoder", "Logging")),
)

# which page each entry has to open, named independently of the binding
# so that a mis-ordered list of pages cannot agree with itself
PAGES = {
    "Player": "page_general_player",
    "Subtitle Style": "page_subtitle_style",
    "Shortcuts": "page_general_shortcuts",
    "Language": "page_general_language",
    "Playlist": "page_defaults_playlist",
    "Video": "page_defaults_video",
    "Link Resolution": "page_streaming_resolution",
    "Cookies": "page_streaming_cookies",
    "Network": "page_streaming_network",
    "Video Decoder": "page_advanced_decoder",
    "Logging": "page_advanced_logging",
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
        assert dialog.section_page.currentWidget() is dialog.page_general_player


class TestKeepingTheTwoSidesInStep:
    def test_a_section_with_no_page_behind_it_is_refused(self, dialog):
        """A new entry in the .ui must not quietly open whatever is next."""

        dialog.section_index.addItem("Network")

        with pytest.raises(ValueError, match="section"):
            dialog.bind_section_pages()

    def test_headings_are_not_counted_as_sections(self, dialog):
        entries = sum(len(entries) for _, entries in SECTIONS)

        assert len(dialog.section_items) == entries
