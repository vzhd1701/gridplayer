"""Playing a video with audio that was kept in a file of its own."""

import logging
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioExternal,
    AudioTrackId,
)
from gridplayer.models.video import Video
from gridplayer.settings import Settings
from gridplayer.vlc_player.static import AudioTrack
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
    return AudioTrack(
        codec="mp4a",
        bitrate=131072,
        language=language,
        description=None,
        channels=2,
        rate=48000,
    )


def _file(tmp_path, name):
    file_path = tmp_path / name
    file_path.write_bytes(b"")

    return file_path


class _Driver:
    def __init__(self):
        self.slaves = []
        self.tracks_set = []
        self.cur_audio_track_id = None
        self.external_audio_ids = ()
        self.default_audio_track_id = None

    def add_audio_slave(self, uri):
        self.slaves.append(uri)

    def set_audio_track(self, track_id):
        self.tracks_set.append(track_id)


class _Block:
    """A block with the real external audio methods, and no player behind it."""

    is_local_file = VideoBlock.is_local_file
    discovered_audio_files = VideoBlock.discovered_audio_files
    offered_audio_files = VideoBlock.offered_audio_files
    attached_audio_file = VideoBlock.attached_audio_file
    _audio_file_to_attach = VideoBlock._audio_file_to_attach
    external_audio_track_ids = VideoBlock.external_audio_track_ids
    default_audio_track_id = VideoBlock.default_audio_track_id
    external_audio_tracks = VideoBlock.external_audio_tracks
    selected_audio_slave_uri = VideoBlock.selected_audio_slave_uri

    add_external_audio = VideoBlock.add_external_audio
    play_external_audio = VideoBlock.play_external_audio
    remove_external_audio = VideoBlock.remove_external_audio
    set_external_audio_autodiscover = VideoBlock.set_external_audio_autodiscover
    tracks_changed = VideoBlock.tracks_changed
    apply_audio_default = VideoBlock.apply_audio_default
    restore_audio_selection = VideoBlock.restore_audio_selection

    _audio_selection_for = VideoBlock._audio_selection_for
    _forget_audio_file_that_is_gone = VideoBlock._forget_audio_file_that_is_gone
    _wanted_audio_track_id = VideoBlock._wanted_audio_track_id
    _apply_wanted_audio_track = VideoBlock._apply_wanted_audio_track
    _put_external_audio_into_effect = VideoBlock._put_external_audio_into_effect
    _is_external_audio_short = VideoBlock._is_external_audio_short
    _adopt_audio_if_silent = VideoBlock._adopt_audio_if_silent
    _warn_about_awkward_audio = VideoBlock._warn_about_awkward_audio

    def __init__(
        self,
        video_path,
        tracks=None,
        is_initialized=True,
        autodiscover=True,
        external_id=None,
    ):
        self._log = logging.getLogger("test-block")

        self.video_params = Video(uri=video_path)
        self.video_params.is_external_audio_autodiscover = autodiscover

        self.is_video_initialized = is_initialized
        self.audio_tracks = {0: _track("eng")} if tracks is None else tracks

        self.video_driver = _Driver()
        self.video_driver.external_audio_ids = (
            () if external_id is None else (external_id,)
        )

        self.audio_present = []
        self.is_audio_present_change = SimpleNamespace(emit=self.audio_present.append)

        self.reloads = 0
        self.selected = []
        self._attached_audio_file = None

        self.warnings = []
        self._ctx = SimpleNamespace(
            commands=SimpleNamespace(warning=self.warnings.append)
        )

    def reload(self):
        self.reloads += 1

    def set_audio_track(self, track_id):
        self.selected.append(track_id)


def _block(tmp_path, **kwargs):
    return _Block(_file(tmp_path, "Movie.mkv"), **kwargs)


def _attached(block, file_path, track_id=1):
    """The state a block is in once a file of its own has been opened with it."""

    block.video_params.external_audio = [
        *block.video_params.external_audio,
        file_path,
    ]
    block.video_params.audio_selection = AudioExternal(file=file_path)
    block._attached_audio_file = file_path
    block.video_driver.external_audio_ids = (track_id,)

    return block


