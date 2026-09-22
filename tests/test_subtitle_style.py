"""What subtitles look like: one style, settled when a VLC process starts.

The text renderer hangs off the media player rather than the input, so
none of this can be asked for per video without a VLC process per style.
It is one page of settings for every video instead, and changing it opens
the videos again.
"""

import logging
from functools import partial
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtWidgets import QApplication, QLabel

from gridplayer.dialogs.settings import SettingsDialog
from gridplayer.params.defaults_fields import SUBTITLE_STYLE_FIELDS
from gridplayer.params.static import SubtitleOutline
from gridplayer.params.subtitle_style import (
    SUBTITLE_STYLE_DEFAULTS,
    SUBTITLE_STYLE_SETTINGS,
    subtitle_style_options,
)
from gridplayer.player.managers.settings import SettingsManager
from gridplayer.settings import Settings
from gridplayer.vlc_player.instance import InstanceVLC


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _init_options(vlc_options=()):
    instance = InstanceVLC(0, list(vlc_options))
    instance._logger = logging.getLogger("test")

    return instance.init_options


def _styled(**style):
    return subtitle_style_options({f"subtitles/{k}": v for k, v in style.items()})


def _is_style_option(option):
    return option.startswith(("--freetype-", "--sub-text-scale", "--sub-margin"))


class TestAnUntouchedInstallAsksForNothing:
    """Every default here is VLC's own, so there is nothing to pass on.

    Taken by rendering a subtitled frame and comparing it against one
    rendered with the option given by hand: an outline of 4 and a shadow
    opacity of 128 reproduce an untouched VLC exactly. Passing them
    anyway would fork the process pool for no visible difference.
    """

    def test_no_options_come_out_of_the_defaults(self):
        assert subtitle_style_options({}) == []

    def test_no_style_option_reaches_the_instance(self):
        assert [opt for opt in _init_options() if _is_style_option(opt)] == []

    @pytest.mark.parametrize("setting", SUBTITLE_STYLE_SETTINGS)
    def test_the_stored_default_survives_being_read_back(self, setting):
        """An enum that does not round-trip reads as the default forever."""

        Settings().set(setting, SUBTITLE_STYLE_DEFAULTS[setting])

        assert Settings().get(setting) == SUBTITLE_STYLE_DEFAULTS[setting]


class TestEachKnobNamesWhatVLCTakes:
    @pytest.mark.parametrize(
        ("style", "option"),
        [
            ({"font": "Comic Sans MS"}, "--freetype-font=Comic Sans MS"),
            ({"size_scale": 200}, "--sub-text-scale=200"),
            ({"color": "#ff8800"}, "--freetype-color=0xff8800"),
            ({"bold": True}, "--freetype-bold"),
            ({"outline": SubtitleOutline.NONE}, "--freetype-outline-thickness=0"),
            ({"outline": SubtitleOutline.THIN}, "--freetype-outline-thickness=2"),
            ({"outline": SubtitleOutline.THICK}, "--freetype-outline-thickness=6"),
            ({"outline_color": "#00ff00"}, "--freetype-outline-color=0x00ff00"),
            ({"shadow": False}, "--freetype-shadow-opacity=0"),
            ({"shadow_color": "#0000ff"}, "--freetype-shadow-color=0x0000ff"),
            ({"background": True}, "--freetype-background-opacity=255"),
            ({"margin": 120}, "--sub-margin=120"),
        ],
    )
    def test_the_option_it_asks_for(self, style, option):
        assert option in _styled(**style)

    def test_a_background_of_its_own_colour_asks_for_both(self):
        options = _styled(background=True, background_color="#202020")

        assert options == [
            "--freetype-background-opacity=255",
            "--freetype-background-color=0x202020",
        ]


class TestWhatIsNotWorthAskingFor:
    """A colour nobody can see is a fork of the process pool for nothing."""

    def test_no_outline_means_no_outline_colour(self):
        options = _styled(outline=SubtitleOutline.NONE, outline_color="#00ff00")

        assert "--freetype-outline-color=0x00ff00" not in options

    def test_no_shadow_means_no_shadow_colour(self):
        options = _styled(shadow=False, shadow_color="#0000ff")

        assert "--freetype-shadow-color=0x0000ff" not in options

    def test_no_background_means_no_background_colour(self):
        assert _styled(background_color="#202020") == []

    def test_something_that_is_not_a_colour_is_dropped_rather_than_read(self):
        """VLC reads anything it cannot parse as black, which looks chosen."""

        assert _styled(color="not a colour") == []


