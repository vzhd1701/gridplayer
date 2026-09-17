"""The Audio Track submenu: one list, whichever way the video is dubbed."""

from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.params.menu import SECTIONS
from gridplayer.params.static import AudioTrackMode
from gridplayer.player.manager import Commands
from gridplayer.player.managers.actions import ActionsManager
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.vlc_player.static import DISABLED_TRACK, AudioTrack


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _track(language, description=None):
    return AudioTrack(
        codec="mp4a",
        bitrate=131072,
        language=language,
        description=description,
        channels=2,
        rate=48000,
    )


# what separates a track's language from the container's name for it
DASH = "\u2014"

CODEC = "mp4a, 2 ch, 48 kHz, 128 kbps"

# one film, three rival Russian dubs and the original; nothing but the
# name each was given tells the first three apart
DUBBED_FILE_TRACKS = {
    0: _track("rus", "MVO (Rakurs) [VHS Hi-Fi]"),
    1: _track("rus", "MVO (ORT) [VHS]"),
    2: _track("rus", "VO (Buratino) [VHS]"),
    3: _track("eng", "Original"),
}


FILE_TRACKS = {0: _track("eng"), 1: _track("jpn"), 2: _track("fre")}

# a dubbed stream is handed to VLC one language at a time, so it only ever
# has the single track to show for itself
STREAM_TRACKS = {0: _track("tlh")}


class _Manager(ActiveBlockManager):
    """The manager's menu methods, without the rest of the player behind them."""

    def __init__(self, block):
        self._ctx = SimpleNamespace(active_block=block)

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None


def _manager(
    tracks=None,
    languages=(),
    mode=AudioTrackMode.PREFERRED,
    preferred=0,
    playing_language=None,
    preferred_language=None,
    track_id=0,
):
    block = SimpleNamespace(
        audio_tracks=FILE_TRACKS if tracks is None else tracks,
        audio_language_options=languages,
        audio_language=playing_language,
        preferred_audio_track_id=preferred,
        preferred_audio_language=preferred_language,
        video_params=SimpleNamespace(
            audio_track_mode=mode,
            audio_track_id=track_id,
        ),
    )

    return _Manager(block)


def _titles(menu):
    return [item if item == "---" else item["title"] for item in menu]


def test_there_is_only_one_audio_submenu_left():
    audio = next(
        item
        for item in SECTIONS["video_active"]
        if isinstance(item, tuple) and item[0] == "Audio"
    )

    assert "Audio Language" not in audio
    assert audio[1] == "Audio Track"


def test_a_file_offers_its_tracks():
    menu = _manager().menu_generator_audio_track()

    assert _titles(menu) == [
        "Preferred (English)",
        "Languages: %v",
        "Disable Audio",
        "---",
        "English, mp4a, 2 ch, 48 kHz, 128 kbps",
        "Japanese, mp4a, 2 ch, 48 kHz, 128 kbps",
        "French, mp4a, 2 ch, 48 kHz, 128 kbps",
    ]


def test_every_row_calls_something_that_exists_on_a_block():
    """A menu entry pointing at nothing fails silently at the click."""

    from gridplayer.widgets.video_block import VideoBlock

    menu = _manager(
        tracks=STREAM_TRACKS, languages=("cop", "tlh"), playing_language="tlh"
    ).menu_generator_audio_track()

    called = [item["func"][1] for item in menu if item != "---"]

    assert called
    for name in called:
        assert hasattr(VideoBlock, name), name


def test_a_dubbed_stream_offers_its_languages_in_the_same_place():
    """The single track VLC can see is not the choice being made."""

    menu = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh", "en"),
        playing_language="tlh",
    ).menu_generator_audio_track()

    assert _titles(menu)[4:] == ["Coptic", "Klingon", "English"]


def test_a_video_with_nothing_to_choose_still_shows_its_one_track():
    menu = _manager(tracks={0: _track("eng")}).menu_generator_audio_track()

    assert _titles(menu)[4:] == ["English, mp4a, 2 ch, 48 kHz, 128 kbps"]


