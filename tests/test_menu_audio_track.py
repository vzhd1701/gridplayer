"""The Audio Track submenu: one list, whichever way the video is dubbed."""

from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioLanguage,
    AudioPreferred,
    AudioTrackId,
)
from gridplayer.params.menu import SECTIONS
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
    selection=None,
    preferred=0,
    playing_language=None,
    preferred_language=None,
    is_local_file=False,
    discovered=(),
    external=(),
    external_ids=None,
    is_autodiscover=True,
    playing_track=None,
):
    audio_tracks = FILE_TRACKS if tracks is None else tracks
    external = list(external)

    # the player says which tracks arrived from a file; here they are the
    # last of them, the way libVLC hands them over
    external_tracks = (
        dict(zip(list(audio_tracks)[-len(external) :], external)) if external else {}
    )

    block = SimpleNamespace(
        audio_tracks=audio_tracks,
        audio_language_options=languages,
        audio_language=playing_language,
        preferred_audio_track_id=preferred,
        preferred_audio_language=preferred_language,
        is_local_file=is_local_file,
        audio_track_playing=playing_track,
        audio_language_playing=playing_language,
        discovered_audio_files=list(discovered),
        offered_audio_files=list(discovered),
        external_audio_tracks=external_tracks,
        external_audio_track_ids=tuple(
            external_tracks if external_ids is None else external_ids
        ),
        attached_audio_file=next(iter(external_tracks.values()), None),
        video_params=SimpleNamespace(
            audio_selection=AudioPreferred() if selection is None else selection,
            external_audio=external,
            is_external_audio_autodiscover=is_autodiscover,
        ),
    )

    return _Manager(block)


def _titles(menu):
    return [item if item == "---" else item["title"] for item in menu]


def _row(menu, title):
    return next(item for item in menu if item != "---" and item["title"] == title)


def _marked(menu):
    """The rows carrying the play mark, by title."""

    return [
        item["title"] for item in menu if item != "---" and item.get("icon") == "play"
    ]


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
        "Default",
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

    menus = [
        _manager(
            tracks=STREAM_TRACKS, languages=("cop", "tlh"), playing_language="tlh"
        ).menu_generator_audio_track(),
        _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            discovered=(Path("D:/films/Movie.rus.mp3"),),
            external=(Path("D:/films/Movie.fra.mp3"),),
        ).menu_generator_audio_track(),
    ]

    for menu in menus:
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

    assert _titles(menu)[5:] == ["Coptic", "Klingon", "English"]


def test_a_video_with_nothing_to_choose_still_shows_its_one_track():
    menu = _manager(tracks={0: _track("eng")}).menu_generator_audio_track()

    assert _titles(menu)[5:] == ["English, mp4a, 2 ch, 48 kHz, 128 kbps"]


def test_an_untagged_track_keeps_the_details_it_does_have():
    menu = _manager(tracks={0: _track(None)}).menu_generator_audio_track()

    assert _titles(menu)[5:] == ["mp4a, 2 ch, 48 kHz, 128 kbps"]


def test_the_preference_row_sits_under_the_entry_that_follows_it():
    row = _manager().menu_generator_audio_track()[2]

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

    manager = _manager(preferred=None, playing_track=1)

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred (Japanese)"


def test_preferred_says_nothing_once_a_track_is_picked_by_hand():
    """What reverting would give is the file's own choice, which is unknown."""

    manager = _manager(preferred=None, selection=AudioTrackId(id=1))

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred"


def test_preferred_says_nothing_while_the_audio_is_off():
    manager = _manager(preferred=None, selection=AudioDisabled())

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred"


def test_preferred_says_nothing_for_a_track_that_names_no_language():
    manager = _manager(tracks={0: _track(None)}, preferred=None, playing_track=0)

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred"


def test_following_the_preference_ticks_the_preference_not_its_answer():
    """Otherwise two rows would be ticked, and one of them a coincidence."""

    manager = _manager(playing_track=0)

    assert manager.is_active_audio_track(0) is False


def test_a_track_picked_by_hand_ticks_itself():
    manager = _manager(selection=AudioTrackId(id=1))

    assert manager.is_active_audio_track(1) is True
    assert manager.is_active_audio_track(0) is False


def test_preferred_names_what_the_preference_gives_not_what_is_playing():
    """Klingon is on screen because it was asked for; English is the fallback."""

    manager = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh", "en"),
        selection=AudioLanguage(tag="tlh"),
        playing_language="tlh",
        preferred_language="en",
    )

    assert manager._preferred_audio_track_menu_item()["title"] == "Preferred (English)"