def _offered(block):
    return [found.name for found in block.offered_audio_files]


class TestPickingAFile:
    def test_it_goes_on_the_player_where_it_stands(self, tmp_path):
        block = _block(tmp_path)
        audio = _file(tmp_path, "Movie.rus.mp3")

        block.add_external_audio([audio])

        assert block.video_driver.slaves == [audio.as_uri()]
        assert block.reloads == 0

    def test_it_is_remembered_by_its_name_rather_than_a_track_id(self, tmp_path):
        """The file keeps its name whatever the tracks do around it."""

        block = _block(tmp_path)
        audio = _file(tmp_path, "Movie.rus.mp3")

        block.add_external_audio([audio])

        assert block.video_params.audio_selection == AudioExternal(file=audio)

    def test_one_picked_mid_load_waits_for_the_video(self, tmp_path):
        block = _block(tmp_path, is_initialized=False)
        audio = _file(tmp_path, "Movie.rus.mp3")

        block.add_external_audio([audio])

        assert block.video_driver.slaves == []
        assert block.video_params.external_audio == [audio]

    def test_the_same_file_is_not_taken_twice(self, tmp_path):
        block = _block(tmp_path)
        audio = _file(tmp_path, "Movie.rus.mp3")

        block.add_external_audio([audio])
        block.add_external_audio([audio])

        assert block.video_params.external_audio == [audio]
        assert len(block.video_driver.slaves) == 1

    def test_several_at_once_are_kept_but_only_the_first_is_played(self, tmp_path):
        """One goes to libVLC; the rest are there to be picked from."""

        block = _block(tmp_path)
        first = _file(tmp_path, "Movie.rus.mp3")
        second = _file(tmp_path, "Movie.fra.mp3")

        block.add_external_audio([first, second])

        assert block.video_params.external_audio == [first, second]
        assert block.video_driver.slaves == [first.as_uri()]

    def test_the_one_already_playing_is_only_switched_back_to(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))

        block.play_external_audio(str(block.attached_audio_file))

        assert block.selected == [1]
        assert block.video_driver.slaves == []
        assert block.reloads == 0


class TestSwappingOneFileForAnother:
    """libVLC will not take a file back, and cannot tell two of them apart."""

    def test_the_video_is_loaded_again_rather_than_handed_a_second(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))
        other = _file(tmp_path, "Movie.fra.mp3")

        block.play_external_audio(str(other))

        assert block.reloads == 1
        assert block.video_driver.slaves == []

    def test_the_new_file_is_what_the_video_comes_back_on(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))
        other = _file(tmp_path, "Movie.fra.mp3")

        block.play_external_audio(str(other))

        assert block.video_params.audio_selection == AudioExternal(file=other)

    def test_a_file_that_is_not_on_the_list_yet_joins_it(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))
        other = _file(tmp_path, "Movie.fra.mp3")

        block.play_external_audio(str(other))

        assert other in block.video_params.external_audio

    def test_a_video_with_none_attached_is_handed_one_where_it_stands(self, tmp_path):
        block = _block(tmp_path)
        audio = _file(tmp_path, "Movie.rus.mp3")
        block.video_params.external_audio = [audio]

        block.play_external_audio(str(audio))

        assert block.video_driver.slaves == [audio.as_uri()]
        assert block.reloads == 0


