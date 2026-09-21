"""Showing a video with subtitles, its own and ones kept in files."""

import logging

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.subtitle_selection import (
    SubtitleDisabled,
    SubtitleExternal,
    SubtitleLanguage,
    SubtitleTrackId,
)
from gridplayer.models.video import Video
from gridplayer.params.static import VideoInitialState
from gridplayer.settings import Settings
from gridplayer.vlc_player.static import DISABLED_TRACK, SubtitleTrack
from gridplayer.widgets.video_block import VideoBlock


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _track(language=None):
    return SubtitleTrack(
        codec="Text subtitles with various tags",
        bitrate=0,
        language=language,
        description=None,
        encoding="UTF-8",
    )


def _file(tmp_path, name):
    file_path = tmp_path / name
    file_path.write_bytes(b"")

    return file_path


class _Driver:
    def __init__(self):
        self.slaves = []
        self.tracks_set = []
        self.times_set = []
        self.cur_subtitle_track_id = None
        self.external_subtitle_ids = ()
        self.default_subtitle_track_id = None

    def add_subtitle_slave(self, uri):
        self.slaves.append(uri)

    def set_subtitle_track(self, track_id):
        self.tracks_set.append(track_id)

    def set_time(self, seek_ms):
        self.times_set.append(seek_ms)


class _Block:
    """A block with the real subtitle methods, and no player behind it."""

    is_local_file = VideoBlock.is_local_file
    discovered_subtitle_files = VideoBlock.discovered_subtitle_files
    offered_subtitle_files = VideoBlock.offered_subtitle_files
    attached_subtitle_files = VideoBlock.attached_subtitle_files
    external_subtitle_track_ids = VideoBlock.external_subtitle_track_ids
    default_subtitle_track_id = VideoBlock.default_subtitle_track_id
    external_subtitle_tracks = VideoBlock.external_subtitle_tracks
    selected_subtitle_slave_uris = VideoBlock.selected_subtitle_slave_uris
    _subtitle_files_to_attach = VideoBlock._subtitle_files_to_attach
    _own_subtitles = VideoBlock._own_subtitles

    set_subtitle_track = VideoBlock.set_subtitle_track
    disable_subtitles = VideoBlock.disable_subtitles
    add_external_subtitles = VideoBlock.add_external_subtitles
    show_external_subtitle = VideoBlock.show_external_subtitle
    remove_external_subtitles = VideoBlock.remove_external_subtitles
    set_external_subtitle_autodiscover = VideoBlock.set_external_subtitle_autodiscover
    restore_subtitle_selection = VideoBlock.restore_subtitle_selection
    subtitle_file_name = VideoBlock.subtitle_file_name
    external_subtitle_track_name = VideoBlock.external_subtitle_track_name
    subtitle_language_key = VideoBlock.subtitle_language_key
    subtitle_number_in_file = VideoBlock.subtitle_number_in_file

    _subtitle_selection_for = VideoBlock._subtitle_selection_for
    _forget_subtitle_files_that_are_gone = (
        VideoBlock._forget_subtitle_files_that_are_gone
    )
    _wanted_subtitle_track_id = VideoBlock._wanted_subtitle_track_id
    _apply_wanted_subtitle_track = VideoBlock._apply_wanted_subtitle_track
    _put_external_subtitles_into_effect = VideoBlock._put_external_subtitles_into_effect
    _nudge_subtitles_into_view = VideoBlock._nudge_subtitles_into_view

    def __init__(
        self,
        video_path,
        tracks=None,
        is_initialized=True,
        autodiscover=True,
        is_paused=False,
    ):
        self._log = logging.getLogger("test-block")

        self.video_params = Video(uri=video_path)
        self.video_params.is_external_subtitle_autodiscover = autodiscover
        self.video_params.playback_state = (
            VideoInitialState.PAUSED if is_paused else VideoInitialState.PLAYING
        )

        self.is_video_initialized = is_initialized
        self.subtitle_tracks = {0: _track("eng")} if tracks is None else tracks

        self.video_driver = _Driver()

        self.is_live = False
        self.time = 4200

        self._attached_subtitle_files = []

        self.reloads = 0

    def reload(self):
        self.reloads += 1


def _block(tmp_path, **kwargs):
    return _Block(_file(tmp_path, "Movie.mkv"), **kwargs)