def test_a_language_picked_by_hand_ticks_itself():
    manager = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh"),
        selection=AudioLanguage(tag="tlh"),
        playing_language="tlh",
    )

    assert manager.is_active_audio_language("tlh") is True
    assert manager.is_active_audio_language("cop") is False


def test_a_language_reached_by_preference_is_not_ticked():
    manager = _manager(
        tracks=STREAM_TRACKS,
        languages=("cop", "tlh"),
        playing_language="tlh",
    )

    assert manager.is_active_audio_language("tlh") is False


def test_disabling_audio_is_ticked_by_the_choice_not_by_a_track():
    """Silence is a choice of its own, and answers to nothing else."""

    disable = _manager().menu_generator_audio_track()[3]

    assert disable["check_if"] == "is_active_audio_disabled"
    assert disable["func"] == ("active", "set_audio_track", DISABLED_TRACK)


@pytest.mark.parametrize(
    ("selection", "ticked"),
    [
        (AudioPreferred(), "Preferred (English)"),
        (AudioDisabled(), "Disable Audio"),
        (AudioTrackId(id=1), None),
    ],
)
def test_the_choice_in_force_is_the_one_ticked(selection, ticked):
    menu = _manager(selection=selection).menu_generator_audio_track()

    rendered = [_rendered(menu[1], selection), _rendered(menu[3], selection)]

    for action in rendered:
        action.adapt()

    checked = [a.text() for a in rendered if a.isChecked()]

    assert checked == ([ticked] if ticked else [])


def test_the_preference_row_renders_the_list_it_is_following():
    menu = _manager().menu_generator_audio_track()

    action = _rendered(menu[2], AudioPreferred(), value="en, ja")
    action.adapt()

    assert action.text() == "Languages: en, ja"
    assert action.is_skipped is False


@pytest.mark.parametrize(
    "selection",
    [AudioPreferred(), AudioDisabled(), AudioTrackId(id=1)],
)
def test_the_preference_row_stays_put_whatever_is_playing(selection):
    """It says what going back to the preference would give, always worth reading."""

    menu = _manager(selection=selection).menu_generator_audio_track()

    action = _rendered(menu[2], selection, value="en, ja")
    action.adapt()

    assert action.is_skipped is False
    assert action.text() == "Languages: en, ja"


