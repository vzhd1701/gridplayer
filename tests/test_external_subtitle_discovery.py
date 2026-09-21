"""Finding the subtitle files kept beside a video, and naming them."""

import pytest

from gridplayer.utils.external_subtitles import (
    MAX_DISCOVERED,
    discover_subtitle_files,
    subtitle_file_label,
    subtitle_language_tag,
)


def _make(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_text("1\n", encoding="utf-8")

    return tmp_path / "Movie.mkv"


def _found(video_path):
    return [path.name for path in discover_subtitle_files(video_path)]


class TestWhatCountsAsNamedAfterTheVideo:
    def test_the_bare_name(self, tmp_path):
        video = _make(tmp_path, "Movie.mkv", "Movie.srt")

        assert _found(video) == ["Movie.srt"]

    @pytest.mark.parametrize("added", ["Movie.en.srt", "Movie-en.srt", "Movie_en.srt"])
    def test_whatever_a_language_was_added_with(self, tmp_path, added):
        video = _make(tmp_path, "Movie.mkv", added)

        assert _found(video) == [added]

    def test_a_name_that_only_begins_the_same_way_is_a_different_name(self, tmp_path):
        video = _make(tmp_path, "Movie.mkv", "Movies Vol 2.srt")

        assert _found(video) == []

    def test_the_video_is_never_offered_as_its_own_subtitle(self, tmp_path):
        video = _make(tmp_path, "Movie.mkv")

        assert _found(video) == []

    def test_a_file_of_a_kind_vlc_cannot_read_is_passed_over(self, tmp_path):
        video = _make(tmp_path, "Movie.mkv", "Movie.nfo", "Movie.srt")

        assert _found(video) == ["Movie.srt"]

    def test_they_come_back_in_the_same_order_every_time(self, tmp_path):
        video = _make(tmp_path, "Movie.mkv", "Movie.fr.srt", "Movie.en.srt")

        assert _found(video) == ["Movie.en.srt", "Movie.fr.srt"]

    def test_a_folder_of_loose_text_files_does_not_flood_the_menu(self, tmp_path):
        names = [f"Movie.{index:03d}.srt" for index in range(MAX_DISCOVERED + 10)]

        video = _make(tmp_path, "Movie.mkv", *names)

        assert len(_found(video)) == MAX_DISCOVERED

    def test_a_folder_that_cannot_be_read_is_not_a_fault(self, tmp_path):
        assert discover_subtitle_files(tmp_path / "gone" / "Movie.mkv") == []


class TestVobSubPairs:
    """The .idx carries the timings and the .sub the pictures.

    VLC has to be handed the .idx, so offering both would put a row in the
    menu that shows nothing at all.
    """

    def test_only_the_index_of_a_pair_is_offered(self, tmp_path):
        video = _make(tmp_path, "Movie.mkv", "Movie.idx", "Movie.sub")

        assert _found(video) == ["Movie.idx"]

    def test_a_sub_with_no_index_beside_it_is_offered_on_its_own(self, tmp_path):
        """Which is a MicroDVD subtitle, and VLC reads those directly."""

        video = _make(tmp_path, "Movie.mkv", "Movie.sub")

        assert _found(video) == ["Movie.sub"]


class TestWhatToCallThemInTheMenu:
    def test_a_language_added_to_the_video_name_is_read_off_it(self, tmp_path):
        video = tmp_path / "Movie.mkv"

        assert subtitle_file_label(tmp_path / "Movie.en.srt", video) == "English"

    def test_a_three_letter_code_reads_the_same_way(self, tmp_path):
        video = tmp_path / "Movie.mkv"

        assert subtitle_file_label(tmp_path / "Movie.jpn.srt", video) == "Japanese"

    def test_what_was_added_but_names_no_language_keeps_the_file_name(self, tmp_path):
        video = tmp_path / "Movie.mkv"

        assert (
            subtitle_file_label(tmp_path / "Movie.forced.srt", video)
            == "Movie.forced.srt"
        )

    def test_a_file_named_nothing_like_the_video_keeps_its_name(self, tmp_path):
        video = tmp_path / "Movie.mkv"

        assert subtitle_file_label(tmp_path / "Whatever.srt", video) == "Whatever.srt"

    def test_a_video_that_is_not_a_file_leaves_the_name_alone(self, tmp_path):
        assert subtitle_file_label(tmp_path / "Movie.en.srt") == "Movie.en.srt"

    def test_the_language_leads_whatever_follows_it(self, tmp_path):
        video = tmp_path / "Movie.mkv"

        assert subtitle_language_tag(tmp_path / "Movie.en.forced.srt", video) == "en"