class TestWhatIsOffered:
    def test_a_file_beside_the_video_is_offered(self, tmp_path):
        block = _block(tmp_path)
        _file(tmp_path, "Movie.rus.mp3")

        assert _offered(block) == ["Movie.rus.mp3"]

    def test_the_one_playing_is_not_offered_again(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))
        _file(tmp_path, "Movie.eng.mp3")

        assert _offered(block) == ["Movie.eng.mp3"]

    def test_one_taken_but_not_playing_is_still_offered(self, tmp_path):
        """The list is a shortlist; only one of them is ever attached."""

        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))
        other = _file(tmp_path, "Movie.fra.mp3")
        block.video_params.external_audio = [*block.video_params.external_audio, other]

        assert _offered(block) == ["Movie.fra.mp3"]

    def test_a_video_from_the_network_has_no_folder_to_look_in(self, tmp_path):
        block = _Block("http://example.com/Movie.mkv")
        _file(tmp_path, "Movie.rus.mp3")

        assert _offered(block) == []

    def test_nothing_is_offered_where_the_detection_is_off(self, tmp_path):
        block = _block(tmp_path, autodiscover=False)
        _file(tmp_path, "Movie.rus.mp3")

        assert _offered(block) == []


class TestWhichFileTheTrackCameFrom:
    """One file is attached at a time, so its track is unmistakable."""

    def test_the_track_belongs_to_the_file_that_is_playing(self, tmp_path):
        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _attached(
            _block(tmp_path, tracks={0: _track("eng"), 1: _track()}), audio
        )

        assert block.external_audio_tracks == {1: audio}

    def test_a_video_with_no_file_has_none_of_them(self, tmp_path):
        block = _block(tmp_path)

        assert block.external_audio_tracks == {}

    def test_a_file_that_brought_no_track_claims_none(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))
        block.video_driver.external_audio_ids = ()

        assert block.external_audio_tracks == {}


class TestHandingItToThePlayer:
    def test_the_file_being_listened_to_is_the_one_handed_over(self, tmp_path):
        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _attached(_block(tmp_path), audio)
        block.video_params.external_audio.append(_file(tmp_path, "Movie.fra.mp3"))

        assert block.selected_audio_slave_uri == audio.as_uri()

    def test_a_video_playing_its_own_sound_hands_over_nothing(self, tmp_path):
        block = _block(tmp_path)
        block.video_params.external_audio = [_file(tmp_path, "Movie.rus.mp3")]

        assert block.selected_audio_slave_uri is None


class TestTakingThemBack:
    def test_the_video_is_loaded_again_without_them(self, tmp_path):
        """libVLC has no way to hand back a file it has been given."""

        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))

        block.remove_external_audio()

        assert block.video_params.external_audio == []
        assert block.reloads == 1

    def test_a_video_with_none_of_them_is_left_alone(self, tmp_path):
        block = _block(tmp_path)

        block.remove_external_audio()

        assert block.reloads == 0

    def test_the_pick_goes_back_to_the_preference_with_the_track(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))

        block.remove_external_audio()

        assert block.video_params.audio_selection == AudioDefault()

    def test_a_pick_of_the_video_s_own_track_is_kept(self, tmp_path):
        block = _block(tmp_path, tracks={0: _track("eng"), 1: _track()})
        block.video_params.external_audio = [_file(tmp_path, "Movie.rus.mp3")]
        block.video_params.audio_selection = AudioTrackId(id=0)

        block.remove_external_audio()

        assert block.video_params.audio_selection == AudioTrackId(id=0)


class TestAVideoWithNoSoundOfItsOwn:
    def test_it_takes_the_one_file_found_beside_it(self, tmp_path):
        block = _block(tmp_path, tracks={})
        audio = _file(tmp_path, "Movie.mp3")

        block._adopt_audio_if_silent()

        assert block.video_params.external_audio == [audio]

    def test_several_are_left_to_be_asked_about(self, tmp_path):
        """Which of them to play is nobody's guess but the viewer's."""

        block = _block(tmp_path, tracks={})
        _file(tmp_path, "Movie.rus.mp3")
        _file(tmp_path, "Movie.eng.mp3")

        block._adopt_audio_if_silent()

        assert block.video_params.external_audio == []

    def test_a_video_that_has_sound_is_left_alone(self, tmp_path):
        block = _block(tmp_path)
        _file(tmp_path, "Movie.mp3")

        block._adopt_audio_if_silent()

        assert block.video_params.external_audio == []

    def test_one_that_was_given_a_file_already_is_left_alone(self, tmp_path):
        block = _block(tmp_path, tracks={})
        picked = _file(tmp_path, "Movie.rus.mp3")
        block.video_params.external_audio = [picked]
        _file(tmp_path, "Movie.eng.mp3")

        block._adopt_audio_if_silent()

        assert block.video_params.external_audio == [picked]


