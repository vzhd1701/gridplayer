"""Finding the audio files someone left beside a video."""

from gridplayer.utils.external_audio import (
    MAX_DISCOVERED,
    discover_audio_files,
    silenced_by_seeking,
    unplayable_as_audio_slave,
)


def _folder(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_bytes(b"")

    return tmp_path


def _found(tmp_path, video_name="Movie.mkv"):
    return [found.name for found in discover_audio_files(tmp_path / video_name)]


def test_a_file_named_after_the_video_is_found(tmp_path):
    _folder(tmp_path, "Movie.mkv", "Movie.mp3")

    assert _found(tmp_path) == ["Movie.mp3"]


def test_what_a_dub_adds_to_the_name_it_adds_to_the_end(tmp_path):
    _folder(tmp_path, "Movie.mkv", "Movie.rus.ac3", "Movie - Commentary.flac")

    assert _found(tmp_path) == ["Movie - Commentary.flac", "Movie.rus.ac3"]


def test_a_name_that_only_begins_the_same_way_is_a_different_name(tmp_path):
    _folder(tmp_path, "Movie.mkv", "Movies Vol 2.mp3", "Movie2.mp3")

    assert _found(tmp_path) == []


def test_something_else_in_the_folder_is_nothing_to_do_with_it(tmp_path):
    _folder(tmp_path, "Movie.mkv", "Soundtrack.mp3")

    assert _found(tmp_path) == []


def test_only_audio_is_offered(tmp_path):
    _folder(tmp_path, "Movie.mkv", "Movie.srt", "Movie.nfo", "Movie.rus.mp4")

    assert _found(tmp_path) == []


def test_a_video_that_is_audio_does_not_find_itself(tmp_path):
    _folder(tmp_path, "Movie.mp3", "Movie.rus.mp3")

    assert _found(tmp_path, "Movie.mp3") == ["Movie.rus.mp3"]


def test_case_does_not_decide_whether_a_file_belongs(tmp_path):
    _folder(tmp_path, "Movie.mkv", "movie.ENG.FLAC")

    assert _found(tmp_path) == ["movie.ENG.FLAC"]


def test_a_folder_named_like_an_audio_file_is_not_one(tmp_path):
    _folder(tmp_path, "Movie.mkv")
    (tmp_path / "Movie.mp3").mkdir()

    assert _found(tmp_path) == []


def test_a_folder_that_cannot_be_read_offers_nothing(tmp_path):
    assert discover_audio_files(tmp_path / "gone" / "Movie.mkv") == []


def test_no_more_than_a_handful_are_offered(tmp_path):
    """A video dropped into a music folder must not offer all of it."""

    _folder(
        tmp_path,
        "Movie.mkv",
        *[f"Movie.{index:02}.mp3" for index in range(MAX_DISCOVERED * 2)],
    )

    assert len(_found(tmp_path)) == MAX_DISCOVERED


def test_the_order_is_by_name_whatever_order_they_arrived_in(tmp_path):
    """The order is what the tracks are identified by, so it has to hold."""

    _folder(tmp_path, "Movie.mkv", "Movie.c.mp3", "Movie.a.mp3", "Movie.B.mp3")

    assert _found(tmp_path) == ["Movie.a.mp3", "Movie.B.mp3", "Movie.c.mp3"]


class TestWhatLibvlcCanKeepUpWith:
    """Measured against the VLC the app ships with; see external_audio.py."""

    def test_the_ordinary_formats_play_through(self, tmp_path):
        files = [tmp_path / f"Movie.{ext}" for ext in ("mp3", "m4a", "flac", "ac3")]

        assert unplayable_as_audio_slave(files) == []
        assert silenced_by_seeking(files) == []

    def test_matroska_and_opus_never_make_a_sound(self, tmp_path):
        files = [tmp_path / "Movie.mka", tmp_path / "Movie.opus"]

        assert unplayable_as_audio_slave(files) == files

    def test_ogg_plays_until_the_video_is_seeked(self, tmp_path):
        files = [tmp_path / "Movie.ogg", tmp_path / "Movie.oga"]

        assert silenced_by_seeking(files) == files
        assert unplayable_as_audio_slave(files) == []

    def test_the_extension_is_read_whatever_its_case(self, tmp_path):
        assert unplayable_as_audio_slave([tmp_path / "Movie.OPUS"])
