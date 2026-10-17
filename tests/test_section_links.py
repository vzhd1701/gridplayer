import pytest
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.settings import SECTION_LINKS_MIN, SettingsDialog


@pytest.fixture
def dialog():
    dialog = SettingsDialog(None)
    dialog.resize(760, 620)
    dialog.show()
    dialog.show_page("playlist")
    # twice: the rows put in a page are shown a pass after the page is
    QApplication.processEvents()
    QApplication.processEvents()

    yield dialog

    dialog.close()
    dialog.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _checked(links):
    return [link.text() for link in links.links if link.isChecked()]


def test_only_the_long_pages_have_them(dialog):
    for page_id, form in dialog.forms.items():
        is_long = len(form.sections()) >= SECTION_LINKS_MIN
        assert (page_id in dialog.section_links) == is_long, page_id

    assert {"player", "playlist", "video"} <= set(dialog.section_links)


def test_they_name_the_sections_in_order(dialog):
    links = dialog.section_links["playlist"]
    titles = [title for title, _ in dialog.forms["playlist"].sections()]

    assert [link.text() for link in links.links] == titles


def test_the_first_is_marked_at_the_top(dialog):
    links = dialog.section_links["playlist"]

    assert _checked(links) == [links.links[0].text()]


def test_a_click_brings_the_section_to_the_top(dialog):
    links = dialog.section_links["playlist"]
    title, section = dialog.forms["playlist"].sections()[1]
    scroll = links._scroll

    links.links[1].click()
    QApplication.processEvents()

    top = section.mapTo(scroll.widget(), section.rect().topLeft()).y()
    assert 0 < top <= scroll.verticalScrollBar().maximum()
    assert scroll.verticalScrollBar().value() == top
    assert _checked(links) == [title]


def test_the_last_one_stays_marked_when_the_page_ends_before_it(dialog):
    links = dialog.section_links["playlist"]

    links.links[-1].click()
    QApplication.processEvents()

    assert _checked(links) == [links.links[-1].text()]


def test_scrolling_moves_the_mark(dialog):
    links = dialog.section_links["playlist"]
    title, section = dialog.forms["playlist"].sections()[2]
    scroll = links._scroll

    top = section.mapTo(scroll.widget(), section.rect().topLeft()).y()
    scroll.verticalScrollBar().setValue(top + 5)

    assert _checked(links) == [title]


def test_at_the_end_of_the_page_the_last_one_is_marked(dialog):
    """The last section can't be scrolled to the top, but down at the end
    it is the one being read."""

    links = dialog.section_links["playlist"]
    bar = links._scroll.verticalScrollBar()

    bar.setValue(bar.maximum())

    assert _checked(links) == [links.links[-1].text()]
