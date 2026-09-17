"""Applying the language preference to the tracks libVLC found in a file."""

import logging
from functools import partial
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.stream import Stream, Streams
from gridplayer.models.video import Video
from gridplayer.params.static import AudioTrackMode
from gridplayer.settings import Settings
from gridplayer.vlc_player.static import (
    DISABLED_TRACK,
    AudioTrack,
    wanted_audio_track_id,
)
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


def _track(language):
    return AudioTrack(
        codec="mp4a",
        bitrate=128000,
        language=language,
        description=None,
        channels=2,
        rate=48000,
    )


TRACKS = {0: _track("eng"), 1: _track("jpn"), 2: _track(None)}


def _player(mocker, languages="", mode=AudioTrackMode.PREFERRED, track_id=None):
    player = mocker.Mock()
    player._tracks_manager = mocker.Mock()
    player._tracks_manager.audio_tracks = TRACKS

    video = Video(uri="http://example.com/a.mp4")
    video.audio_languages = languages
    video.audio_track_mode = mode
    video.audio_track_id = track_id

    player.media_input = mocker.Mock()
    player.media_input.video = video

    return player


def _wanted(player):
    return wanted_audio_track_id(
        player.media_input.video, player._tracks_manager.audio_tracks
    )


@pytest.mark.parametrize(
    ("languages", "expected"),
    [
        ("en", 0),
        ("eng", 0),
        ("English", 0),
        ("ja", 1),
        ("de, ja", 1),
    ],
)
def test_the_preferred_language_decides_which_track_opens(mocker, languages, expected):
    assert _wanted(_player(mocker, languages)) == expected


def test_a_language_nothing_answers_to_leaves_the_file_alone(mocker):
    """None means "do not touch it", so the container's own default stands."""

    assert _wanted(_player(mocker, "de")) is None


def test_no_preference_leaves_the_file_alone(mocker):
    assert _wanted(_player(mocker, "")) is None


def test_an_untagged_track_answers_to_no_language(mocker):
    """Track 2 names no language, so nothing asked for can land on it."""

    assert _wanted(_player(mocker, "de, fr, qqq")) is None


def test_disabled_opens_with_no_audio_at_all(mocker):
    player = _player(mocker, "en", mode=AudioTrackMode.DISABLED)

    assert _wanted(player) == DISABLED_TRACK


def test_a_track_picked_by_hand_outranks_the_language_asked_for(mocker):
    player = _player(mocker, "en", mode=AudioTrackMode.EXPLICIT, track_id=1)

    assert _wanted(player) == 1


def _block(mocker, languages="", tracks=None):
    block = mocker.Mock()
    block._log = logging.getLogger("test")
    block.audio_tracks = TRACKS if tracks is None else tracks
    block.video_params = Video(uri="http://example.com/a.mp4")
    block.video_params.audio_languages = languages
    block.video_params.video_track_id = 0
    block._track_language_key = partial(VideoBlock._track_language_key, block)
    block._apply_wanted_audio_track = partial(
        VideoBlock._apply_wanted_audio_track, block
    )
    block.is_video_initialized = True
    # there is a picture, so the sound may be turned off
    block._is_video_track_off = False
    # a file is not dubbed by the site, so nothing is served per language
    block._language_variants = Streams()

    return block


def test_picking_a_track_by_hand_records_that_it_was_picked(mocker):
    block = _block(mocker)

    VideoBlock.set_audio_track(block, 1)

    assert block.video_params.audio_track_mode is AudioTrackMode.EXPLICIT
    assert block.video_params.audio_track_id == 1
    block.video_driver.set_audio_track.assert_called_once_with(1)


def test_disabling_audio_is_recorded_as_a_mode_rather_than_a_track(mocker):
    """The track id is overwritten on every load; the mode is not."""

    block = _block(mocker)

    VideoBlock.set_audio_track(block, DISABLED_TRACK)

    assert block.video_params.audio_track_mode is AudioTrackMode.DISABLED


def test_going_back_to_preferred_applies_the_language_again(mocker):
    block = _block(mocker, "ja")
    block.preferred_audio_track_id = VideoBlock.preferred_audio_track_id.fget(block)

    VideoBlock.apply_audio_preference(block)

    assert block.video_params.audio_track_mode is AudioTrackMode.PREFERRED
    assert block.video_params.audio_track_id == 1
    block.video_driver.set_audio_track.assert_called_once_with(1)


def test_going_back_to_preferred_keeps_the_track_when_nothing_matches(mocker):
    """Nothing here is in a language that was asked for, and audio is on."""

    block = _block(mocker, "de")
    block.video_driver.cur_audio_track_id = 0

    VideoBlock.apply_audio_preference(block)

    assert block.video_params.audio_track_mode is AudioTrackMode.PREFERRED
    block.video_driver.set_audio_track.assert_not_called()


def test_going_back_to_preferred_lifts_a_disable_even_with_no_match(mocker):
    """Otherwise "disable" would be a one-way door on an untagged video."""

    block = _block(mocker, "de")
    block.video_params.audio_track_mode = AudioTrackMode.DISABLED
    block.video_params.audio_track_id = DISABLED_TRACK
    block.video_driver.cur_audio_track_id = DISABLED_TRACK

    VideoBlock.apply_audio_preference(block)

    assert block.video_params.audio_track_mode is AudioTrackMode.PREFERRED
    block.video_driver.set_audio_track.assert_called_once_with(0)