def test_an_untagged_track_keeps_the_details_it_does_have():
    menu = _manager(tracks={0: _track(None)}).menu_generator_audio_track()

    assert _titles(menu)[4:] == ["mp4a, 2 ch, 48 kHz, 128 kbps"]


def test_the_preference_row_sits_under_the_entry_that_follows_it():
    row = _manager().menu_generator_audio_track()[1]

    assert row["func"] == ("active", "audio_languages_dialog")
    assert row["value_getter"] == ("active", "get_audio_languages")


def test_preferred_goes_through_the_path_that_knows_about_dubbing():
    """The track-only path is a no-op for a stream served one language at a time."""

    item = _manager()._preferred_audio_track_menu_item()

    assert item["func"] == ("active", "apply_audio_preference")


def test_preferred_names_the_track_it_resolves_to():
    manager = _manager(preferred=1)

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred (Japanese)"


def test_preferred_names_the_track_playing_when_it_matched_nothing():
    """No preference is set, so the file opened with its own choice."""

    manager = _manager(preferred=None, track_id=1)

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred (Japanese)"


def test_preferred_says_nothing_once_a_track_is_picked_by_hand():
    """What reverting would give is the file's own choice, which is unknown."""

    manager = _manager(preferred=None, track_id=1, mode=AudioTrackMode.EXPLICIT)

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred"


def test_preferred_says_nothing_while_the_audio_is_off():
    manager = _manager(
        preferred=None, track_id=DISABLED_TRACK, mode=AudioTrackMode.DISABLED
    )

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred"


def test_preferred_says_nothing_for_a_track_that_names_no_language():
    manager = _manager(tracks={0: _track(None)}, preferred=None, track_id=0)

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred"


def test_following_the_preference_ticks_the_preference_not_its_answer():
    """Otherwise two rows would be ticked, and one of them a coincidence."""

    manager = _manager(mode=AudioTrackMode.PREFERRED, track_id=0)

    assert manager.is_active_audio_track(0) is False


def test_a_track_picked_by_hand_ticks_itself():
    manager = _manager(mode=AudioTrackMode.EXPLICIT, track_id=1)

    assert manager.is_active_audio_track(1) is True
    assert manager.is_active_audio_track(0) is False


def test_preferred_names_what_the_preference_gives_not_what_is_playing():
    """Klingon is on screen because it was asked for; English is the fallback."""

    manager = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh", "en"),
        mode=AudioTrackMode.EXPLICIT,
        playing_language="tlh",
        preferred_language="en",
    )

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred (English)"


def test_a_language_picked_by_hand_ticks_itself():
    manager = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh"),
        mode=AudioTrackMode.EXPLICIT,
        playing_language="tlh",
    )

    assert manager.is_active_audio_language("tlh") is True
    assert manager.is_active_audio_language("cop") is False


def test_a_language_reached_by_preference_is_not_ticked():
    manager = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh"),
        mode=AudioTrackMode.PREFERRED,
        playing_language="tlh",
    )

    assert manager.is_active_audio_language("tlh") is False


def test_disabling_audio_is_ticked_by_the_mode_not_the_track_id():
    """The track id is overwritten with whatever libVLC settled on."""

    disable = _manager().menu_generator_audio_track()[2]

    assert disable["check_if"] == (
        "is_active_param_set_to",
        "audio_track_mode",
        AudioTrackMode.DISABLED,
    )
    assert disable["func"] == ("active", "set_audio_track", DISABLED_TRACK)


@pytest.mark.parametrize(
    ("mode", "ticked"),
    [
        (AudioTrackMode.PREFERRED, "Preferred (English)"),
        (AudioTrackMode.DISABLED, "Disable Audio"),
        (AudioTrackMode.EXPLICIT, None),
    ],
)
def test_the_mode_in_force_is_the_one_ticked(mode, ticked):
    menu = _manager(mode=mode).menu_generator_audio_track()

    rendered = [_rendered(menu[0], mode), _rendered(menu[2], mode)]

    for action in rendered:
        action.adapt()

    checked = [a.text() for a in rendered if a.isChecked()]

    assert checked == ([ticked] if ticked else [])


