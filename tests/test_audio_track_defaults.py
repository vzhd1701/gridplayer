import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QComboBox, QLineEdit

from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioLanguage,
)
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.params.defaults_fields import VIDEO_FIELDS, FieldKind
from gridplayer.params.static import AudioTrackMode
from gridplayer.playlist_settings import (
    PlaylistSettings,
    overrides_from_playlist,
    playlist_kwargs_from_overrides,
)
from gridplayer.settings import Settings
from gridplayer.widgets.defaults_form import DefaultsForm

MODE_KEY = "video_defaults/audio_track_mode"
LANGUAGES_KEY = "video_defaults/audio_languages"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    # the store lives on the singleton, so leaving it pointed at a temporary
    # file follows every test that runs after this module
    settings.settings = real_settings


def _spec(settings_key):
    return next(f for f in VIDEO_FIELDS if f.settings_key == settings_key)


def _form():
    return DefaultsForm(VIDEO_FIELDS)


def test_both_fields_live_in_the_audio_section():
    assert _spec(MODE_KEY).section == "Audio"
    assert _spec(LANGUAGES_KEY).section == "Audio"


def test_languages_field_follows_the_mode_field():
    """The box only makes sense once the combo above it has been read."""

    audio = [f.settings_key for f in VIDEO_FIELDS if f.section == "Audio"]

    assert audio.index(LANGUAGES_KEY) == audio.index(MODE_KEY) + 1


def test_languages_field_is_a_text_box_with_an_example_in_it():
    spec = _spec(LANGUAGES_KEY)

    assert spec.kind is FieldKind.TEXT
    assert spec.text_placeholder


def test_text_field_renders_a_line_edit():
    form = _form()
    # the example only shows while the field is live; see _sync_enabled_by
    form.set_values({MODE_KEY: AudioTrackMode.PREFERRED})
    widget = form._widgets[LANGUAGES_KEY]

    assert isinstance(widget, QLineEdit)
    assert widget.placeholderText() == _spec(LANGUAGES_KEY).text_placeholder


def test_text_field_round_trips_its_value():
    form = _form()

    form.set_values({LANGUAGES_KEY: "en, ja"})

    assert form.values()[LANGUAGES_KEY] == "en, ja"


def test_text_field_shows_an_empty_default_as_empty():
    form = _form()

    form.set_values({LANGUAGES_KEY: ""})

    assert form.values()[LANGUAGES_KEY] == ""


@pytest.mark.parametrize(
    ("mode", "is_enabled"),
    [
        (AudioTrackMode.PREFERRED, True),
        (AudioTrackMode.DISABLED, False),
        (AudioTrackMode.DEFAULT, False),
    ],
)
def test_languages_field_follows_the_mode(mode, is_enabled):
    """Asking for no audio at all makes the preference moot."""

    form = _form()

    form.set_values({MODE_KEY: mode})

    assert form.is_enabled(LANGUAGES_KEY) is is_enabled


def test_video_takes_both_defaults_from_settings():
    Settings().set(MODE_KEY, AudioTrackMode.DISABLED)
    Settings().set(LANGUAGES_KEY, "ja, en")

    video = Video(uri="http://host/video")

    assert video.audio_selection == AudioDisabled()
    assert video.audio_languages == "ja, en"


def test_playlist_overrides_reach_the_video():
    PlaylistSettings().replace({LANGUAGES_KEY: "fr"})

    assert Video(uri="http://host/video").audio_languages == "fr"


def test_overrides_survive_a_playlist_round_trip():
    kwargs = playlist_kwargs_from_overrides(
        {MODE_KEY: AudioTrackMode.DISABLED, LANGUAGES_KEY: "en, ja"}
    )

    playlist = Playlist(videos=[], **kwargs)
    reloaded = Playlist._parse_json(playlist.dumps(), base_dir=None)

    assert overrides_from_playlist(reloaded) == {
        MODE_KEY: AudioTrackMode.DISABLED,
        LANGUAGES_KEY: "en, ja",
    }


def test_an_emptied_preference_is_an_override_of_its_own():
    """ "No preference" has to be storable, or it reads as "unset"."""

    kwargs = playlist_kwargs_from_overrides({LANGUAGES_KEY: ""})

    playlist = Playlist(videos=[], **kwargs)
    reloaded = Playlist._parse_json(playlist.dumps(), base_dir=None)

    assert overrides_from_playlist(reloaded) == {LANGUAGES_KEY: ""}


