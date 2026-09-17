import json
import time
from datetime import datetime, timezone

import pytest
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QTableWidgetSelectionRange,
)

from gridplayer.utils.cookies import parse_cookies
from gridplayer.widgets.cookie_store_list import (
    COUNT_COLUMN,
    DOMAIN_COLUMN,
    EXPIRES_COLUMN,
    CookieStoreList,
)

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"

LONG_AFTER = 4102444800  # 2100
LONG_AGO = 1000000000  # 2001
SESSION = 0
SOON = int(time.time()) + 30 * 24 * 3600

DASH = chr(0x2013)


def _line(domain, name, value="secret", expires=LONG_AFTER):
    includes_subdomains = "TRUE" if domain.startswith(".") else "FALSE"

    return f"{domain}\t{includes_subdomains}\t/\tFALSE\t{expires}\t{name}\t{value}\n"


def _date(expires):
    lapses = datetime.fromtimestamp(expires, tz=timezone.utc).astimezone()

    return lapses.strftime("%Y-%m-%d")


def _jar(*lines):
    return parse_cookies(NETSCAPE_HEADER + "".join(lines))


@pytest.fixture
def widget():
    widget = CookieStoreList()

    yield widget

    widget.deleteLater()


@pytest.fixture
def errors(widget):
    seen = []
    widget.error.connect(seen.append)

    return seen


def _table(widget):
    table = widget.table

    return [
        (
            table.item(row, DOMAIN_COLUMN).text(),
            table.item(row, COUNT_COLUMN).text(),
            table.item(row, EXPIRES_COLUMN).text(),
        )
        for row in range(table.rowCount())
    ]


def _domains(widget):
    return [row[0] for row in _table(widget)]


class TestWhatTheTableShows:
    def test_one_row_per_host_with_a_count(self, widget):
        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID"),
                _line(".youtube.com", "HSID"),
                _line(".bilibili.tv", "SESSDATA"),
            )
        )

        assert _table(widget) == [
            (".youtube.com", "2", "2100-01-01"),
            (".bilibili.tv", "1", "2100-01-01"),
        ]

    def test_it_never_shows_a_value(self, widget):
        """The page has to be as safe to read over a shoulder as any other."""

        widget.set_jar(_jar(_line(".youtube.com", "SID", value="s3cr3t")))

        assert "s3cr3t" not in str(_table(widget))

    @pytest.mark.parametrize(
        ("expires", "shown"),
        [
            (SESSION, "session"),
            (LONG_AGO, "expired"),
            (LONG_AFTER, "2100-01-01"),
        ],
    )
    def test_a_single_cookie_reads_plainly(self, widget, expires, shown):
        widget.set_jar(_jar(_line(".youtube.com", "SID", expires=expires)))

        assert _table(widget)[0][2] == shown

    def test_several_dates_are_shown_as_a_span(self, widget):
        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID", expires=LONG_AFTER),
                _line(".youtube.com", "HSID", expires=SOON),
            )
        )

        assert _table(widget)[0][2] == f"{_date(SOON)} {DASH} 2100-01-01"

    def test_cookies_that_lapsed_on_the_way_out_are_left_out_of_it(self, widget):
        """A fresh export carries a few that died minutes before it was taken.

        Going by those called a brand new login expired, which is what this
        column is supposed to warn about.
        """

        widget.set_jar(
            _jar(
                _line(".youtube.com", "dead", expires=LONG_AGO),
                _line(".youtube.com", "SID", expires=SOON),
                _line(".youtube.com", "HSID", expires=LONG_AFTER),
            )
        )

        assert _table(widget)[0][2] == f"{_date(SOON)} {DASH} 2100-01-01"

    def test_the_whole_host_being_past_it_still_says_so(self, widget):
        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID", expires=LONG_AGO),
                _line(".youtube.com", "HSID", expires=LONG_AGO - 1000),
            )
        )

        assert _table(widget)[0][2] == "expired"

    def test_a_session_cookie_keeps_a_host_from_reading_as_dead(self, widget):
        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID", expires=LONG_AGO),
                _line(".youtube.com", "tmp", expires=SESSION),
            )
        )

        assert _table(widget)[0][2] == "session"

    def test_cookies_lapsing_the_same_day_are_not_a_span(self, widget):
        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID", expires=LONG_AFTER),
                _line(".youtube.com", "HSID", expires=LONG_AFTER - 60),
            )
        )

        assert _table(widget)[0][2] == "2100-01-01"

    def test_the_count_still_takes_in_everything(self, widget):
        """How many are stored is a fact about the file, live or not."""

        widget.set_jar(
            _jar(
                _line(".youtube.com", "dead", expires=LONG_AGO),
                _line(".youtube.com", "SID", expires=LONG_AFTER),
            )
        )

        assert _table(widget)[0][1] == "2"

    def test_kin_are_listed_together(self, widget):
        """No public suffix list, but reversed labels get most of the way."""

        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID"),
                _line(".google.com", "NID"),
                _line("accounts.google.com", "ACCT"),
            )
        )

        assert _domains(widget) == [
            ".google.com",
            "accounts.google.com",
            ".youtube.com",
        ]

    def test_an_empty_jar_says_so(self, widget):
        widget.set_jar(None)

        assert _table(widget) == []
        assert widget.summary.text() == "No cookies stored"

    def test_one_of_something_is_not_called_several(self, widget):
        widget.set_jar(_jar(_line(".youtube.com", "SID")))

        assert widget.summary.text() == "Cookies: 1    Domains: 1"

    def test_a_full_one_is_counted_up(self, widget):
        widget.set_jar(
            _jar(_line(".youtube.com", "SID"), _line(".bilibili.tv", "SESSDATA"))
        )

        assert widget.summary.text() == "Cookies: 2    Domains: 2"


