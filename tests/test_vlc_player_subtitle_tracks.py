"""Subtitles as the tracks manager sees them.

The id map, the switch, the delay, and putting all three back after a loop.
"""

import pytest

from gridplayer.vlc_player.player_tracks_manager import (
    TracksManager,
    _convert_subtitle_track,
)
from gridplayer.vlc_player.static import DISABLED_TRACK

from .test_vlc_player_tracks_manager import (
    FakeMediaPlayer,
    FakeSubtitleContent,
    make_audio_track,
    make_subtitle_track,
    make_video_track,
)


@pytest.fixture(autouse=True)
def fake_codec_description(monkeypatch):
    monkeypatch.setattr(
        "gridplayer.vlc_player.player_tracks_manager.vlc.libvlc_media_get_codec_description",
        lambda *_args: b"Text subtitles with various tags",
    )


def _manager(player, media_tracks):
    return TracksManager(
        media_player=player,
        media_tracks=media_tracks,
        is_audio_only=False,
        media_uri="movie.mkv",
    )


class TestReadingWhatIsThere:
    def test_a_subtitle_track_is_read_off_the_media(self):
        tracks = [make_subtitle_track(track_id=3, language=b"eng")]

        manager = _manager(FakeMediaPlayer(), tracks)

        assert list(manager.subtitle_tracks) == [3]
        assert manager.subtitle_tracks[3].language == "eng"
        assert manager.subtitle_tracks[3].encoding == "UTF-8"

    def test_the_encoding_is_shown_beside_the_codec(self):
        track = _convert_subtitle_track(
            make_subtitle_track(track_id=0, language=b"eng")
        )

        assert track.codec_info == "Text subtitles with various tags, UTF-8"

    def test_a_file_that_brought_no_encoding_says_only_the_codec(self):
        track = _convert_subtitle_track(
            make_subtitle_track(
                track_id=0, subtitle_content=FakeSubtitleContent(encoding=None)
            )
        )

        assert track.codec_info == "Text subtitles with various tags"

    def test_none_at_all_is_an_empty_list_rather_than_a_fault(self):
        manager = _manager(FakeMediaPlayer(), [make_video_track(track_id=0)])

        assert manager.subtitle_tracks == {}


class TestTheIdMap:
    """libVLC numbers every track of an input in one sequence.

    A subtitle therefore never answers to the number a picture or a sound
    answers to, which is what lets one flat map carry all three.
    """

    def _three_kinds(self):
        player = FakeMediaPlayer(
            video_desc=[(-1, b"Disable"), (0, b"Track 1")],
            audio_desc=[(-1, b"Disable"), (1, b"Track 1 - [English]")],
            spu_desc=[
                (-1, b"Disable"),
                (2, b"Track 1 - [English]"),
                (3, b"Track 2 - [Spanish]"),
            ],
        )

        media_tracks = [
            make_video_track(track_id=0),
            make_audio_track(track_id=1, language=b"eng"),
            make_subtitle_track(track_id=2, language=b"eng"),
            make_subtitle_track(track_id=3, language=b"spa"),
        ]

        return player, _manager(player, media_tracks)

    def test_each_kind_keeps_its_own_numbers(self):
        _player, manager = self._three_kinds()

        assert manager.tracks_map == {0: 0, 1: 1, 2: 2, 3: 3}

    def test_the_showing_subtitle_is_read_back_through_the_map(self):
        player, manager = self._three_kinds()

        player.spu_id = 3

        assert manager.current_subtitle_track_id == 3

    def test_showing_none_reads_back_as_nothing_chosen(self):
        player, manager = self._three_kinds()

        player.spu_id = DISABLED_TRACK

        assert manager.current_subtitle_track_id is None


class TestSwitchingThemOnAndOff:
    def _one_track(self):
        player = FakeMediaPlayer(
            spu_desc=[(-1, b"Disable"), (5, b"Track 1 - [English]")]
        )

        manager = _manager(player, [make_subtitle_track(track_id=5, language=b"eng")])

        return player, manager

    def test_asking_for_a_track_asks_libvlc_for_its_own_number(self):
        player, manager = self._one_track()

        manager.set_subtitle_track_id(5)

        assert ("video_set_spu", 5) in player.calls

    def test_switching_them_off_is_never_refused(self):
        """Unlike the picture and the sound, which guard each other."""

        player, manager = self._one_track()

        manager.set_subtitle_track_id(DISABLED_TRACK)

        assert ("video_set_spu", DISABLED_TRACK) in player.calls

    def test_a_track_the_media_does_not_have_is_left_alone(self):
        player, manager = self._one_track()

        manager.set_subtitle_track_id(99)

        assert player.calls == []

    def test_the_delay_reaches_libvlc_in_microseconds(self):
        player, manager = self._one_track()

        manager.set_subtitle_delay_ms(250)

        assert ("video_set_spu_delay", 250_000) in player.calls


class TestPuttingThemBackAfterALoop:
    """A new pass starts on whatever the container marks, every time."""

    def _asked_for(self, track_id=None, delay_ms=0):
        # the picture is what says the new pass has its streams; a media
        # carrying subtitles carries one of those too
        player = FakeMediaPlayer(
            video_desc=[(-1, b"Disable"), (0, b"Track 1")],
            spu_desc=[(-1, b"Disable"), (5, b"Track 1 - [English]")],
        )

        manager = _manager(
            player,
            [
                make_video_track(track_id=0),
                make_subtitle_track(track_id=5, language=b"eng"),
            ],
        )

        if track_id is not None:
            manager.set_subtitle_track_id(track_id)

        if delay_ms:
            manager.set_subtitle_delay_ms(delay_ms)

        player.calls.clear()

        return player, manager

    def test_a_subtitle_chosen_by_hand_is_chosen_again(self):
        player, manager = self._asked_for(track_id=5)

        manager.reapply()

        assert ("video_set_spu", 5) in player.calls

    def test_being_switched_off_is_put_back_too(self):
        """Or the video comes back wearing the container's own subtitle."""

        player, manager = self._asked_for(track_id=DISABLED_TRACK)

        manager.reapply()

        assert ("video_set_spu", DISABLED_TRACK) in player.calls

    def test_the_delay_is_put_back_after_the_track(self):
        player, manager = self._asked_for(track_id=5, delay_ms=250)

        manager.reapply()

        names = [call[0] for call in player.calls]

        assert names.index("video_set_spu") < names.index("video_set_spu_delay")

    def test_a_video_nobody_asked_anything_of_is_left_alone(self):
        """Which is what keeps a media with no subtitles free of all this."""

        player, manager = self._asked_for()

        assert manager.reapply() is True
        assert player.calls == []