def test_the_preference_row_renders_the_list_it_is_following():
    menu = _manager().menu_generator_audio_track()

    action = _rendered(menu[1], AudioTrackMode.PREFERRED, value="en, ja")
    action.adapt()

    assert action.text() == "Languages: en, ja"
    assert action.is_skipped is False


@pytest.mark.parametrize(
    "mode",
    [AudioTrackMode.PREFERRED, AudioTrackMode.DISABLED, AudioTrackMode.EXPLICIT],
)
def test_the_preference_row_stays_put_whatever_is_playing(mode):
    """It says what going back to the preference would give, always worth reading."""

    menu = _manager(mode=mode).menu_generator_audio_track()

    action = _rendered(menu[1], mode, value="en, ja")
    action.adapt()

    assert action.is_skipped is False
    assert action.text() == "Languages: en, ja"


def _rendered(template, mode, value=None):
    commands = Commands()
    commands.update(
        {
            "active": lambda command, *args: value,
            "is_active_initialized": lambda: True,
            "is_active_param_set_to": lambda attr, expected: mode == expected,
        }
    )

    manager = Mock(spec=ActionsManager)
    manager._ctx = Mock()
    manager._ctx.commands = commands
    manager.parent = Mock(return_value=None)
    manager._map_dynamic_functions = partial(
        ActionsManager._map_dynamic_functions, manager
    )

    return ActionsManager._make_action(manager, template)


class TestTellingTracksApart:
    """Several tracks in one language, which is ordinary for a film."""

    def test_each_one_is_named_by_what_the_container_called_it(self):
        menu = _manager(tracks=DUBBED_FILE_TRACKS).menu_generator_audio_track()

        assert _titles(menu)[4:] == [
            f"Russian {DASH} MVO (Rakurs) [VHS Hi-Fi], {CODEC}",
            f"Russian {DASH} MVO (ORT) [VHS], {CODEC}",
            f"Russian {DASH} VO (Buratino) [VHS], {CODEC}",
            f"English {DASH} Original, {CODEC}",
        ]

    def test_the_entries_are_all_different(self):
        """The whole point: three identical rows are three unusable rows."""

        titles = _titles(
            _manager(tracks=DUBBED_FILE_TRACKS).menu_generator_audio_track()
        )

        assert len(set(titles[4:])) == len(titles[4:])

    def test_preferred_names_the_track_it_picks_not_just_the_language(self):
        manager = _manager(tracks=DUBBED_FILE_TRACKS, preferred=1)

        assert manager._preferred_audio_track_menu_item()["title"] == (
            f"Preferred (Russian {DASH} MVO (ORT) [VHS])"
        )

    def test_a_name_that_only_repeats_the_language_is_left_out(self):
        menu = _manager(
            tracks={0: _track("eng", "English")}
        ).menu_generator_audio_track()

        assert _titles(menu)[4:] == [f"English, {CODEC}"]

    def test_so_is_one_that_only_repeats_the_code(self):
        menu = _manager(tracks={0: _track("eng", "eng")}).menu_generator_audio_track()

        assert _titles(menu)[4:] == [f"English, {CODEC}"]

    def test_an_untagged_track_is_named_by_what_it_does_have(self):
        menu = _manager(
            tracks={0: _track(None, "Commentary")}
        ).menu_generator_audio_track()

        assert _titles(menu)[4:] == [f"Commentary, {CODEC}"]

    def test_a_language_with_no_name_of_its_own_keeps_its_code(self):
        """pycountry knows most of them, and the code beats saying nothing."""

        menu = _manager(
            tracks={0: _track("qtz", "Invented")}
        ).menu_generator_audio_track()

        assert _titles(menu)[4:] == [f"qtz {DASH} Invented, {CODEC}"]