def test_going_back_to_preferred_refetches_a_dubbed_stream(mocker):
    """There is only one track in hand, and it is the one being left behind."""

    block = _block(mocker, "en")
    block._language_variants = Streams(
        {
            language: Stream(url="http://host/s", protocol="http", language=language)
            for language in ("tlh", "en")
        }
    )

    # the tracks in hand are settled either way, but the reload is what
    # actually brings the preferred language back
    block._apply_wanted_audio_track = mocker.Mock()

    VideoBlock.apply_audio_preference(block)

    block.set_audio_language.assert_called_once_with(None)
    block._apply_wanted_audio_track.assert_called_once()


def test_the_preferred_track_is_found_by_language(mocker):
    block = _block(mocker, "English")

    assert VideoBlock.preferred_audio_track_id.fget(block) == 0


NAMESAKES = {0: _track("eng"), 1: _track("eng"), 2: _track("jpn")}


def test_a_pick_is_remembered_by_language_where_that_names_one_track(mocker):
    """An id is only as good as the media it was read from."""

    block = _block(mocker)

    VideoBlock.set_audio_track(block, 1)

    assert block.video_params.audio_language == "jpn"
    assert block.video_params.audio_track_id == 1


def test_a_pick_falls_back_to_the_id_where_two_tracks_share_a_language(mocker):
    """Commentary and feature are both English; only the id tells them apart."""

    block = _block(mocker, tracks=NAMESAKES)

    VideoBlock.set_audio_track(block, 1)

    assert block.video_params.audio_language is None
    assert block.video_params.audio_track_id == 1


def test_a_pick_falls_back_to_the_id_for_an_untagged_track(mocker):
    block = _block(mocker)

    VideoBlock.set_audio_track(block, 2)

    assert block.video_params.audio_language is None
    assert block.video_params.audio_track_id == 2


def test_namesakes_are_spotted_across_spellings_of_the_same_language(mocker):
    """ "eng" and "en" are one language however the container spelled them."""

    block = _block(mocker, tracks={0: _track("eng"), 1: _track("en")})

    VideoBlock.set_audio_track(block, 0)

    assert block.video_params.audio_language is None


def test_a_language_keyed_pick_survives_new_track_ids(mocker):
    """The stream was demuxed again and everything moved up one."""

    player = _player(mocker, mode=AudioTrackMode.EXPLICIT, track_id=1)
    player.media_input.video.audio_language = "jpn"
    player._tracks_manager.audio_tracks = {7: _track("eng"), 8: _track("jpn")}

    assert _wanted(player) == 8


def test_an_id_keyed_pick_is_used_where_no_language_was_stored(mocker):
    player = _player(mocker, mode=AudioTrackMode.EXPLICIT, track_id=2)
    player.media_input.video.audio_language = None

    assert _wanted(player) == 2


def test_a_language_keyed_pick_falls_back_to_the_id_when_it_is_gone(mocker):
    player = _player(mocker, mode=AudioTrackMode.EXPLICIT, track_id=1)
    player.media_input.video.audio_language = "kor"

    assert _wanted(player) == 1


def test_going_back_to_preferred_forgets_the_pick(mocker):
    block = _block(mocker, "ja")
    block.video_params.audio_language = "fre"
    block.preferred_audio_track_id = VideoBlock.preferred_audio_track_id.fget(block)

    VideoBlock.apply_audio_preference(block)

    assert block.video_params.audio_language is None


def test_disabling_audio_sticks_while_a_video_is_still_reloading(mocker):
    """A language switch reloads, and the click lands before it is done."""

    block = _block(mocker)
    block.is_video_initialized = False

    VideoBlock.set_audio_track(block, DISABLED_TRACK)

    assert block.video_params.audio_track_mode is AudioTrackMode.DISABLED
    block.video_driver.set_audio_track.assert_not_called()

    # what the load then settles on
    assert _wanted(_player_for(block)) == DISABLED_TRACK


def test_picking_a_language_after_a_disable_is_not_still_silent(mocker):
    """The -1 left behind must not outlive the mode that put it there."""

    video = Video(uri="http://example.com/a.mp4")
    video.audio_track_mode = AudioTrackMode.DISABLED
    video.audio_track_id = DISABLED_TRACK

    # the viewer now picks a language from the dubbed stream's menu
    video.audio_track_mode = AudioTrackMode.EXPLICIT
    video.audio_language = "tlh"
    video.audio_track_id = None

    # VLC is handed one rendition per language, and it may name none of them
    assert wanted_audio_track_id(video, {0: _track(None)}) is None


def test_a_stale_disable_is_never_mistaken_for_a_track_that_was_picked(mocker):
    video = Video(uri="http://example.com/a.mp4")
    video.audio_track_mode = AudioTrackMode.EXPLICIT
    video.audio_language = "kor"
    video.audio_track_id = DISABLED_TRACK

    assert wanted_audio_track_id(video, TRACKS) is None


def _player_for(block):
    player = SimpleNamespace(
        media_input=SimpleNamespace(video=block.video_params),
        _tracks_manager=SimpleNamespace(audio_tracks=block.audio_tracks),
    )
    return player
