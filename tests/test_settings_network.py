"""The Network page, from the widgets to the ini and back.

The keys themselves are one thing and the page another: a setting nobody
wired to a widget is stored faithfully and never edited, and a widget
nobody wired to a setting is edited and never stored.
"""

import pytest
from PyQt5.QtCore import QEvent, QSettings, Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SECTION_PAGE_ROLE, SettingsDialog
from gridplayer.params.static import IPVersion, ProxyMode
from gridplayer.settings import _Settings
from gridplayer.utils.cookies import CookieStore

PROXY_URL = "socks5h://127.0.0.1:1080"

NETWORK_KEYS = (
    "network/proxy_mode",
    "network/proxy_url",
    "network/user_agent",
    "network/ip_version",
    "network/timeout",
    "network/verify_tls",
)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


@pytest.fixture
def _no_real_jar(tmp_path, monkeypatch):
    """Saving the page saves the cookies with it, so redirect those too."""

    monkeypatch.setattr(
        settings_dialog, "cookie_store", lambda: CookieStore(tmp_path / "cookies.txt")
    )


@pytest.fixture
def make_dialog(settings, _no_real_jar):
    """Build the dialog once a test has seeded the settings it wants.

    It reads them as it is constructed, so the seeding has to come first.
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


def _choose(combo, value):
    combo.setCurrentIndex(combo.findData(value))


class TestThePageIsWiredUp:
    @pytest.mark.parametrize("key", NETWORK_KEYS)
    def test_every_setting_has_a_widget(self, dialog, key):
        assert key in dialog.settings_map

    def test_the_section_opens_the_network_page(self, dialog):
        entry = dialog.section_index.findItems("Network", Qt.MatchExactly)[0]

        assert entry.data(SECTION_PAGE_ROLE) is dialog.page_streaming_network


class TestWhatIsStoredShowsUpOnThePage:
    def test_out_of_the_box_it_asks_for_nothing(self, dialog):
        assert dialog.networkProxyMode.currentData() is ProxyMode.SYSTEM
        assert dialog.networkUserAgent.text() == ""
        assert dialog.networkIPVersion.currentData() is IPVersion.AUTO
        assert dialog.networkTimeout.value() == 0
        assert dialog.networkVerifyTLS.isChecked()

    def test_a_proxy_that_was_stored(self, settings, make_dialog):
        settings.set("network/proxy_mode", ProxyMode.CUSTOM)
        settings.set("network/proxy_url", PROXY_URL)

        dialog = make_dialog()

        assert dialog.networkProxyMode.currentData() is ProxyMode.CUSTOM
        assert dialog.networkProxyUrl.text() == PROXY_URL


class TestWhatIsOnThePageIsStored:
    def test_a_proxy_typed_in(self, settings, dialog):
        _choose(dialog.networkProxyMode, ProxyMode.CUSTOM)
        dialog.networkProxyUrl.setText(PROXY_URL)

        dialog.save_settings()

        assert settings.get("network/proxy_mode") is ProxyMode.CUSTOM
        assert settings.get("network/proxy_url") == PROXY_URL

    def test_the_rest_of_the_page(self, settings, dialog):
        dialog.networkUserAgent.setText("Mozilla/5.0 (test)")
        _choose(dialog.networkIPVersion, IPVersion.V4)
        dialog.networkTimeout.setValue(30)
        dialog.networkVerifyTLS.setChecked(False)

        dialog.save_settings()

        assert settings.get("network/user_agent") == "Mozilla/5.0 (test)"
        assert settings.get("network/ip_version") is IPVersion.V4
        assert settings.get("network/timeout") == 30
        assert settings.get("network/verify_tls") is False


class TestTheAddressOnlyMattersForACustomProxy:
    def test_it_cannot_be_typed_into_out_of_the_box(self, dialog):
        assert not dialog.networkProxyUrl.isEnabled()

    def test_choosing_custom_opens_it_up(self, dialog):
        _choose(dialog.networkProxyMode, ProxyMode.CUSTOM)

        assert dialog.networkProxyUrl.isEnabled()

    def test_a_stored_custom_proxy_opens_it_up_on_the_way_in(
        self, settings, make_dialog
    ):
        settings.set("network/proxy_mode", ProxyMode.CUSTOM)

        assert make_dialog().networkProxyUrl.isEnabled()

    def test_an_address_is_kept_while_the_proxy_is_switched_off(
        self, settings, make_dialog
    ):
        """Switching back to Custom should not mean typing it again."""

        settings.set("network/proxy_mode", ProxyMode.CUSTOM)
        settings.set("network/proxy_url", PROXY_URL)

        dialog = make_dialog()
        _choose(dialog.networkProxyMode, ProxyMode.SYSTEM)

        dialog.save_settings()

        assert settings.get("network/proxy_mode") is ProxyMode.SYSTEM
        assert settings.get("network/proxy_url") == PROXY_URL


class TestTheUserAgentField:
    def test_it_is_left_empty_unless_somebody_says_otherwise(self, settings, dialog):
        """Empty is what leaves each tool on the one it came with."""

        dialog.save_settings()

        assert settings.get("network/user_agent") == ""


class TestTheKeysThemselves:
    """What survives a trip through settings.ini, page or no page."""

    def test_a_bare_ini_answers_with_the_defaults(self, settings):
        assert settings.get("network/proxy_mode") is ProxyMode.SYSTEM
        assert settings.get("network/proxy_url") == ""
        assert settings.get("network/user_agent") == ""
        assert settings.get("network/ip_version") is IPVersion.AUTO
        assert settings.get("network/timeout") == 0
        assert settings.get("network/verify_tls") is True

    def test_a_user_agent_with_something_awkward_in_it_survives(self, settings):
        """They are pasted in, so they are not all going to be tidy."""

        pasted = 'Mozilla/5.0 (X11; Linux) "quoted" \\ back; semi, comma'

        settings.set("network/user_agent", pasted)

        assert settings.get("network/user_agent") == pasted

    def test_an_ini_written_before_the_page_existed_still_reads(self, settings):
        """Nothing on the page is in it, which is not the same as wrong."""

        settings.settings.setValue("player/language", "en_US")
        settings.settings.sync()

        assert settings.get("network/proxy_mode") is ProxyMode.SYSTEM
        assert settings.get("network/timeout") == 0