class TestImporting:
    def test_pasted_text_is_added(self, widget, errors):
        widget.import_text(NETSCAPE_HEADER + _line(".youtube.com", "SID"))

        assert _domains(widget) == [".youtube.com"]
        assert errors == []

    def test_it_adds_rather_than_replaces(self, widget):
        """Somebody builds a jar up one site at a time."""

        widget.set_jar(_jar(_line(".youtube.com", "SID")))

        widget.import_text(NETSCAPE_HEADER + _line(".bilibili.tv", "SESSDATA"))

        assert _domains(widget) == [".youtube.com", ".bilibili.tv"]

    def test_what_a_browser_extension_copies_is_taken_too(self, widget, errors):
        pasted = json.dumps(
            [
                {
                    "domain": ".youtube.com",
                    "name": "SID",
                    "value": "x",
                    "path": "/",
                    "expirationDate": float(LONG_AFTER),
                }
            ]
        )

        widget.import_text(pasted)

        assert _table(widget) == [(".youtube.com", "1", "2100-01-01")]
        assert errors == []

    def test_nonsense_is_reported_and_changes_nothing(self, widget, errors):
        widget.set_jar(_jar(_line(".youtube.com", "SID")))

        widget.import_text("have some cookies")

        assert _domains(widget) == [".youtube.com"]
        assert len(errors) == 1

    def test_an_empty_clipboard_is_reported(self, widget, errors):
        widget.import_text("   ")

        assert _domains(widget) == []
        assert len(errors) == 1

    def test_a_file_that_is_picked_is_read(self, widget, monkeypatch, tmp_path):
        path = tmp_path / "cookies.txt"
        path.write_text(NETSCAPE_HEADER + _line(".youtube.com", "SID"), "utf-8")

        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *a, **kw: (str(path), "")
        )

        widget.import_from_file()

        assert _domains(widget) == [".youtube.com"]

    def test_backing_out_of_the_file_picker_changes_nothing(self, widget, monkeypatch):
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: ("", ""))

        widget.import_from_file()

        assert widget.jar is None

    def test_the_clipboard_is_where_pasting_reads_from(self, widget):
        QApplication.clipboard().setText(
            NETSCAPE_HEADER + _line(".bilibili.tv", "SESSDATA")
        )

        widget.import_from_clipboard()

        assert _domains(widget) == [".bilibili.tv"]


class TestTakingCookiesOut:
    def test_removing_a_host_leaves_the_others(self, widget):
        widget.set_jar(
            _jar(
                _line(".youtube.com", "SID"),
                _line(".google.com", "NID"),
                _line(".bilibili.tv", "SESSDATA"),
            )
        )

        widget.table.selectRow(_domains(widget).index(".google.com"))
        widget.remove_selected()

        assert _domains(widget) == [".youtube.com", ".bilibili.tv"]

    def test_several_at_once(self, widget):
        """A login spread over three hosts comes out in one go."""

        widget.set_jar(
            _jar(
                _line(".google.com", "NID"),
                _line("accounts.google.com", "ACCT"),
                _line(".youtube.com", "SID"),
            )
        )

        widget.table.setRangeSelected(
            QTableWidgetSelectionRange(0, DOMAIN_COLUMN, 1, EXPIRES_COLUMN), True
        )
        widget.remove_selected()

        assert _domains(widget) == [".youtube.com"]

    def test_removing_the_last_one_empties_it(self, widget):
        widget.set_jar(_jar(_line(".youtube.com", "SID")))

        widget.table.selectRow(0)
        widget.remove_selected()

        assert widget.jar is None

    def test_clearing_takes_the_lot(self, widget):
        widget.set_jar(
            _jar(_line(".youtube.com", "SID"), _line(".bilibili.tv", "SESSDATA"))
        )

        widget.clear()

        assert widget.jar is None
        assert _table(widget) == []


class TestWhichButtonsAreLive:
    def test_remove_waits_for_something_to_be_picked(self, widget):
        widget.set_jar(_jar(_line(".youtube.com", "SID")))

        assert not widget.remove_button.isEnabled()

        widget.table.selectRow(0)

        assert widget.remove_button.isEnabled()

    def test_clear_all_waits_for_there_to_be_something(self, widget):
        assert not widget.clear_button.isEnabled()

        widget.set_jar(_jar(_line(".youtube.com", "SID")))

        assert widget.clear_button.isEnabled()

    def test_importing_is_always_offered(self, widget):
        assert widget.import_file_button.isEnabled()
        assert widget.paste_button.isEnabled()
