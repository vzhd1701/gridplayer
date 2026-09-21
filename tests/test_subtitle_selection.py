"""One field says what a video's subtitles were chosen to be."""

import json
from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.models.playlist import Playlist
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleDisabled,
    SubtitleExternal,
    SubtitleLanguage,
    SubtitlePreferred,
    SubtitleTrackId,
    track_of_file,
)
from gridplayer.models.video import Video, default_subtitle_selection
from gridplayer.params.static import SubtitleTrackMode
from gridplayer.settings import Settings
from gridplayer.vlc_player.static import DISABLED_TRACK, wanted_subtitle_track_id

from .test_vlc_player_subtitle_tracks import _manager
from .test_vlc_player_tracks_manager import FakeMediaPlayer, make_subtitle_track

URI = "http://example.com/a.mp4"


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _video(**kwargs):
    return Video(uri=URI, **kwargs)


def _reopened(video):
    """The same video, through a playlist file and back."""

    return Playlist.parse(Playlist(videos=[video]).dumps()).videos[0]


def _tracks(*languages):
    player = FakeMediaPlayer(
        spu_desc=[
            (-1, b"Disable"),
            *((index, b"Track") for index, _ in enumerate(languages)),
        ]
    )

    media_tracks = [
        make_subtitle_track(track_id=index, language=language)
        for index, language in enumerate(languages)
    ]

    return _manager(player, media_tracks).subtitle_tracks


class TestTheSixThingsSubtitlesCanBe:
    @pytest.mark.parametrize(
        "selection",
        [
            SubtitleDisabled(),
            SubtitlePreferred(),
            SubtitleDefault(),
            SubtitleTrackId(id=7),
            SubtitleLanguage(tag="rus"),
            SubtitleExternal(file=Path("C:/films/Movie.rus.srt").absolute()),
        ],
    )
    def test_each_survives_being_written_down_and_read_back(self, selection):
        reopened = _reopened(_video(subtitle_selection=selection))

        assert reopened.subtitle_selection == selection

    def test_they_are_told_apart_by_what_they_say_they_are(self):
        written = json.loads(
            Playlist(videos=[_video(subtitle_selection=SubtitleTrackId(id=7))]).dumps()
        )

        assert written["videos"][0]["subtitle_selection"] == {"kind": "track", "id": 7}


class TestWhereEveryVideoStarts:
    def test_off_unless_the_defaults_say_otherwise(self):
        assert default_subtitle_selection() == SubtitleDisabled()
        assert _video().subtitle_selection == SubtitleDisabled()

    def test_a_playlist_written_before_subtitles_existed_opens_with_none(self):
        older = Video.model_validate({"uri": URI, "audio_track_mode": "explicit"})

        assert older.subtitle_selection == SubtitleDisabled()

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            (SubtitleTrackMode.DISABLED, SubtitleDisabled()),
            (SubtitleTrackMode.PREFERRED, SubtitlePreferred()),
            (SubtitleTrackMode.DEFAULT, SubtitleDefault()),
        ],
    )
    def test_the_defaults_decide_which_one(self, mode, expected):
        Settings().set("video_defaults/subtitle_track_mode", mode)

        assert default_subtitle_selection() == expected


class TestWhichTrackTheSettingsCallFor:
    def test_off_asks_for_nothing_at_all(self):
        video = _video(subtitle_selection=SubtitleDisabled())

        assert wanted_subtitle_track_id(video, _tracks(b"eng")) == DISABLED_TRACK

    def test_the_container_default_is_left_to_libvlc(self):
        """Which has already opened on it, so there is nothing to ask for."""

        video = _video(subtitle_selection=SubtitleDefault())

        assert wanted_subtitle_track_id(video, _tracks(b"eng")) is None

    def test_a_track_named_by_number_is_used_as_named(self):
        video = _video(subtitle_selection=SubtitleTrackId(id=1))

        assert wanted_subtitle_track_id(video, _tracks(b"eng", b"spa")) == 1

    def test_a_track_named_by_language_is_looked_up_afresh(self):
        video = _video(subtitle_selection=SubtitleLanguage(tag="spa"))

        assert wanted_subtitle_track_id(video, _tracks(b"eng", b"spa")) == 1

    def test_the_preference_is_followed_where_it_answers(self):
        video = _video(
            subtitle_selection=SubtitlePreferred(), subtitle_languages="ja, es"
        )

        assert wanted_subtitle_track_id(video, _tracks(b"eng", b"spa")) == 1

    def test_a_preference_nothing_answers_shows_none(self):
        """Where the sound would take whatever it could get.

        A subtitle in a language nobody asked for is worse than a bare
        picture, which is not true of a sound track nobody asked for.
        """

        video = _video(subtitle_selection=SubtitlePreferred(), subtitle_languages="ja")

        assert (
            wanted_subtitle_track_id(video, _tracks(b"eng", b"spa")) == DISABLED_TRACK
        )

    def test_a_language_that_is_gone_falls_back_on_the_preference(self):
        video = _video(
            subtitle_selection=SubtitleLanguage(tag="rus"), subtitle_languages="en"
        )

        assert wanted_subtitle_track_id(video, _tracks(b"eng", b"spa")) == 0

    def test_a_file_of_its_own_is_never_matched_on_language(self):
        """libVLC writes the file's name where a language belongs.

        Left in, that path would answer a preference for a language it
        only happens to spell like.
        """

        tracks = _tracks(b"eng", b"C:\\films\\Movie.ja")

        video = _video(subtitle_selection=SubtitlePreferred(), subtitle_languages="ja")

        assert (
            wanted_subtitle_track_id(video, tracks, external_ids=(1,)) == DISABLED_TRACK
        )


class TestNamingATrackInsideAFile:
    def test_the_track_that_was_picked(self):
        assert track_of_file(SubtitleExternal(file=Path("s.srt"), track=1), (4, 5)) == 5

    def test_a_file_holding_fewer_tracks_than_it_did_still_shows_one(self):
        assert track_of_file(SubtitleExternal(file=Path("s.srt"), track=3), (4,)) == 4

    def test_a_file_that_brought_nothing_names_nothing(self):
        assert track_of_file(SubtitleExternal(file=Path("s.srt")), ()) is None


class TestFilesTravelWithThePlaylist:
    def test_a_chosen_file_is_written_beside_the_video(self, tmp_path):
        subtitles = tmp_path / "Movie.en.srt"
        subtitles.write_text("1\n", encoding="utf-8")

        video = _video(
            external_subtitles=[subtitles],
            subtitle_selection=SubtitleExternal(file=subtitles),
        )

        playlist = Playlist(videos=[video], save_paths_relative=True)
        written = json.loads(playlist.dumps(base_dir=tmp_path))

        assert written["videos"][0]["external_subtitles"] == ["Movie.en.srt"]
        assert written["videos"][0]["subtitle_selection"]["file"] == "Movie.en.srt"

    def test_and_found_again_where_the_playlist_is(self, tmp_path):
        subtitles = tmp_path / "Movie.en.srt"
        subtitles.write_text("1\n", encoding="utf-8")

        video = _video(
            external_subtitles=[subtitles],
            subtitle_selection=SubtitleExternal(file=subtitles),
        )

        text = Playlist(videos=[video], save_paths_relative=True).dumps(
            base_dir=tmp_path
        )

        reopened = Playlist.parse(text, base_dir=tmp_path).videos[0]

        assert reopened.external_subtitles == [subtitles]
        assert reopened.subtitle_selection.file == subtitles