def _rendered(template, selection, value=None):
    commands = Commands()
    commands.update(
        {
            "active": lambda command, *args: value,
            "is_active_initialized": lambda: True,
            "is_active_param_set_to": lambda attr, expected: False,
            "is_active_audio_preferred": lambda: isinstance(selection, AudioPreferred),
            "is_active_audio_disabled": lambda: isinstance(selection, AudioDisabled),
            "is_active_audio_default": lambda: isinstance(selection, AudioDefault),
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

        assert _titles(menu)[5:] == [
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

        assert len(set(titles[5:])) == len(titles[5:])

    def test_preferred_names_the_track_it_picks_not_just_the_language(self):
        manager = _manager(tracks=DUBBED_FILE_TRACKS, preferred=1)

        assert manager._preferred_audio_track_menu_item()["title"] == (
            f"Preferred (Russian {DASH} MVO (ORT) [VHS])"
        )

    def test_a_name_that_only_repeats_the_language_is_left_out(self):
        menu = _manager(
            tracks={0: _track("eng", "English")}
        ).menu_generator_audio_track()

        assert _titles(menu)[5:] == [f"English, {CODEC}"]

    def test_so_is_one_that_only_repeats_the_code(self):
        menu = _manager(tracks={0: _track("eng", "eng")}).menu_generator_audio_track()

        assert _titles(menu)[5:] == [f"English, {CODEC}"]

    def test_an_untagged_track_is_named_by_what_it_does_have(self):
        menu = _manager(
            tracks={0: _track(None, "Commentary")}
        ).menu_generator_audio_track()

        assert _titles(menu)[5:] == [f"Commentary, {CODEC}"]

    def test_a_language_with_no_name_of_its_own_keeps_its_code(self):
        """pycountry knows most of them, and the code beats saying nothing."""

        menu = _manager(
            tracks={0: _track("qtz", "Invented")}
        ).menu_generator_audio_track()

        assert _titles(menu)[5:] == [f"qtz {DASH} Invented, {CODEC}"]


class TestAudioKeptBesideTheVideo:
    """A file next to the video is a third place its sound can come from."""

    RUSSIAN = Path("D:/films/Movie.rus.mp3")
    FRENCH = Path("D:/films/Movie.fra.mp3")

    def test_a_video_from_the_network_is_offered_none_of_it(self):
        menu = _manager().menu_generator_audio_track()

        assert "Add External Audio..." not in _titles(menu)

    def test_a_local_file_can_be_given_audio_of_its_own(self):
        menu = _manager(is_local_file=True).menu_generator_audio_track()

        assert _titles(menu)[-2:] == ["Add External Audio...", "Detect Audio Files"]

    def test_what_lies_beside_it_is_listed_under_its_own_tracks(self):
        menu = _manager(
            is_local_file=True, discovered=(self.RUSSIAN, self.FRENCH)
        ).menu_generator_audio_track()

        assert _titles(menu)[-5:-3] == ["Movie.rus.mp3", "Movie.fra.mp3"]

    def test_picking_one_plays_that_file(self):
        menu = _manager(
            is_local_file=True, discovered=(self.RUSSIAN,)
        ).menu_generator_audio_track()

        row = _row(menu, "Movie.rus.mp3")

        assert row["func"] == ("active", "play_external_audio", str(self.RUSSIAN))

    def test_the_one_that_is_open_is_spelled_out_among_the_files(self):
        """It answers to its file name, which is the only name it has."""

        menu = _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            external=(self.RUSSIAN,),
        ).menu_generator_audio_track()

        assert f"Movie.rus.mp3, {CODEC}" in _titles(menu)

    def test_it_is_not_listed_among_the_video_s_own_tracks(self):
        """Which list a row is in is what says where the sound comes from."""

        menu = _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            external=(self.RUSSIAN,),
        ).menu_generator_audio_track()

        titles = _titles(menu)
        own_tracks = titles[: titles.index(f"Movie.rus.mp3, {CODEC}")]

        assert f"{CODEC}" not in own_tracks

    def test_the_video_s_own_tracks_are_not_marked(self):
        menu = _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            external=(self.RUSSIAN,),
        ).menu_generator_audio_track()

        assert f"English, {CODEC}" in _titles(menu)

    def test_a_file_that_brought_no_track_is_still_named(self):
        """Otherwise it would look as though nothing had been opened."""

        menu = _manager(
            tracks={0: _track("eng")},
            is_local_file=True,
            external=(self.RUSSIAN,),
            external_ids=(),
        ).menu_generator_audio_track()

        assert "Movie.rus.mp3" in _titles(menu)

    def test_taking_them_back_is_only_offered_with_something_to_take(self):
        without = _manager(is_local_file=True).menu_generator_audio_track()
        with_file = _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            external=(self.RUSSIAN,),
        ).menu_generator_audio_track()

        assert "Remove External Audio" not in _titles(without)
        assert "Remove External Audio" in _titles(with_file)

    def test_the_detection_is_ticked_while_it_is_on(self):
        menu = _manager(is_local_file=True).menu_generator_audio_track()

        row = _row(menu, "Detect Audio Files")

        assert row["check_if"] == (
            "is_active_param_set_to",
            "is_external_audio_autodiscover",
            True,
        )

    @pytest.mark.parametrize("is_on", [True, False])
    def test_clicking_the_detection_sets_it_the_other_way(self, is_on):
        menu = _manager(
            is_local_file=True, is_autodiscover=is_on
        ).menu_generator_audio_track()

        row = _row(menu, "Detect Audio Files")

        assert row["func"] == ("active", "set_external_audio_autodiscover", not is_on)


class TestAVideoWithNoSoundOfItsOwn:
    def test_it_still_shows_what_lies_beside_it(self):
        menu = _manager(
            tracks={}, is_local_file=True, discovered=(Path("D:/films/Movie.mp3"),)
        ).menu_generator_audio_track()

        assert _titles(menu) == [
            "Movie.mp3",
            "---",
            "Add External Audio...",
            "Detect Audio Files",
        ]

    def test_a_silent_video_can_still_be_given_a_file(self):
        """Nothing to choose between is the very reason to go looking."""

        menu = _manager(tracks={}, is_local_file=True).menu_generator_audio_track()

        assert _titles(menu) == ["Add External Audio...", "Detect Audio Files"]

    def test_a_silent_stream_has_no_menu_at_all(self):
        assert _manager(tracks={}).menu_generator_audio_track() == {}


