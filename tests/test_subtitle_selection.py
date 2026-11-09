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
