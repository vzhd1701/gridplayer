"""The SponsorBlock page, from the widgets to the ini and back."""

import pytest
from PyQt5.QtCore import QEvent, QSettings, Qt
from PyQt5.QtWidgets import QApplication, QComboBox

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SECTION_PAGE_ROLE, SettingsDialog
from gridplayer.params.sponsorblock import (
    CATEGORY_COLORS,
    HIGHLIGHT_CATEGORY,
    SPONSORBLOCK_SETTINGS,
    category_setting,
)
from gridplayer.params.static import SponsorBlockMode
from gridplayer.settings import _Settings
from gridplayer.utils.cookies import CookieStore


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


@pytest.fixture
def make_dialog(settings, tmp_path, monkeypatch):
    """Build the dialog once a test has seeded the settings it wants."""

    # saving the page saves the cookies with it
    monkeypatch.setattr(
        settings_dialog, "cookie_store", lambda: CookieStore(tmp_path / "cookies.txt")
    )

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


def _combo(dialog, category) -> QComboBox:
    return dialog.settings_map[category_setting(category)]


def _choose(combo, value):
    combo.setCurrentIndex(combo.findData(value))


def _modes(combo):
    return [combo.itemData(index) for index in range(combo.count())]


class TestThePageIsWiredUp:
    @pytest.mark.parametrize("key", SPONSORBLOCK_SETTINGS)
    def test_every_setting_has_a_widget(self, dialog, key):
        assert key in dialog.settings_map

    def test_the_section_opens_the_page(self, dialog):
        entry = dialog.section_index.findItems("SponsorBlock", Qt.MatchExactly)[0]

        assert entry.data(SECTION_PAGE_ROLE) is dialog.page_streaming_sponsorblock

    def test_a_highlight_cannot_be_set_to_be_skipped(self, dialog):
        assert _modes(_combo(dialog, HIGHLIGHT_CATEGORY)) == [
            SponsorBlockMode.SHOW,
            SponsorBlockMode.OFF,
        ]

    def test_the_rest_can_be_set_to_anything(self, dialog):
        assert _modes(_combo(dialog, "sponsor")) == list(SponsorBlockMode)


class TestSwitchedOff:
    def test_out_of_the_box_it_is(self, dialog):
        assert not dialog.sponsorblockEnabled.isChecked()
        assert not dialog.sponsorblockCategories.isEnabled()

    def test_switching_it_on_opens_up_the_categories(self, dialog):
        dialog.sponsorblockEnabled.setChecked(True)

        assert dialog.sponsorblockCategories.isEnabled()

    def test_a_stored_on_opens_them_up_on_the_way_in(self, settings, make_dialog):
        settings.set("sponsorblock/enabled", True)

        assert make_dialog().sponsorblockCategories.isEnabled()


class TestWhatIsStoredShowsUpOnThePage:
    def test_out_of_the_box_only_sponsors_are_skipped(self, dialog):
        skipped = [
            category
            for category in CATEGORY_COLORS
            if _combo(dialog, category).currentData() is SponsorBlockMode.SKIP
        ]

        assert skipped == ["sponsor"]

    def test_a_category_that_was_stored(self, settings, make_dialog):
        settings.set("sponsorblock/intro", SponsorBlockMode.SKIP)

        dialog = make_dialog()

        assert _combo(dialog, "intro").currentData() is SponsorBlockMode.SKIP


class TestWhatIsOnThePageIsStored:
    def test_it_switched_on_with_a_category_changed(self, settings, dialog):
        dialog.sponsorblockEnabled.setChecked(True)
        _choose(_combo(dialog, "outro"), SponsorBlockMode.SKIP)

        dialog.save_settings()

        assert settings.get("sponsorblock/enabled") is True
        assert settings.get("sponsorblock/outro") is SponsorBlockMode.SKIP

    def test_switched_off_what_was_chosen_before_is_kept(self, settings, make_dialog):
        """Switching it back on should not mean choosing them all again."""

        settings.set("sponsorblock/enabled", True)
        settings.set("sponsorblock/outro", SponsorBlockMode.SKIP)

        dialog = make_dialog()
        dialog.sponsorblockEnabled.setChecked(False)

        dialog.save_settings()

        assert settings.get("sponsorblock/enabled") is False
        assert settings.get("sponsorblock/outro") is SponsorBlockMode.SKIP
