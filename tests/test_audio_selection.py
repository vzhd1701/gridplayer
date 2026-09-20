"""One field says what a video's sound was chosen to be."""

import json
from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioExternal,
    AudioLanguage,
    AudioPreferred,
    AudioTrackId,
    track_of_file,
)
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video, default_audio_selection
from gridplayer.params.static import AudioTrackMode
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

    text = Playlist(videos=[video]).dumps()

    return Playlist.parse(text).videos[0]


class TestTheSixThingsSoundCanBe:
    @pytest.mark.parametrize(
        "selection",
        [
            AudioDefault(),
            AudioPreferred(),
            AudioDisabled(),
            AudioTrackId(id=7),
            AudioLanguage(tag="rus"),
            AudioExternal(file=Path("C:/films/Movie.rus.m4a").absolute()),
        ],
    )
    def test_each_survives_being_written_down_and_read_back(self, selection):
        assert _reopened(_video(audio_selection=selection)).audio_selection == selection

    def test_they_are_told_apart_by_what_they_say_they_are(self):
        written = json.loads(
            Playlist(videos=[_video(audio_selection=AudioTrackId(id=7))]).dumps()
        )

        assert written["videos"][0]["audio_selection"] == {"kind": "track", "id": 7}

    def test_two_of_the_same_choice_are_the_same_choice(self):
        assert AudioTrackId(id=7) == AudioTrackId(id=7)
        assert AudioTrackId(id=7) != AudioTrackId(id=8)
        assert AudioPreferred() != AudioDisabled()


class TestWhichTrackOfAFileWasChosen:
    """A file holding several is answered by place, since nothing else can."""

    def test_the_one_it_names(self):
        selection = AudioExternal(file=Path("C:/a.m4a"), track=1)

        assert track_of_file(selection, (7, 8)) == 8

    def test_the_first_where_it_names_one_the_file_no_longer_has(self):
        selection = AudioExternal(file=Path("C:/a.m4a"), track=3)

        assert track_of_file(selection, (7, 8)) == 7

    def test_none_at_all_where_the_file_brought_nothing(self):
        selection = AudioExternal(file=Path("C:/a.m4a"))

        assert track_of_file(selection, ()) is None


class TestOnlyOneOfThemAtATime:
    """The point of the field: the illegal states cannot be written down."""

    def test_a_new_choice_replaces_the_one_before_it(self):
        video = _video(audio_selection=AudioDisabled())

        video.audio_selection = AudioLanguage(tag="tlh")

        assert video.audio_selection == AudioLanguage(tag="tlh")

    def test_a_video_carries_no_second_place_to_look(self):
        fields = set(type(_video()).model_fields)

        assert "audio_selection" in fields
        assert not fields & {"audio_track_mode", "audio_track_id", "audio_language"}


class TestWhatTheDefaultsDecide:
    def test_a_new_video_follows_the_preference(self):
        Settings().set("video_defaults/audio_track_mode", AudioTrackMode.PREFERRED)

        assert _video().audio_selection == AudioPreferred()

    def test_a_new_video_can_start_with_no_sound_at_all(self):
        Settings().set("video_defaults/audio_track_mode", AudioTrackMode.DISABLED)

        assert _video().audio_selection == AudioDisabled()


class TestPlaylistsWrittenByOlderVersions:
    """Three keys used to say this between them; they still have to be read."""

    def test_a_disabled_video_stays_silent(self):
        video = Video(uri=URI, audio_track_mode="disabled", audio_track_id=-1)

        assert video.audio_selection == AudioDisabled()

    def test_a_pick_kept_by_language_is_read_as_one(self):
        video = Video(
            uri=URI,
            audio_track_mode="explicit",
            audio_language="rus",
            audio_track_id=3,
        )

        assert video.audio_selection == AudioLanguage(tag="rus")

    def test_a_pick_kept_by_id_is_read_as_one(self):
        video = Video(uri=URI, audio_track_mode="explicit", audio_track_id=3)

        assert video.audio_selection == AudioTrackId(id=3)

    def test_a_video_following_the_preference_keeps_following_it(self):
        """The id it happened to be playing was never the choice."""

        video = Video(uri=URI, audio_track_mode="preferred", audio_track_id=3)

        assert video.audio_selection == AudioPreferred()

    def test_a_disable_leaves_no_track_behind_to_be_mistaken_for_a_pick(self):
        video = Video(uri=URI, audio_track_mode="explicit", audio_track_id=-1)

        assert video.audio_selection == AudioPreferred()

    def test_a_playlist_older_than_any_of_them_takes_the_default(self):
        assert Video(uri=URI).audio_selection == default_audio_selection()

    def test_the_old_keys_are_not_written_out_again(self):
        video = Video(uri=URI, audio_track_mode="explicit", audio_track_id=3)

        assert not set(video.model_dump()) & {
            "audio_track_mode",
            "audio_track_id",
            "audio_language",
        }


class TestAChosenFileTravelsWithTheVideo:
    def test_it_is_written_beside_the_video_when_paths_are_relative(self, tmp_path):
        video_file = tmp_path / "videos" / "a.mp4"
        video_file.parent.mkdir()
        video_file.write_bytes(b"0")
        audio_file = video_file.with_suffix(".rus.m4a")
        audio_file.write_bytes(b"0")

        playlist = Playlist(
            videos=[
                Video(
                    uri=video_file,
                    external_audio=[audio_file],
                    audio_selection=AudioExternal(file=audio_file),
                )
            ],
            save_paths_relative=True,
        )

        text = playlist.dumps(base_dir=tmp_path)

        written = json.loads(text)["videos"][0]["audio_selection"]

        assert written == {
            "kind": "external",
            "file": "videos/a.rus.m4a",
            "track": 0,
        }
        assert str(tmp_path) not in text

    def test_it_is_found_again_where_the_playlist_was_opened(self, tmp_path):
        video_file = tmp_path / "videos" / "a.mp4"
        video_file.parent.mkdir()
        video_file.write_bytes(b"0")
        audio_file = video_file.with_suffix(".rus.m4a")
        audio_file.write_bytes(b"0")

        playlist = Playlist(
            videos=[
                Video(
                    uri=video_file,
                    external_audio=[audio_file],
                    audio_selection=AudioExternal(file=audio_file),
                )
            ],
            save_paths_relative=True,
        )

        reopened = Playlist.parse(playlist.dumps(base_dir=tmp_path), base_dir=tmp_path)

        assert reopened.videos[0].audio_selection == AudioExternal(file=audio_file)
