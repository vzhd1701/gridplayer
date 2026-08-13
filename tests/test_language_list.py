from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from gridplayer.main.init_icons import switch_icon_theme
from gridplayer.main.init_resources import init_resources
from gridplayer.params.languages import Language, LanguageAuthor
from gridplayer.widgets.language_list import (
    LanguageList,
    _author_credit_html,
    _author_plain,
    _author_tooltip,
    _selection_tint,
    _shown_author_count,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    init_resources()
    switch_icon_theme()
    return app


def _language(
    code: str,
    authors: list[LanguageAuthor] | None = None,
    completion: int = 100,
) -> Language:
    return Language(code=code, completion=completion, authors=authors or [])


def _has_checkmark(row) -> bool:
    pixmap = row.icon_checkmark.pixmap()
    return pixmap is not None and not pixmap.isNull()


def _many_authors(count: int = 7) -> list[LanguageAuthor]:
    return [
        LanguageAuthor(
            name=f"Translator Name {i} (very_long_username_{i})",
            url=f"https://crowdin.com/profile/user{i}",
        )
        for i in range(count)
    ]


def _short_authors() -> list[LanguageAuthor]:
    return [
        LanguageAuthor("Ann", "https://crowdin.com/profile/ann"),
        LanguageAuthor("Bob", "https://crowdin.com/profile/bob"),
        LanguageAuthor("Cam", "https://crowdin.com/profile/cam"),
    ]


def test_selection_tint_matches_theme_highlight():
    from gridplayer.params.theme import current_colors

    assert _selection_tint().name() == current_colors()["highlight"]


def test_author_credit_fits_names_then_overflows():
    authors = _short_authors()
    font = QFont()
    font.setPixelSize(12)

    assert _shown_author_count(authors, font, 10_000) == 3
    assert _author_credit_html(authors, 3).count("<a href=") == 3
    assert "+" not in _author_plain(authors, 3)

    narrow = _shown_author_count(authors, font, 1)
    assert narrow == 1
    assert "+2 others" in _author_plain(authors, 1)
    assert "+2 others" in _author_credit_html(authors, 1)

    tooltip = _author_tooltip(authors)
    assert tooltip == "Ann\nBob\nCam"


def test_value_roundtrip_and_left_checkmark():
    widget = LanguageList()
    widget.add_language_row(_language("en_US"))
    widget.add_language_row(_language("de_DE", _many_authors(2)))
    widget.add_language_row(_language("zh_CN", _many_authors(7), completion=84))

    widget.setValue("de_DE")
    assert widget.value() == "de_DE"

    selected = widget.itemWidget(widget.currentItem())
    assert selected is not None
    assert _has_checkmark(selected)
    assert selected.icon_checkmark.width() == selected.check_slot_size.width()
    assert selected.check_icon_size.width() >= 32

    other = widget.itemWidget(widget.item(0))
    assert other is not None
    assert not _has_checkmark(other)
    assert other.icon_checkmark.width() == other.check_slot_size.width()

    widget.setValue("en_US")
    assert widget.value() == "en_US"
    assert not _has_checkmark(selected)
    assert _has_checkmark(other)
    assert "background-color:" in other.styleSheet()
    assert "LanguageRow" in other.styleSheet()


def test_authors_collapse_and_expand_with_width():
    widget = LanguageList()
    widget.add_language_row(_language("de_DE", _short_authors()))
    widget.resize(900, 300)
    widget.show()
    QApplication.processEvents()

    row = widget.itemWidget(widget.item(0))
    assert row is not None
    assert row.authors is not None
    assert "Ann" in row.authors.text()
    assert "Bob" in row.authors.text()
    assert "Cam" in row.authors.text()
    assert "+" not in row.authors.text()
    assert row.authors.toolTip() == ""

    full_width = QFontMetrics(row.authors.font()).horizontalAdvance("Ann, Bob, Cam")
    used = (
        row.layout().contentsMargins().left()
        + row.layout().contentsMargins().right()
        + row.check_slot_size.width()
        + row.icon_flag.sizeHint().width()
        + row.layout().spacing() * 2
    )
    widget.resize(used + max(full_width // 2, 40), 300)
    QApplication.processEvents()

    assert "Ann" in row.authors.text()
    assert "+2 others" in row.authors.text()
    assert row.authors.toolTip() == "Ann\nBob\nCam"

    widget.resize(900, 300)
    QApplication.processEvents()

    assert "Cam" in row.authors.text()
    assert "+" not in row.authors.text()
    assert row.authors.toolTip() == ""
    assert widget.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff


def test_arabic_row_stays_left_aligned():
    widget = LanguageList()
    widget.add_language_row(_language("ar_SA", _many_authors(1)))
    widget.add_language_row(_language("en_US"))
    widget.resize(360, 300)
    widget.show()
    QApplication.processEvents()

    arabic = widget.itemWidget(widget.item(0))
    english = widget.itemWidget(widget.item(1))
    assert arabic is not None
    assert english is not None

    assert widget.layoutDirection() == Qt.LeftToRight
    assert arabic.layoutDirection() == Qt.LeftToRight
    assert arabic.title.layoutDirection() == Qt.LeftToRight
    assert arabic.title.alignment() & Qt.AlignAbsolute
    assert arabic.title.alignment() & Qt.AlignLeft
    assert 'dir="ltr"' in arabic.title.text()
    assert arabic.title.alignment() == english.title.alignment()


def test_clicking_authors_selects_row_without_text_selection():
    widget = LanguageList()
    widget.add_language_row(_language("en_US"))
    widget.add_language_row(_language("de_DE", _short_authors()))
    widget.resize(500, 300)
    widget.show()
    QApplication.processEvents()

    widget.setValue("en_US")
    assert widget.value() == "en_US"

    row = widget.itemWidget(widget.item(1))
    assert row is not None
    assert row.authors is not None
    assert not (row.authors.textInteractionFlags() & Qt.TextSelectableByMouse)
    assert row.authors.textInteractionFlags() & Qt.LinksAccessibleByMouse

    with patch("PyQt5.QtGui.QDesktopServices.openUrl"):
        QTest.mouseClick(row.authors, Qt.LeftButton)
        QApplication.processEvents()

    assert widget.value() == "de_DE"
    assert not (row.authors.textInteractionFlags() & Qt.TextSelectableByMouse)
