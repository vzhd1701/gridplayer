"""The JavaScript runtime row, and the button that opens where it goes.

Most packages cannot see a runtime installed anywhere a shell would put
it, so the two ways of pointing GridPlayer at one are a folder named on
this page and the folder the button opens. Both are useless if the
wiring is wrong, and wrong wiring is quiet: a widget nobody stored is
edited and forgotten.
"""

import pytest
from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.settings import _Settings
from gridplayer.utils.cookies import CookieStore

SETTING = "streaming/js_runtime_path"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


@pytest.fixture
def _no_real_jar(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings_dialog, "cookie_store", lambda: CookieStore(tmp_path / "cookies.txt")
    )


@pytest.fixture
def dialog(settings, _no_real_jar):
    made = SettingsDialog(None)

    yield made

    made.close()
    made.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def opened(monkeypatch):
    """What the button handed to the desktop to open."""

    urls = []

    monkeypatch.setattr(
        settings_dialog.QDesktopServices, "openUrl", lambda url: urls.append(url)
    )
    monkeypatch.setattr(settings_dialog.env, "IS_SNAP", False)

    return urls


def test_the_setting_has_a_widget(dialog):
    assert SETTING in dialog.settings_map


def test_a_named_folder_survives_being_saved(dialog, settings, tmp_path):
    dialog.streamingJSRuntimePath.setText(str(tmp_path))
    dialog.save_settings()

    assert settings.get(SETTING) == str(tmp_path)


def test_it_comes_back_empty_where_nobody_named_one(dialog):
    """Empty is what sends the search to the usual places."""

    assert dialog.streamingJSRuntimePath.text() == ""


def test_the_button_opens_the_data_folder(dialog, opened, monkeypatch, tmp_path):
    monkeypatch.setattr(settings_dialog, "get_app_data_dir", lambda: tmp_path)

    dialog.open_data_dir()

    assert [url.toLocalFile().rstrip("/") for url in opened] == [
        str(tmp_path).replace("\\", "/")
    ]


def test_it_opens_even_with_no_log_file_in_there(dialog, opened, monkeypatch, tmp_path):
    """It used to open the log, and refused when there was none.

    The folder is now somewhere a person is sent for reasons of their
    own -- it is where a JavaScript runtime goes -- so an empty one is
    not a failure.
    """

    monkeypatch.setattr(settings_dialog, "get_app_data_dir", lambda: tmp_path)

    assert not list(tmp_path.glob("*.log"))

    dialog.open_data_dir()

    assert len(opened) == 1


def test_a_snap_goes_around_qt_to_open_it(dialog, monkeypatch, tmp_path):
    """QDesktopServices does not work inside a snap, xdg-open does."""

    called = []

    monkeypatch.setattr(settings_dialog, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(settings_dialog.env, "IS_SNAP", True)
    monkeypatch.setattr(
        settings_dialog.subprocess, "call", lambda cmd: called.append(cmd)
    )

    dialog.open_data_dir()

    assert called == [["xdg-open", tmp_path]]


class TestTheYouTubeTestButton:
    """It belongs with link resolution, not with the cookies.

    Two of its six steps are about cookies; the other four are about
    whether a link resolves at all. It also reports a missing
    JavaScript runtime, and the field for that is on this page.
    """

    def test_it_is_on_the_link_resolution_page(self, dialog):
        assert dialog.streamingTestButton.parent() is dialog.page_streaming_resolution

    def test_it_is_not_on_the_cookies_page_any_more(self, dialog):
        assert not hasattr(dialog, "cookiesTestButton")

    def test_it_says_what_it_tries(self, dialog):
        """ "Test yt-dlp" named the tool; this names the thing being tried."""

        assert dialog.streamingTestButton.text() == "Test a YouTube link"

    def test_it_still_tries_the_cookies_as_the_page_has_them(self, dialog, mocker):
        """Moving pages must not quietly switch it to the stored jar.

        Somebody pastes cookies and tests them before pressing OK.
        """

        made = mocker.patch.object(settings_dialog, "YouTubeCheckup")
        mocker.patch.object(settings_dialog, "CheckupDialog")

        dialog.run_youtube_checkup()

        assert made.call_args.kwargs["jar"] is dialog.cookiesList.jar


def test_the_test_button_sits_with_the_runtime_it_tests(dialog):
    """One group: the engine setting and the thing that tries it.

    They were a page apart before, which is how the button came to be
    filed under cookies in the first place.
    """

    field_row = dialog.streamingJSRuntimePath.parentWidget().layout()

    assert dialog.lay_ytdlp_test.indexOf(dialog.streamingTestButton) >= 0
    assert dialog.formLayout_ytdlp.indexOf(dialog.streamingJSRuntimePath) >= 0
    assert field_row is not None


class TestTheTestTriesWhatIsOnScreen:
    """Nobody has pressed OK yet, which is the point of pressing Test.

    The cookies were handed over from the start. The runtime folder and
    the network settings were not, so a folder typed and then tested
    was tested against whatever had last been saved, which is the one
    answer that cannot help.
    """

    @pytest.fixture
    def tried(self, dialog, mocker):
        made = mocker.patch.object(settings_dialog, "YouTubeCheckup")
        mocker.patch.object(settings_dialog, "CheckupDialog")

        def _run():
            dialog.run_youtube_checkup()
            return made.call_args.kwargs

        return _run

    def test_a_folder_typed_but_not_saved_is_the_one_tried(self, dialog, tried):
        dialog.streamingJSRuntimePath.setText("/typed/just/now")

        assert tried()["js_runtime_path"] == "/typed/just/now"

    def test_clearing_the_field_is_tried_as_cleared(self, dialog, settings, tried):
        """Empty must not read as "nothing said, go and load the old one"."""

        settings.set("streaming/js_runtime_path", "/saved/earlier")
        dialog.streamingJSRuntimePath.setText("")

        assert tried()["js_runtime_path"] == ""

    def test_the_network_page_is_tried_as_it_stands_too(self, dialog, tried):
        dialog.networkUserAgent.setText("something-just-typed")

        assert tried()["net_opts"].user_agent == "something-just-typed"

    def test_the_cookies_still_come_from_their_page(self, dialog, tried):
        assert tried()["jar"] is dialog.cookiesList.jar
