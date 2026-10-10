"""The Settings dialog's pages: sized to the page shown, a page that scrolls
as tall as the tallest one that cannot needs to be."""

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget

from gridplayer.widgets.settings_current_page_stack import CurrentPageStackedWidget
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Page(QWidget):
    """A page that would like more room than it needs."""

    def __init__(self, height, needed=None):
        super().__init__()
        self._height = height
        self._needed = height if needed is None else needed

    def sizeHint(self):
        return QSize(100, self._height)

    def minimumSizeHint(self):
        return QSize(100, self._needed)


def _scrolling(height) -> PageScrollArea:
    inner = QWidget()
    QVBoxLayout(inner).addWidget(_Page(height))

    page = PageScrollArea()
    page.setWidget(inner)

    return page


@pytest.fixture
def stack():
    stack = CurrentPageStackedWidget()
    stack.addWidget(_Page(300, needed=250))
    stack.addWidget(_Page(200, needed=180))
    stack.addWidget(_scrolling(1000))

    return stack


def test_a_page_that_cannot_scroll_as_tall_as_it_wants(stack):
    stack.setCurrentIndex(1)

    assert stack.sizeHint().height() == 200


def test_one_that_scrolls_as_tall_as_the_tallest_that_cannot_needs(stack):
    stack.setCurrentIndex(2)

    assert stack.sizeHint().height() == 250


def test_with_none_that_cannot_as_tall_as_it_wants():
    stack = CurrentPageStackedWidget()
    page = _scrolling(1000)
    stack.addWidget(page)

    assert stack.sizeHint().height() == page.sizeHint().height()