class TestATrackThatArrivesAfterTheLoad:
    def test_the_choice_is_left_as_it_was(self, tmp_path):
        """What is playing is the player's business, not the choice's.

        Writing it back here is what would turn "go by my languages" into
        "play track three" behind the viewer's back.
        """

        block = _block(tmp_path, tracks={0: _track("eng"), 1: _track()})
        block.video_driver.cur_audio_track_id = 1
        before = block.video_params.audio_selection

        block.tracks_changed()

        assert block.video_params.audio_selection == before
        assert block.reloads == 0

    def test_a_file_that_brought_nothing_is_loaded_with_the_video(self, tmp_path):
        """Some formats only open as part of a video, not alongside one."""

        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.ogg"))
        block.video_driver.external_audio_ids = ()

        block.tracks_changed()

        assert block.reloads == 1

    def test_one_that_brought_its_track_is_left_where_it_is(self, tmp_path):
        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))

        block.tracks_changed()

        assert block.reloads == 0

    def test_a_silent_video_is_no_longer_silent(self, tmp_path):
        block = _block(tmp_path, tracks={0: _track()})

        block.tracks_changed()

        assert block.audio_present == [True]


class TestLeavingItToTheVideosOwnFile:
    def test_the_track_the_file_puts_forward_is_played(self, tmp_path):
        block = _block(tmp_path, tracks={0: _track("eng"), 1: _track("jpn")})
        block.video_driver.default_audio_track_id = 1
        block.video_params.audio_selection = AudioTrackId(id=0)

        block.apply_audio_default()

        assert block.video_params.audio_selection == AudioDefault()
        assert block.video_driver.tracks_set == [1]

    def test_where_libvlc_never_said_the_first_of_its_own_is_taken(self, tmp_path):
        """As close to what it would have played alone as this gets."""

        block = _block(tmp_path, tracks={3: _track("eng"), 4: _track("jpn")})
        block.video_driver.default_audio_track_id = None

        block.apply_audio_default()

        assert block.video_driver.tracks_set == [3]

    def test_a_track_out_of_a_file_is_never_what_it_falls_back_on(self, tmp_path):
        """The file took the sound at load; it is not the video's own choice."""

        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _attached(
            _block(tmp_path, tracks={0: _track("eng"), 1: _track()}), audio
        )
        # what libVLC opened on was the file, as it does once its stream is in
        block.video_driver.default_audio_track_id = 1

        block.apply_audio_default()

        assert block.video_driver.tracks_set == [0]


class TestAFileLibvlcWillNotKeepUpWith:
    """Measured against the VLC the app ships with; see external_audio.py."""

    def test_one_that_never_makes_a_sound_is_called_out(self, tmp_path):
        block = _block(tmp_path)

        block.add_external_audio([_file(tmp_path, "Movie.opus")])

        assert "Movie.opus" in block.warnings[0]
        assert "MP3" in block.warnings[0]

    def test_one_that_stops_at_the_first_seek_is_called_out(self, tmp_path):
        block = _block(tmp_path)

        block.add_external_audio([_file(tmp_path, "Movie.ogg")])

        assert "seeked" in block.warnings[0]

    def test_it_is_taken_all_the_same(self, tmp_path):
        """One build of VLC is not every build, and it is their file."""

        block = _block(tmp_path)
        audio = _file(tmp_path, "Movie.opus")

        block.add_external_audio([audio])

        assert block.video_params.external_audio == [audio]

    def test_a_format_that_plays_is_not_complained_about(self, tmp_path):
        block = _block(tmp_path)

        block.add_external_audio([_file(tmp_path, "Movie.m4a")])

        assert block.warnings == []


