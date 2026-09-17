import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.utils.cookies import CookieStore, parse_cookies

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"

FOREVER = 4102444800


def _line(domain, name, value="secret"):
    includes_subdomains = "TRUE" if domain.startswith(".") else "FALSE"

    return f"{domain}\t{includes_subdomains}\t/\tFALSE\t{FOREVER}\t{name}\t{value}\n"


def _text(*lines):
    return NETSCAPE_HEADER + "".join(lines)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A jar of our own, so no test can reach the real one."""

    store = CookieStore(tmp_path / "cookies.txt")

    monkeypatch.setattr(settings_dialog, "cookie_store", lambda: store)

    return store


@pytest.fixture
def make_dialog(store):
    """Build the dialog once the store has been set up the way a test wants.

    It reads the jar as it is constructed, so seeding has to come first.
    """

    made = []

    def _make():
        dialog = SettingsDialog(None)
        made.append(dialog)

        return dialog

    yield _make

    for dialog in made:
        dialog.close()
        dialog.deleteLater()

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def dialog(make_dialog):
    return make_dialog()


def _domains(jar):
    return sorted({cookie.domain for cookie in jar or ()})


class TestTheSwitchesOnThePage:
    def test_both_of_them_are_wired_to_a_setting(self, dialog):
        assert dialog.settings_map["cookies/enabled"] is dialog.cookiesEnabled
        assert dialog.settings_map["cookies/allow_update"] is dialog.cookiesAllowUpdate

    def test_the_section_opens_the_cookies_page(self, dialog):
        entry = dialog.section_index.findItems("Cookies", Qt.MatchExactly)[0]

        dialog.section_index.setCurrentItem(entry)

        assert dialog.section_page.currentWidget() is dialog.page_streaming_cookies


class TestWhatThePageStartsWith:
    def test_it_shows_the_jar_that_is_stored(self, store, make_dialog):
        store.save(parse_cookies(_text(_line(".youtube.com", "SID"))))

        dialog = make_dialog()

        assert _domains(dialog.cookiesList.jar) == [".youtube.com"]

    def test_an_empty_store_leaves_the_page_empty(self, make_dialog):
        assert make_dialog().cookiesList.jar is None


class TestNothingIsWrittenUntilTheDialogIsAccepted:
    def test_an_import_alone_leaves_the_disk_alone(self, store, dialog):
        """Cancel has to undo an import the way it undoes anything else."""

        dialog.cookiesList.import_text(_text(_line(".youtube.com", "SID")))

        assert store.jar is None
        assert not store.path.exists()

    def test_accepting_writes_what_the_page_holds(self, store, dialog):
        dialog.cookiesList.import_text(_text(_line(".youtube.com", "SID")))

        dialog.save_cookies()

        assert _domains(store.jar) == [".youtube.com"]

    def test_a_removal_is_staged_the_same_way(self, store, dialog):
        store.save(parse_cookies(_text(_line(".youtube.com", "SID"))))
        dialog.cookiesList.set_jar(store.jar)

        dialog.cookiesList.clear()

        assert _domains(store.jar) == [".youtube.com"]

    def test_accepting_with_nothing_left_takes_the_file_away(self, store, dialog):
        store.save(parse_cookies(_text(_line(".youtube.com", "SID"))))
        dialog.cookiesList.set_jar(store.jar)

        dialog.cookiesList.clear()
        dialog.save_cookies()

        assert store.jar is None
        assert not store.path.exists()


class TestNotRewritingForNothing:
    def test_accepting_an_untouched_page_leaves_the_file_as_it_was(self, store, dialog):
        """A file full of logins is not rewritten just because OK was pressed."""

        store.save(parse_cookies(_text(_line(".youtube.com", "SID"))))
        dialog.cookiesList.set_jar(store.jar)
        before = store.path.read_bytes()
        stamp = store.path.stat().st_mtime_ns

        dialog.save_cookies()

        assert store.path.read_bytes() == before
        assert store.path.stat().st_mtime_ns == stamp

    def test_a_changed_value_still_gets_written(self, store, dialog):
        store.save(parse_cookies(_text(_line(".youtube.com", "SID", "old"))))
        dialog.cookiesList.set_jar(
            parse_cookies(_text(_line(".youtube.com", "SID", "new")))
        )

        dialog.save_cookies()

        assert [c.value for c in store.jar] == ["new"]

    def test_saving_nothing_over_nothing_creates_no_file(self, store, dialog):
        dialog.save_cookies()

        assert not store.path.exists()
