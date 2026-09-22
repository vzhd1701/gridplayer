"""The Subtitle Track submenu: everything a video's subtitles can be."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleDisabled,
    SubtitleLanguage,
    SubtitlePreferred,
    SubtitleTrackId,
)
from gridplayer.params.menu import SECTIONS
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.utils.track_language import language_name
from gridplayer.vlc_player.static import SubtitleTrack


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _track(language, description=None):
    return SubtitleTrack(
        codec="Text subtitles with various tags",
        bitrate=0,
        language=language,
        description=description,
        encoding="UTF-8",
    )


FILE_TRACKS = {0: _track("eng"), 1: _track("jpn"), 2: _track("fre")}


class _Manager(ActiveBlockManager):
    """The manager's menu methods, without the rest of the player behind them."""

    def __init__(self, block):
        self._ctx = SimpleNamespace(active_block=block)

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None


def _manager(
    tracks=None,
    selection=None,
    preferred=None,
    default=None,
    showing=None,
    is_local_file=False,
    offered=(),
    external=(),
    is_autodiscover=True,
):
    subtitle_tracks = FILE_TRACKS if tracks is None else tracks
    external = list(external)

    # the player says which tracks arrived from a file; here they are the
    # last of them, the way libVLC hands them over
    external_tracks = (
        dict(zip(list(subtitle_tracks)[-len(external) :], external)) if external else {}
    )

    def _number_in_file(track_id, file_path):
        from_file = [
            other
            for other, other_file in external_tracks.items()
            if other_file == file_path
        ]

        return from_file.index(track_id) if track_id in from_file else 0

    def _language_key(track_id):
        track = subtitle_tracks.get(track_id)

        if track is None or track_id in external_tracks:
            return None

        return track.language

    def _external_track_name(track_id):
        """None where the "language" is only the file's own name again."""

        track = subtitle_tracks.get(track_id)
        file_path = external_tracks.get(track_id)

        if track is None or not track.language or file_path is None:
            return None

        if track.language.replace("\\", "/").rsplit("/", 1)[-1] == file_path.stem:
            return None

        return language_name(track.language) or track.language

    block = SimpleNamespace(
        subtitle_tracks=subtitle_tracks,
        has_subtitles=bool(subtitle_tracks),
        subtitle_track_showing=showing,
        preferred_subtitle_track_id=preferred,
        default_subtitle_track_id=default,
        external_subtitle_track_ids=tuple(external_tracks),
        external_subtitle_tracks=external_tracks,
        offered_subtitle_files=list(offered),
        subtitle_file_name=lambda path: path.name,
        external_subtitle_track_name=_external_track_name,
        subtitle_number_in_file=_number_in_file,
        subtitle_language_key=_language_key,
        is_local_file=is_local_file,
        video_params=SimpleNamespace(
            subtitle_selection=SubtitleDisabled() if selection is None else selection,
            external_subtitles=external,
            is_external_subtitle_autodiscover=is_autodiscover,
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


def test_the_submenu_is_wired_into_the_video_menu():
    subtitles = next(
        item
        for item in SECTIONS["video_active"]
        if isinstance(item, tuple) and item[0] == "Subtitles"
    )

    assert subtitles[1] == "Subtitle Track"


class TestWhatIsOnOffer:
    def test_a_file_offers_its_tracks(self):
        menu = _manager().menu_generator_subtitle_track()

        assert "English" in _titles(menu)
        assert "Japanese" in _titles(menu)
        assert "French" in _titles(menu)

    def test_off_comes_first_because_that_is_where_a_video_starts(self):
        menu = _manager().menu_generator_subtitle_track()

        assert _titles(menu)[0] == "Off"

    def test_a_video_with_none_and_nowhere_to_look_offers_nothing(self):
        menu = _manager(tracks={}).menu_generator_subtitle_track()

        assert menu == {}

    def test_the_container_default_is_offered_only_where_there_is_one(self):
        assert "Default" not in _titles(_manager().menu_generator_subtitle_track())

        with_default = _manager(default=1).menu_generator_subtitle_track()

        assert "Default" in _titles(with_default)

    def test_the_preference_says_what_following_it_would_give(self):
        menu = _manager(preferred=1).menu_generator_subtitle_track()

        assert "Preferred (Japanese)" in _titles(menu)

    def test_a_preference_that_answers_nothing_says_only_its_own_name(self):
        menu = _manager(preferred=None).menu_generator_subtitle_track()

        assert "Preferred" in _titles(menu)

    def test_a_track_with_no_language_falls_back_on_its_codec(self):
        menu = _manager(tracks={0: _track(None)}).menu_generator_subtitle_track()

        assert "Text subtitles with various tags" in _titles(menu)

    def test_what_the_text_is_read_as_comes_last_and_on_its_own(self):
        """The row nobody needs: a file written in UTF-8 never reaches it."""

        titles = _titles(_manager().menu_generator_subtitle_track())

        assert titles[-1] == "Encoding: %v"
        assert titles[-2] == "---"

    def test_a_video_with_nothing_to_read_is_not_asked_how_to_read_it(self):
        menu = _manager(
            tracks={}, offered=[Path("a.srt")]
        ).menu_generator_subtitle_track()

        assert "Encoding: %v" not in _titles(menu)


class TestWhatIsTicked:
    def test_off_where_nothing_was_asked_for(self):
        menu = _manager(selection=SubtitleDisabled()).menu_generator_subtitle_track()

        assert _row(menu, "Off")["check_if"] == "is_active_subtitle_disabled"

    @pytest.mark.parametrize(
        ("selection", "expected"),
        [
            (SubtitleDisabled(), ["Off"]),
            (SubtitlePreferred(), ["Preferred"]),
            (SubtitleDefault(), ["Default"]),
            (SubtitleTrackId(id=1), ["Japanese"]),
            (SubtitleLanguage(tag="fre"), ["French"]),
        ],
    )
    def test_the_row_that_was_chosen(self, selection, expected):
        manager = _manager(selection=selection, default=0)
        menu = manager.menu_generator_subtitle_track()

        ticked = [
            item["title"]
            for item in menu
            if item != "---" and _is_ticked(manager, item.get("check_if"))
        ]

        assert ticked == expected

    def test_the_one_on_screen_is_marked_even_where_nothing_named_it(self):
        """A preference names no track; the mark is all that says which answered."""

        menu = _manager(
            selection=SubtitlePreferred(), preferred=2, showing=2
        ).menu_generator_subtitle_track()

        assert _marked(menu) == ["French"]


def _is_ticked(manager, check_if):
    if check_if is None:
        return False

    if isinstance(check_if, tuple):
        return manager.commands[check_if[0]](*check_if[1:])

    return manager.commands[check_if]()


class TestFilesKeptBesideTheVideo:
    def test_a_video_that_is_not_a_file_is_offered_none_of_this(self):
        menu = _manager(is_local_file=False).menu_generator_subtitle_track()

        assert "Add External Subtitles..." not in _titles(menu)

    def test_the_files_found_beside_it_are_offered_by_name(self):
        menu = _manager(
            is_local_file=True, offered=[Path("Movie.en.srt")]
        ).menu_generator_subtitle_track()

        assert "Movie.en.srt" in _titles(menu)

    def test_a_file_already_on_is_listed_as_the_track_it_became(self):
        menu = _manager(
            tracks={0: _track("eng"), 1: _track("C:\\films\\Movie.ja")},
            is_local_file=True,
            external=[Path("Movie.ja.srt")],
            showing=1,
        ).menu_generator_subtitle_track()

        assert "Movie.ja.srt" in _titles(menu)
        assert _marked(menu) == ["Movie.ja.srt"]

    def test_a_file_holding_several_tracks_names_each_by_its_language(self):
        """A VobSub index off a DVD carries a language per track."""

        menu = _manager(
            tracks={0: _track("eng"), 1: _track("en"), 2: _track("de")},
            is_local_file=True,
            external=[Path("Movie.idx"), Path("Movie.idx")],
        ).menu_generator_subtitle_track()

        titles = _titles(menu)

        assert "Movie.idx \u2014 English" in titles
        assert "Movie.idx \u2014 German" in titles

    def test_a_file_that_says_nothing_about_its_tracks_numbers_them(self):
        menu = _manager(
            tracks={0: _track("eng"), 1: _track("Movie"), 2: _track("Movie")},
            is_local_file=True,
            external=[Path("Movie.srt"), Path("Movie.srt")],
        ).menu_generator_subtitle_track()

        titles = _titles(menu)

        assert "Movie.srt \u2014 #1" in titles
        assert "Movie.srt \u2014 #2" in titles

    def test_removing_them_is_offered_only_where_some_were_picked(self):
        without = _manager(is_local_file=True).menu_generator_subtitle_track()

        assert "Remove External Subtitles" not in _titles(without)

        with_files = _manager(
            tracks={0: _track("eng"), 1: _track("x")},
            is_local_file=True,
            external=[Path("Movie.srt")],
        ).menu_generator_subtitle_track()

        assert "Remove External Subtitles" in _titles(with_files)

    def test_a_silent_video_still_gets_the_files_beside_it(self):
        menu = _manager(
            tracks={}, is_local_file=True, offered=[Path("Movie.en.srt")]
        ).menu_generator_subtitle_track()

        assert "Movie.en.srt" in _titles(menu)
        assert "Add External Subtitles..." in _titles(menu)