class TestAFileThatIsNoLongerThere:
    """A playlist outlives the folder it was saved from."""

    def test_it_is_not_handed_to_the_player(self, tmp_path):
        block = _block(tmp_path)
        gone = tmp_path / "gone.mp3"
        block.video_params.external_audio = [gone]
        block.video_params.audio_selection = AudioExternal(file=gone)

        assert block.selected_audio_slave_uri is None
        assert block.attached_audio_file is None

    def test_it_is_kept_in_the_playlist_all_the_same(self, tmp_path):
        """Whatever moved it may move it back."""

        block = _block(tmp_path)
        gone = tmp_path / "gone.mp3"
        block.video_params.external_audio = [gone]

        assert block.video_params.external_audio == [gone]

    def test_it_is_no_reason_to_load_the_video_again(self, tmp_path):
        block = _block(tmp_path)
        gone = tmp_path / "gone.mp3"
        block.video_params.external_audio = [gone]
        block.video_params.audio_selection = AudioExternal(file=gone)

        block.tracks_changed()

        assert block.reloads == 0


class TestGoingBackToTheVideosOwnSound:
    """libVLC keeps the file until the next load, whatever is being played."""

    def test_the_file_s_track_keeps_its_name(self, tmp_path):
        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _attached(
            _block(tmp_path, tracks={0: _track("eng"), 1: _track()}), audio
        )

        block.video_params.audio_selection = AudioTrackId(id=0)

        assert block.external_audio_tracks == {1: audio}

    def test_it_is_not_offered_again_below(self, tmp_path):
        """It is in the track list already; offering it twice reads as two files."""

        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _attached(_block(tmp_path), audio)

        block.video_params.audio_selection = AudioTrackId(id=0)

        assert _offered(block) == []

    def test_the_next_load_opens_without_it(self, tmp_path):
        """What is chosen is what a fresh load is handed, not what is on now."""

        block = _attached(_block(tmp_path), _file(tmp_path, "Movie.rus.mp3"))

        block.video_params.audio_selection = AudioTrackId(id=0)

        assert block.selected_audio_slave_uri is None

    def test_picking_it_again_needs_no_reload(self, tmp_path):
        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _attached(_block(tmp_path), audio)
        block.video_params.audio_selection = AudioTrackId(id=0)

        block.play_external_audio(str(audio))

        assert block.selected == [1]
        assert block.reloads == 0

    def test_the_pick_falls_back_to_what_the_video_would_open_on(self, tmp_path):
        """Nothing named and nothing ticked reads as a menu with a hole in it."""

        block = _block(tmp_path)
        gone = tmp_path / "gone.mp3"
        block.video_params.external_audio = [gone]
        block.video_params.audio_selection = AudioExternal(file=gone)

        block._forget_audio_file_that_is_gone()

        assert block.video_params.audio_selection == AudioDefault()

    def test_the_file_keeps_its_place_in_the_list(self, tmp_path):
        block = _block(tmp_path)
        gone = tmp_path / "gone.mp3"
        block.video_params.external_audio = [gone]
        block.video_params.audio_selection = AudioExternal(file=gone)

        block._forget_audio_file_that_is_gone()

        assert block.video_params.external_audio == [gone]

    def test_a_pick_whose_file_is_there_is_left_alone(self, tmp_path):
        audio = _file(tmp_path, "Movie.rus.mp3")
        block = _block(tmp_path)
        block.video_params.audio_selection = AudioExternal(file=audio)

        block._forget_audio_file_that_is_gone()

        assert block.video_params.audio_selection == AudioExternal(file=audio)

    def test_it_is_not_offered_while_it_is_away(self, tmp_path):
        """A row that cannot play anything is worse than no row."""

        block = _block(tmp_path)
        block.video_params.external_audio = [tmp_path / "gone.mp3"]

        assert _offered(block) == []