def test_an_explicit_pick_survives_a_playlist_round_trip():
    """Both keys travel, since only one of them applies to a given video."""

    from gridplayer.models.video import Video

    video = Video(uri="http://example.com/a.mp4")
    video.audio_selection = AudioLanguage(tag="jpn")

    reloaded = Playlist._parse_json(Playlist(videos=[video]).dumps(), base_dir=None)
    stored = reloaded.videos[0]

    assert stored.audio_selection == AudioLanguage(tag="jpn")


def test_the_preference_list_is_not_where_a_pick_is_stored():
    """Otherwise Preferred and the language picked would be one state."""

    from gridplayer.models.video import Video

    video = Video(uri="http://example.com/a.mp4")

    assert "audio_selection" in type(video).model_fields
    assert "audio_languages" in type(video).model_fields
    assert video.audio_selection == AudioDefault()


MUTED_KEY = "video_defaults/muted"


class TestTheAudioTrackDefaultIsAChoiceOfThree:
    """A tick box could only say two of the three things worth saying."""

    def test_the_field_offers_them_by_name(self):
        spec = _spec(MODE_KEY)

        assert spec.kind is FieldKind.COMBO
        assert spec.label == "Audio track"
        assert list(spec.combo_values()) == [
            AudioTrackMode.DEFAULT,
            AudioTrackMode.PREFERRED,
            AudioTrackMode.DISABLED,
        ]

    def test_it_renders_as_a_drop_down(self):
        form = _form()

        assert isinstance(form._widgets[MODE_KEY], QComboBox)

    @pytest.mark.parametrize(
        "mode",
        [AudioTrackMode.DEFAULT, AudioTrackMode.PREFERRED, AudioTrackMode.DISABLED],
    )
    def test_what_is_picked_is_what_comes_back(self, mode):
        """What is saved has to stay an AudioTrackMode.

        The same value is read as a per-video choice with states the list
        never offers, and a bool in the middle of that would not survive
        the round trip through a playlist.
        """

        form = _form()

        form.set_values({MODE_KEY: mode})

        assert form.values()[MODE_KEY] is mode

    def test_a_plain_check_box_still_answers_with_a_bool(self):
        """The mapping is opt-in; every other tick box is a bool as before."""

        form = _form()

        form.set_values({MUTED_KEY: True})

        assert form.values()[MUTED_KEY] is True

        form._widgets[MUTED_KEY].setChecked(False)

        assert form.values()[MUTED_KEY] is False


class TestTheHintWhileTheFieldIsGreyedOut:
    """Greyed out, an example reads as a value somebody put there."""

    def _languages(self, form):
        return form._widgets[LANGUAGES_KEY]

    def test_an_empty_field_really_looks_empty(self):
        form = _form()

        form.set_values({MODE_KEY: AudioTrackMode.DISABLED, LANGUAGES_KEY: ""})

        assert self._languages(form).isEnabled() is False
        assert self._languages(form).text() == ""
        assert self._languages(form).placeholderText() == ""

    def test_the_hint_comes_back_when_the_field_does(self):
        form = _form()

        form.set_values({MODE_KEY: AudioTrackMode.DISABLED, LANGUAGES_KEY: ""})
        form.set_values({MODE_KEY: AudioTrackMode.PREFERRED, LANGUAGES_KEY: ""})

        assert self._languages(form).placeholderText() == "en, ja, fr"

    def test_a_value_that_was_entered_still_shows(self):
        """Only the example is hidden; what someone typed is still theirs."""

        form = _form()

        form.set_values({MODE_KEY: AudioTrackMode.DISABLED, LANGUAGES_KEY: "ru, en"})

        assert self._languages(form).text() == "ru, en"
        assert self._languages(form).placeholderText() == ""

    def test_hiding_the_hint_does_not_touch_the_stored_value(self):
        form = _form()

        form.set_values({MODE_KEY: AudioTrackMode.DISABLED, LANGUAGES_KEY: "ru, en"})

        assert form.values()[LANGUAGES_KEY] == "ru, en"
