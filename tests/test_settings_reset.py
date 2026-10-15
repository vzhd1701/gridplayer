"""Putting settings back to how they come out of the box: a field at a
time with the button beside it, or a page at a time with Reset Page.

A setting at its default is not kept in the ini, so that it follows the
default if a later version changes it.
"""

import pytest
from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.dialogs import settings as settings_dialog
from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.models.keymap_overrides import KeymapOverrides
from gridplayer.params.settings_fields import general as general_fields
from gridplayer.params.settings_pages import PAGES
from gridplayer.params.static import ProxyMode, VideoAspect
from gridplayer.settings import _Settings, default_value
from gridplayer.utils.taskbar import TaskbarHidingBlocker
from gridplayer.widgets.settings_form import SettingsForm


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(settings_dialog, "Settings", lambda: store)

    return store


@pytest.fixture
def make_dialog(settings, _no_real_cache, monkeypatch):
    monkeypatch.setattr(
        settings_dialog.QSystemTrayIcon,
        "isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(general_fields, "taskbar_hiding_blocker", lambda: None)

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


def _reset_button(dialog, key):
    return dialog.form_of(key)._reset_btns[key]


def _is_marked(dialog, key):
    form = dialog.form_of(key)
    return (
        form.is_modified(key)
        and form.editor(key).marked.font().italic()
        and not _reset_button(dialog, key).isHidden()
    )


def _choose(combo, value):
    combo.setCurrentIndex(combo.findData(value))


class TestWhatIsMarked:
    def test_out_of_the_box_nothing_is(self, dialog):
        for form in dialog.forms.values():
            assert not form.has_modified()

        assert not dialog.resetPage.isEnabled()

    def test_a_field_changed_from_its_default(self, dialog):
        dialog.widget("player/one_instance").setChecked(False)

        assert _is_marked(dialog, "player/one_instance")
        assert dialog.resetPage.isEnabled()

    def test_a_field_changed_back_is_not_any_more(self, dialog):
        dialog.widget("player/one_instance").setChecked(False)
        dialog.widget("player/one_instance").setChecked(True)

        assert not _is_marked(dialog, "player/one_instance")
        assert not dialog.resetPage.isEnabled()

    def test_a_blank_that_saves_as_the_default_is_not(self, dialog):
        dialog.widget("screenshots/filename_template").setText("  ")

        assert not _is_marked(dialog, "screenshots/filename_template")

    def test_a_saved_one_is_marked_as_it_opens(self, settings, make_dialog):
        settings.set("network/force_ipv4", True)

        dialog = make_dialog()

        assert _is_marked(dialog, "network/force_ipv4")

    def test_reset_page_goes_by_the_page_on_show(self, settings, make_dialog):
        settings.set("network/force_ipv4", True)

        dialog = make_dialog()

        dialog.show_page("player")
        assert not dialog.resetPage.isEnabled()

        dialog.show_page("network")
        assert dialog.resetPage.isEnabled()


class TestResettingAField:
    def test_it_goes_back_to_the_factory_default(self, settings, make_dialog):
        settings.set("video_defaults/aspect", VideoAspect.STRETCH)
        dialog = make_dialog()

        _reset_button(dialog, "video_defaults/aspect").click()

        assert dialog.value("video_defaults/aspect") is VideoAspect.FIT
        assert not _is_marked(dialog, "video_defaults/aspect")

    def test_it_is_forgotten_on_save(self, settings, make_dialog):
        settings.set("video_defaults/aspect", VideoAspect.STRETCH)
        dialog = make_dialog()

        _reset_button(dialog, "video_defaults/aspect").click()
        dialog.save_settings()

        assert not settings.settings.contains("video_defaults/aspect")
        assert settings.get("video_defaults/aspect") is VideoAspect.FIT

    def test_cancel_keeps_what_was_saved(self, settings, make_dialog):
        settings.set("video_defaults/aspect", VideoAspect.STRETCH)
        dialog = make_dialog()

        _reset_button(dialog, "video_defaults/aspect").click()
        dialog.reject()

        assert settings.get("video_defaults/aspect") is VideoAspect.STRETCH


class TestResettingAPage:
    def test_only_the_page_on_show(self, settings, make_dialog):
        settings.set("network/force_ipv4", True)
        settings.set("player/one_instance", False)
        dialog = make_dialog()

        dialog.show_page("network")
        dialog.resetPage.click()

        assert dialog.value("network/force_ipv4") is False
        assert dialog.value("player/one_instance") is False
        assert not dialog.resetPage.isEnabled()

    def test_a_greyed_out_field_reset_is_saved_too(self, settings, make_dialog):
        """The address is kept while the proxy is off, and not saved over;
        reset, it goes, or Reset Page would quietly leave it."""

        settings.set("network/proxy_mode", ProxyMode.SYSTEM)
        settings.set("network/proxy_url", "http://proxy:8080")
        dialog = make_dialog()

        dialog.show_page("network")
        dialog.resetPage.click()
        dialog.save_settings()

        assert not settings.settings.contains("network/proxy_url")

    def test_shortcuts(self, settings, make_dialog):
        settings.set("player/keymap", KeymapOverrides({"Play / Pause": ["F5"]}))
        dialog = make_dialog()

        dialog.show_page("shortcuts")
        assert dialog.resetPage.isEnabled()

        dialog.resetPage.click()
        dialog.save_settings()

        assert settings.get("player/keymap") == KeymapOverrides({})

    def test_cookies_stay(self, dialog):
        dialog.cookiesList.import_text(
            "# Netscape HTTP Cookie File\n"
            ".example.com\tTRUE\t/\tTRUE\t2147483647\tsid\tabc\n"
        )
        dialog.widget("cookies/enabled").setChecked(False)

        dialog.show_page("cookies")
        dialog.resetPage.click()

        assert dialog.value("cookies/enabled") is True
        assert dialog.cookiesList.jar is not None

    def test_minimize_ticked_for_the_taskbar_goes_back_too(self, settings, make_dialog):
        settings.set("player/tray_icon", True)
        settings.set("player/hide_taskbar", True)
        dialog = make_dialog()

        # ticked for hiding from the taskbar, not by the user
        assert dialog.value("player/minimize_to_tray") is True

        dialog.show_page("player")
        dialog.resetPage.click()

        assert dialog.value("player/tray_icon") is False
        assert dialog.value("player/hide_taskbar") is False
        assert dialog.value("player/minimize_to_tray") is False
        assert not dialog.resetPage.isEnabled()

    def test_minimize_ticked_for_the_taskbar_is_forgotten_too(
        self, settings, make_dialog
    ):
        for key in ("player/tray_icon", "player/hide_taskbar"):
            settings.set(key, True)
        settings.set("player/minimize_to_tray", True)
        dialog = make_dialog()

        dialog.show_page("player")
        dialog.resetPage.click()
        dialog.save_settings()

        for key in (
            "player/tray_icon",
            "player/hide_taskbar",
            "player/minimize_to_tray",
        ):
            assert not settings.settings.contains(key), key


class TestWhatCannotBeChangedHere:
    def test_it_has_no_reset_and_keeps_what_was_saved(
        self, settings, make_dialog, monkeypatch
    ):
        settings.set("player/tray_icon", True)
        settings.set("player/hide_taskbar", True)
        monkeypatch.setattr(
            general_fields,
            "taskbar_hiding_blocker",
            lambda: TaskbarHidingBlocker.WAYLAND,
        )
        dialog = make_dialog()

        assert _reset_button(dialog, "player/hide_taskbar").isHidden()

        dialog.show_page("player")
        dialog.resetPage.click()
        dialog.save_settings()

        assert settings.get("player/hide_taskbar") is True


class TestSaving:
    def test_a_default_is_not_kept(self, settings, dialog):
        dialog.save_settings()

        assert settings.settings.allKeys() == []

    def test_a_setting_changed_back_to_its_default_is_forgotten(
        self, settings, make_dialog
    ):
        settings.set("network/force_ipv4", True)
        dialog = make_dialog()

        dialog.widget("network/force_ipv4").setChecked(False)
        dialog.save_settings()

        assert not settings.settings.contains("network/force_ipv4")

    def test_what_differs_is_kept(self, settings, dialog):
        _choose(dialog.widget("video_defaults/aspect"), VideoAspect.NONE)
        dialog.save_settings()

        assert settings.settings.allKeys() == ["video_defaults/aspect"]


def test_settings_reset_forgets_the_setting(settings):
    settings.set("network/force_ipv4", True)

    settings.reset("network/force_ipv4")

    assert not settings.settings.contains("network/force_ipv4")
    assert settings.get("network/force_ipv4") is default_value("network/force_ipv4")


class TestThePlaylistSettings:
    """There a reset goes back to the global settings, not out of the box."""

    def test_a_field_goes_back_to_the_global_setting(self, settings, monkeypatch):
        from gridplayer.dialogs import playlist_settings
        from gridplayer.models.grid_state import GridState

        settings.set("video_defaults/aspect", VideoAspect.STRETCH)
        monkeypatch.setattr(playlist_settings, "Settings", lambda: settings)

        dialog = playlist_settings.PlaylistSettingsDialog(
            {"video_defaults/aspect": VideoAspect.NONE}, GridState()
        )
        form = dialog._video_form

        form._reset_btns["video_defaults/aspect"].click()

        assert form.value("video_defaults/aspect") is VideoAspect.STRETCH
        assert "video_defaults/aspect" not in dialog.result_overrides()


class TestALanguageNoLongerShipped:
    def test_shows_the_default_and_is_forgotten_on_save(self, settings, make_dialog):
        settings.settings.setValue("player/language", "xx_YY")
        dialog = make_dialog()

        assert dialog.value("player/language") == default_value("player/language")

        dialog.save_settings()

        assert not settings.settings.contains("player/language")


class TestWhatAnEditReads:
    def test_only_the_field_edited(self, dialog, monkeypatch):
        patterns = dialog.widget("streaming/resolver_priority_patterns")
        reads = []
        rows_data = patterns.rows_data
        monkeypatch.setattr(
            patterns, "rows_data", lambda: reads.append(1) or rows_data()
        )

        dialog.widget("streaming/js_runtime_path").setText("/opt/deno")

        assert dialog.forms["resolution"].is_modified("streaming/js_runtime_path")
        assert reads == []

    def test_a_page_built_reads_nothing_before_its_values(self, monkeypatch):
        page = next(p for g in PAGES for p in g.pages if p.id == "resolution")
        reads = []
        monkeypatch.setattr(
            SettingsForm, "_is_modified", lambda _self, key: reads.append(key)
        )

        SettingsForm(
            page.items,
            reset_to=default_value,
            track_edits=False,
            slots=dict.fromkeys(("youtube_test", "wildcard_help"), QWidget),
        )

        assert reads == []