def _attached(block, file_path, track_id, language=None):
    """The state a block is in once a file has been opened with it."""

    block.video_params.external_subtitles = [
        *block.video_params.external_subtitles,
        file_path,
    ]
    block._attached_subtitle_files = [*block._attached_subtitle_files, file_path]
    block.subtitle_tracks = {
        **block.subtitle_tracks,
        track_id: _track(language or str(file_path.with_suffix(""))),
    }
    block.video_driver.external_subtitle_ids = (
        *block.video_driver.external_subtitle_ids,
        track_id,
    )


class TestRememberingWhichSubtitleWasPicked:
    def test_switching_them_off_is_remembered_as_off(self, tmp_path):
        block = _block(tmp_path)

        block.disable_subtitles()

        assert block.video_params.subtitle_selection == SubtitleDisabled()
        assert block.video_driver.tracks_set == [DISABLED_TRACK]

    def test_a_track_with_a_language_of_its_own_is_remembered_by_it(self, tmp_path):
        block = _block(tmp_path, tracks={0: _track("eng"), 1: _track("jpn")})

        block.set_subtitle_track(1)

        assert block.video_params.subtitle_selection == SubtitleLanguage(tag="jpn")

    def test_one_of_two_in_the_same_language_is_remembered_by_number(self, tmp_path):
        """A language that picks out two tracks picks out neither."""

        block = _block(tmp_path, tracks={0: _track("eng"), 1: _track("eng")})

        block.set_subtitle_track(1)

        assert block.video_params.subtitle_selection == SubtitleTrackId(id=1)

    def test_a_track_with_no_language_is_remembered_by_number(self, tmp_path):
        block = _block(tmp_path, tracks={0: _track(None), 1: _track(None)})

        block.set_subtitle_track(1)

        assert block.video_params.subtitle_selection == SubtitleTrackId(id=1)

    def test_a_track_out_of_a_file_is_remembered_by_the_file(self, tmp_path):
        block = _block(tmp_path)
        subtitles = _file(tmp_path, "Movie.ja.srt")

        _attached(block, subtitles, track_id=1)

        block.set_subtitle_track(1)

        selection = block.video_params.subtitle_selection

        assert selection == SubtitleExternal(file=subtitles, track=0)

    def test_a_file_is_never_remembered_by_the_language_libvlc_invented(self, tmp_path):
        """libVLC writes the file's own name where a language belongs."""

        block = _block(tmp_path)
        subtitles = _file(tmp_path, "Movie.ja.srt")

        _attached(block, subtitles, track_id=1)

        assert block.subtitle_language_key(1) is None