class TestTheOneBeingHeard:
    """Chosen and playing are different things, as on the stream ladder."""

    def test_the_track_the_sound_comes_from_is_marked(self):
        menu = _manager(playing_track=1).menu_generator_audio_track()

        assert _marked(menu) == [f"Japanese, {CODEC}"]

    def test_the_preference_is_ticked_where_the_track_it_found_is_marked(self):
        """A preference names no track, so the mark is the only answer."""

        menu = _manager(preferred=1, playing_track=1).menu_generator_audio_track()

        ticked = _row(menu, "Preferred (Japanese)")
        marked = _row(menu, f"Japanese, {CODEC}")

        assert ticked["check_if"] == "is_active_audio_preferred"
        assert ticked["icon"] == "empty"
        assert marked["icon"] == "play"

    def test_one_picked_by_hand_is_both_ticked_and_marked(self):
        menu = _manager(
            selection=AudioTrackId(id=2), playing_track=2
        ).menu_generator_audio_track()

        row = _row(menu, f"French, {CODEC}")

        assert row["icon"] == "play"
        assert row["check_if"] == ("is_active_audio_track", 2)

    def test_nothing_is_marked_while_the_sound_is_off(self):
        menu = _manager(
            selection=AudioDisabled(), playing_track=DISABLED_TRACK
        ).menu_generator_audio_track()

        assert _marked(menu) == []

    def test_a_video_that_has_not_said_yet_marks_nothing(self):
        menu = _manager(playing_track=None).menu_generator_audio_track()

        assert _marked(menu) == []

    def test_the_language_being_heard_is_marked(self):
        """A dubbed video is picked from by language, and one is playing."""

        menu = _manager(
            tracks=STREAM_TRACKS,
            languages=("cop", "tlh"),
            playing_language="tlh",
        ).menu_generator_audio_track()

        assert _marked(menu) == ["Klingon"]

    def test_an_external_track_is_marked_like_any_other(self):
        menu = _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            external=(Path("D:/films/Movie.rus.mp3"),),
            playing_track=1,
        ).menu_generator_audio_track()

        assert _marked(menu) == [f"Movie.rus.mp3, {CODEC}"]

    def test_the_files_are_kept_apart_from_what_can_be_done_with_them(self):
        """One list is things to play, the other is things to do."""

        menu = _manager(
            is_local_file=True, discovered=(Path("D:/films/Movie.rus.mp3"),)
        ).menu_generator_audio_track()

        titles = _titles(menu)

        assert titles[titles.index("Movie.rus.mp3") + 1] == "---"


class TestAFileHoldingSeveralTracks:
    """Which of them to play is as much a choice as which file."""

    MULTI = Path("D:/films/Movie.dubs.m4a")

    def _menu(self, first, second):
        return _manager(
            tracks={0: _track("eng"), 1: first, 2: second},
            is_local_file=True,
            external=(self.MULTI, self.MULTI),
        ).menu_generator_audio_track()

    def test_each_is_named_by_the_language_it_carries(self):
        menu = self._menu(_track("rus"), _track("jpn"))

        assert _titles(menu)[-6:-4] == [
            f"Movie.dubs.m4a {DASH} Russian, {CODEC}",
            f"Movie.dubs.m4a {DASH} Japanese, {CODEC}",
        ]

    def test_the_name_the_file_gave_one_is_used_where_it_has_one(self):
        menu = self._menu(_track("rus", "MVO (Rakurs)"), _track("rus", "VO (ORT)"))

        assert _titles(menu)[-6:-4] == [
            f"Movie.dubs.m4a {DASH} Russian {DASH} MVO (Rakurs), {CODEC}",
            f"Movie.dubs.m4a {DASH} Russian {DASH} VO (ORT), {CODEC}",
        ]

    def test_tracks_that_say_nothing_at_all_are_numbered(self):
        """Otherwise they read as the same row twice."""

        menu = self._menu(_track(None), _track(None))

        assert _titles(menu)[-6:-4] == [
            f"Movie.dubs.m4a {DASH} #1, {CODEC}",
            f"Movie.dubs.m4a {DASH} #2, {CODEC}",
        ]

    def test_a_file_holding_one_track_is_not_numbered(self):
        menu = _manager(
            tracks={0: _track("eng"), 1: _track(None)},
            is_local_file=True,
            external=(self.MULTI,),
        ).menu_generator_audio_track()

        assert f"Movie.dubs.m4a, {CODEC}" in _titles(menu)