class TestItReachesTheProcessThatDrawsIt:
    def test_the_style_is_passed_to_the_instance(self):
        Settings().set("subtitles/size_scale", 150)
        Settings().set("subtitles/background", True)

        options = _init_options()

        assert "--sub-text-scale=150" in options
        assert "--freetype-background-opacity=255" in options

    def test_what_was_typed_by_hand_still_wins(self):
        """Last on the command line is what VLC goes by."""

        Settings().set("subtitles/color", "#ff0000")
        Settings().set("misc/vlc_options", "--freetype-color=0x00ff00")

        options = _init_options()

        assert options.index("--freetype-color=0xff0000") < options.index(
            "--freetype-color=0x00ff00"
        )


class TestChangingItOpensTheVideosAgain:
    """It is settled when the input opens, so nothing else would show it."""

    @pytest.mark.parametrize("setting", SUBTITLE_STYLE_SETTINGS)
    def test_every_knob_asks_for_a_reload(self, setting):
        previous = Settings().get_all()
        Settings().set(setting, _other_than(Settings().get(setting)))

        manager = Mock(spec=SettingsManager)
        manager._setting_changes = partial(SettingsManager._setting_changes, manager)

        assert SettingsManager._is_reload_needed(manager, previous)


def _other_than(value):
    """Any value of the same type that is not the one given."""

    if isinstance(value, SubtitleOutline):
        return (
            SubtitleOutline.THICK
            if value is SubtitleOutline.THIN
            else (SubtitleOutline.THIN)
        )

    if isinstance(value, bool):
        return not value

    if isinstance(value, int):
        return value + 1

    return f"{value}x"


class TestThePageIsWiredToTheSettings:
    @pytest.mark.parametrize("field", SUBTITLE_STYLE_FIELDS, ids=lambda f: f.label)
    def test_every_row_has_a_setting_behind_it(self, field):
        assert field.settings_key in SUBTITLE_STYLE_DEFAULTS

    def test_every_setting_has_a_row(self):
        on_page = {field.settings_key for field in SUBTITLE_STYLE_FIELDS}

        assert on_page == set(SUBTITLE_STYLE_SETTINGS)

    def test_nothing_here_belongs_to_a_video(self):
        """A style is one per process; a per-video one would fork the pool."""

        for field in SUBTITLE_STYLE_FIELDS:
            assert field.video_attr is None
            assert field.playlist_attr is None


@pytest.fixture
def dialog():
    dialog = SettingsDialog(None)

    yield dialog

    # nothing owns a dialog made here, so it has to be taken down on the
    # spot rather than left for the garbage collector to drop mid-test
    dialog.close()
    dialog.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class TestThePageItIsSetOn:
    def test_what_is_picked_on_the_page_is_what_is_saved(self, dialog):
        dialog.subtitle_style_form.set_values(
            {
                "subtitles/size_scale": 140,
                "subtitles/background": True,
                "subtitles/outline": SubtitleOutline.THICK,
            }
        )

        dialog.save_settings()

        assert Settings().get("subtitles/size_scale") == 140
        assert Settings().get("subtitles/background") is True
        assert Settings().get("subtitles/outline") is SubtitleOutline.THICK

    def test_a_colour_nobody_would_see_is_greyed_out(self, dialog):
        form = dialog.subtitle_style_form

        form.set_values(
            {
                "subtitles/outline": SubtitleOutline.NONE,
                "subtitles/shadow": False,
                "subtitles/background": False,
            }
        )

        assert not form.is_enabled("subtitles/outline_color")
        assert not form.is_enabled("subtitles/shadow_color")
        assert not form.is_enabled("subtitles/background_color")

    def test_a_colour_that_would_be_drawn_can_be_picked(self, dialog):
        form = dialog.subtitle_style_form

        form.set_values(
            {
                "subtitles/outline": SubtitleOutline.THIN,
                "subtitles/shadow": True,
                "subtitles/background": True,
            }
        )

        assert form.is_enabled("subtitles/outline_color")
        assert form.is_enabled("subtitles/shadow_color")
        assert form.is_enabled("subtitles/background_color")

    def test_the_page_says_that_ass_subtitles_style_themselves(self, dialog):
        """Otherwise styling an anime release looks like a bug in this."""

        page = dialog.page_subtitle_style.widget()
        notes = [
            label.text() for label in page.findChildren(QLabel) if "ASS" in label.text()
        ]

        assert notes