class TestFilesKeptBesideTheVideo:
    def test_the_ones_named_after_it_are_offered(self, tmp_path):
        block = _block(tmp_path)
        _file(tmp_path, "Movie.en.srt")

        assert [path.name for path in block.offered_subtitle_files] == ["Movie.en.srt"]

    def test_nothing_is_offered_where_looking_was_turned_off(self, tmp_path):
        block = _block(tmp_path, autodiscover=False)
        _file(tmp_path, "Movie.en.srt")

        assert block.offered_subtitle_files == []

    def test_picking_one_hands_it_over_without_a_reload(self, tmp_path):
        """Which is what sets this apart from an audio file."""

        block = _block(tmp_path)
        block._attached_subtitle_files = []
        subtitles = _file(tmp_path, "Movie.en.srt")

        block.show_external_subtitle(str(subtitles))

        assert block.video_driver.slaves == [subtitles.as_uri()]
        assert block.reloads == 0

    def test_picking_one_is_what_chooses_it(self, tmp_path):
        block = _block(tmp_path)
        block._attached_subtitle_files = []
        subtitles = _file(tmp_path, "Movie.en.srt")

        block.show_external_subtitle(str(subtitles))

        assert block.video_params.subtitle_selection == SubtitleExternal(
            file=subtitles, track=0
        )

    def test_one_already_on_is_only_switched_back_to(self, tmp_path):
        block = _block(tmp_path)
        subtitles = _file(tmp_path, "Movie.en.srt")

        _attached(block, subtitles, track_id=1)
        block.video_driver.slaves.clear()

        block.show_external_subtitle(str(subtitles))

        assert block.video_driver.slaves == []
        assert block.video_driver.tracks_set == [1]

    def test_taking_them_away_costs_a_reload(self, tmp_path):
        """libVLC has no way to give a file back."""

        block = _block(tmp_path)
        subtitles = _file(tmp_path, "Movie.en.srt")

        _attached(block, subtitles, track_id=1)
        block.video_params.subtitle_selection = SubtitleExternal(file=subtitles)

        block.remove_external_subtitles()

        assert block.reloads == 1
        assert block.video_params.external_subtitles == []
        assert block.video_params.subtitle_selection == SubtitleDisabled()

    def test_a_file_that_is_gone_is_let_go_of(self, tmp_path):
        block = _block(tmp_path)
        subtitles = tmp_path / "Moved.srt"

        block.video_params.external_subtitles = [subtitles]
        block.video_params.subtitle_selection = SubtitleExternal(file=subtitles)

        block._forget_subtitle_files_that_are_gone()

        assert block.video_params.subtitle_selection == SubtitleDisabled()
        # the file keeps its place, in case whatever moved it moves it back
        assert block.video_params.external_subtitles == [subtitles]

    def test_which_file_a_track_came_from_is_read_off_its_name(self, tmp_path):
        block = _block(tmp_path)

        first = _file(tmp_path, "Movie.en.srt")
        second = _file(tmp_path, "Movie.ja.srt")

        # libVLC hands them back in the order they were attached, naming
        # each after its own file -- but with the names crossed over here,
        # to show the name is what is being read rather than the order
        _attached(block, first, track_id=1, language="C:\\films\\Movie.ja")
        _attached(block, second, track_id=2, language="C:\\films\\Movie.en")

        assert block.external_subtitle_tracks == {1: second, 2: first}

    def test_one_file_can_bring_several_tracks(self, tmp_path):
        """A VobSub index off a DVD routinely carries a dozen languages."""

        block = _block(tmp_path)
        vobsub = _file(tmp_path, "Movie.idx")

        _attached(block, vobsub, track_id=1, language="en")
        _attached(block, vobsub, track_id=2, language="de")

        assert block.external_subtitle_tracks == {1: vobsub, 2: vobsub}
        assert block.subtitle_number_in_file(1, vobsub) == 0
        assert block.subtitle_number_in_file(2, vobsub) == 1

    def test_which_of_them_was_picked_is_part_of_the_choice(self, tmp_path):
        """Or the video comes back on the first of them after every reload."""

        block = _block(tmp_path)
        vobsub = _file(tmp_path, "Movie.idx")

        _attached(block, vobsub, track_id=1, language="en")
        _attached(block, vobsub, track_id=2, language="de")

        block.set_subtitle_track(2)

        assert block.video_params.subtitle_selection == SubtitleExternal(
            file=vobsub, track=1
        )

    def test_a_track_of_such_a_file_is_named_by_its_language(self, tmp_path):
        block = _block(tmp_path)
        vobsub = _file(tmp_path, "Movie.idx")

        _attached(block, vobsub, track_id=1, language="de")

        assert block.external_subtitle_track_name(1) == "German"

    def test_a_file_with_one_track_says_nothing_beyond_its_own_name(self, tmp_path):
        """libVLC puts the file's name where the language belongs."""

        block = _block(tmp_path)
        subtitles = _file(tmp_path, "Movie.en.srt")

        _attached(block, subtitles, track_id=1)

        assert block.external_subtitle_track_name(1) is None

    def test_a_name_that_answers_to_nothing_falls_back_on_the_order(self, tmp_path):
        block = _block(tmp_path)

        first = _file(tmp_path, "Movie.en.srt")
        second = _file(tmp_path, "Movie.ja.srt")

        _attached(block, first, track_id=1, language="something else")
        _attached(block, second, track_id=2, language="something else again")

        assert block.external_subtitle_tracks == {1: first, 2: second}


class TestPuttingTheSettingsIntoEffect:
    def test_a_video_part_way_through_a_load_settles_it_itself(self, tmp_path):
        block = _block(tmp_path, is_initialized=False)

        block.set_subtitle_track(1)

        assert block.video_driver.tracks_set == []
        assert block.video_params.subtitle_selection == SubtitleTrackId(id=1)

    @pytest.mark.parametrize("is_paused", [True, False])
    def test_the_line_already_on_screen_is_put_through_again(self, tmp_path, is_paused):
        """Or a track switched to mid-line shows nothing until the next one.

        Playing or paused makes no difference: VLC draws a subtitle as the
        packet carrying it goes past, and for the line already up that
        packet went past while another track was selected.
        """

        block = _block(tmp_path, is_paused=is_paused)

        block.set_subtitle_track(0)

        assert block.video_driver.times_set == [4200]

    def test_a_live_stream_has_nothing_to_seek_in(self, tmp_path):
        block = _block(tmp_path)
        block.is_live = True

        block.set_subtitle_track(0)

        assert block.video_driver.times_set == []
