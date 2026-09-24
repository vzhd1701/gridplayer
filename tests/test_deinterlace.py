"""Deinterlacing, per video: automatic, on or off, and the mode it runs in.

libVLC 3 keeps deinterlacing on the media player, so every video has its
own even where several share one VLC process. It can switch a player on or
off, mode and all, while it plays; but auto is only where a player starts,
and on auto the mode comes from the VLC instance -- so going back to auto,
or picking another mode while on it, opens the video again.
"""

from functools import partial
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from gridplayer.models.playlist import PlaylistVideoDefaults
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.defaults_fields import VIDEO_FIELDS
from gridplayer.params.menu import SECTIONS, SUBMENUS
from gridplayer.params.static import VideoDeinterlace, VideoDeinterlaceMode
from gridplayer.settings import Settings
from gridplayer.utils.libvlc_options_parser import DeinterlaceModeMap, get_vlc_options
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import MediaInput
from gridplayer.widgets.video_block import VideoBlock, _is_deinterlace_reload_needed

URI = "http://example.com/a.mp4"

AUTO = VideoDeinterlace.AUTO
ON = VideoDeinterlace.ON
OFF = VideoDeinterlace.OFF

MODE_AUTO = VideoDeinterlaceMode.AUTO
X = VideoDeinterlaceMode.X
YADIF = VideoDeinterlaceMode.YADIF
BOB = VideoDeinterlaceMode.BOB


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


def _video(deinterlace, mode):
    return Video(uri=URI, deinterlace=deinterlace, deinterlace_mode=mode)


class _MinimalPlayer(VlcPlayerBase):
    def notify_snapshot_taken(self, snapshot_path): ...
    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def notify_tracks_changed(self, media_track): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _FakeEventManager:
    def event_attach(self, event_type, callback): ...


class _FakeMedia:
    def event_manager(self):
        return _FakeEventManager()

    def add_options(self, *options): ...

    def parse_with_options(self, parse_flag, timeout): ...

    def tracks_get(self):
        return []


class _FakeInstance:
    def media_new(self, uri):
        return _FakeMedia()

    def media_new_path(self, uri):
        return _FakeMedia()


def _loaded_player(deinterlace, mode):
    """A player that has opened a video, and what it told the media player."""

    player = _MinimalPlayer(vlc_instance=_FakeInstance())
    player._media_player = Mock()

    player.load_video(
        MediaInput(
            uri=URI,
            is_live=False,
            is_audio_only=False,
            size=(640, 360),
            video=_video(deinterlace, mode),
        )
    )

    return player


def _told(player):
    return [c.args for c in player._media_player.video_set_deinterlace.mock_calls]


class TestWhatGoesToVLC:
    def test_on_names_the_mode(self):
        assert _told(_loaded_player(ON, YADIF)) == [("yadif",)]

    def test_off_names_no_mode(self):
        assert _told(_loaded_player(OFF, YADIF)) == [(None,)]

    def test_auto_leaves_the_player_as_it_starts(self):
        assert _told(_loaded_player(AUTO, YADIF)) == []

    def test_on_in_the_auto_mode_is_named_x(self):
        """libVLC 3 turns "auto" away; every deinterlacer reads it as "x"."""

        assert _told(_loaded_player(ON, MODE_AUTO)) == [("x",)]

    def test_a_change_while_playing_goes_to_the_same_player(self):
        player = _loaded_player(AUTO, X)

        player.set_deinterlace(ON, BOB)
        player.set_deinterlace(OFF, BOB)

        assert _told(player) == [("bob",), (None,)]
        # kept for the player's own copy of the video, like the view is
        assert player.media_input.video.deinterlace == OFF
        assert player.media_input.video.deinterlace_mode == BOB

    def test_every_mode_has_the_name_vlc_knows_it_by(self):
        assert set(DeinterlaceModeMap) == set(VideoDeinterlaceMode)
        assert DeinterlaceModeMap[MODE_AUTO] == "auto"
        assert DeinterlaceModeMap[VideoDeinterlaceMode.YADIF2X] == "yadif2x"
        assert DeinterlaceModeMap[VideoDeinterlaceMode.IVTC] == "ivtc"


class TestWhichProcessItPlaysIn:
    """On auto the mode can only come from the instance, which is shared."""

    def test_auto_in_the_auto_mode_needs_nothing(self):
        """It is what the instance is on already, so no process of its own."""

        assert get_vlc_options(_video(AUTO, MODE_AUTO)) == []

    def test_auto_in_a_mode_named_outright_is_handed_over_as_is(self):
        assert get_vlc_options(_video(AUTO, X)) == ["--deinterlace-mode=x"]

    def test_auto_in_another_mode_takes_an_instance_of_its_own(self):
        assert get_vlc_options(_video(AUTO, YADIF)) == ["--deinterlace-mode=yadif"]

    @pytest.mark.parametrize("deinterlace", [ON, OFF])
    def test_on_or_off_is_the_players_own_business(self, deinterlace):
        assert get_vlc_options(_video(deinterlace, YADIF)) == []


class TestWhenItTakesAReload:
    @pytest.mark.parametrize(
        ("current", "wanted"),
        [
            ((ON, YADIF), (AUTO, YADIF)),
            ((OFF, X), (AUTO, X)),
            ((AUTO, X), (AUTO, YADIF)),
            ((AUTO, YADIF), (AUTO, MODE_AUTO)),
        ],
    )
    def test_getting_to_auto_or_changing_its_mode(self, current, wanted):
        assert _is_deinterlace_reload_needed(_video(*current), *wanted)

    @pytest.mark.parametrize(
        ("current", "wanted"),
        [
            ((AUTO, X), (ON, X)),
            ((AUTO, YADIF), (OFF, YADIF)),
            ((ON, X), (ON, BOB)),
            ((OFF, X), (ON, X)),
            ((AUTO, YADIF), (AUTO, YADIF)),
        ],
    )
    def test_everything_else_is_done_in_place(self, current, wanted):
        assert not _is_deinterlace_reload_needed(_video(*current), *wanted)


def _block(deinterlace, mode, has_video=True):
    block = Mock(spec=VideoBlock)
    block.video_params = _video(deinterlace, mode)
    block.video_tracks = [0] if has_video else []
    block.video_driver = Mock()
    for name in ("set_deinterlace", "set_deinterlace_mode", "set_deinterlace_params"):
        setattr(block, name, partial(getattr(VideoBlock, name), block))
    return block


def _state(block):
    return block.video_params.deinterlace, block.video_params.deinterlace_mode


class TestPickingItOnOneVideo:
    def test_switching_on_is_done_in_place(self):
        block = _block(AUTO, BOB)

        block.set_deinterlace(ON)

        block.video_driver.set_deinterlace.assert_called_once_with(ON, BOB)
        block.reload.assert_not_called()
        assert _state(block) == (ON, BOB)

    def test_going_back_to_auto_reopens(self):
        block = _block(ON, BOB)

        block.set_deinterlace(AUTO)

        block.reload.assert_called_once()
        block.video_driver.set_deinterlace.assert_not_called()
        assert _state(block) == (AUTO, BOB)

    def test_picking_a_mode_while_off_switches_it_on(self):
        """As VLC's own menu does: nobody picks a mode to leave it unused."""

        block = _block(OFF, X)

        block.set_deinterlace_mode(YADIF)

        block.video_driver.set_deinterlace.assert_called_once_with(ON, YADIF)
        assert _state(block) == (ON, YADIF)

    def test_picking_a_mode_while_on_auto_stays_on_auto(self):
        block = _block(AUTO, X)

        block.set_deinterlace_mode(YADIF)

        block.reload.assert_called_once()
        assert _state(block) == (AUTO, YADIF)

    def test_a_video_without_a_picture_is_left_alone(self):
        block = _block(AUTO, X, has_video=False)

        block.set_deinterlace(ON)
        block.set_deinterlace_mode(YADIF)

        block.video_driver.set_deinterlace.assert_not_called()
        block.reload.assert_not_called()
        assert _state(block) == (AUTO, X)


class TestSnapshots:
    def _snapshot_block(self, current, wanted):
        block = _block(*current)
        block.is_video_initialized = True
        block._default_title = "a"

        snapshot = _video(*wanted)
        VideoBlock.apply_snapshot(block, snapshot)

        return block, snapshot

    def test_one_on_auto_reopens_the_video_as_it_was_saved(self):
        block, snapshot = self._snapshot_block((ON, X), (AUTO, X))

        block.reload.assert_called_once()
        assert block.video_params == snapshot

    def test_one_on_or_off_is_restored_in_place(self):
        block, _ = self._snapshot_block((AUTO, X), (ON, BOB))

        block.reload.assert_not_called()
        block.video_driver.set_deinterlace.assert_called_once_with(ON, BOB)


class TestTheMenu:
    def _video_submenu(self):
        return next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Video"
        )

    def _deinterlace_submenu(self):
        return next(
            item
            for item in self._video_submenu()
            if isinstance(item, tuple) and item[0] == "Deinterlace"
        )

    def test_it_is_one_submenu_below_the_others_in_video(self):
        """The last submenu; Take Screenshot goes under all of them."""

        video = self._video_submenu()
        submenus = [i[0] for i in video if isinstance(i, tuple)]

        assert submenus[-1] == "Deinterlace"
        assert "Deinterlace" in SUBMENUS

    def test_the_state_comes_first_then_the_modes(self):
        deinterlace = self._deinterlace_submenu()

        assert deinterlace[1:5] == (
            "Deinterlace Auto",
            "Deinterlace On",
            "Deinterlace Off",
            "---",
        )
        modes = [ACTIONS[a]["func"][2] for a in deinterlace[5:]]
        assert modes == list(VideoDeinterlaceMode)

    def test_every_row_reaches_the_video_and_shows_what_is_in_force(self):
        deinterlace = self._deinterlace_submenu()

        for name in deinterlace[1:]:
            if name == "---":
                continue
            action = ACTIONS[name]
            target, command, value = action["func"]
            assert target == "active"
            assert hasattr(VideoBlock, command)
            assert action["check_if"][2] == value
            assert action["show_if"] == "is_active_has_video"


class TestWhereItIsRemembered:
    def test_a_new_video_is_left_to_vlc_entirely(self):
        video = Video(uri=URI)

        assert video.deinterlace == AUTO
        assert video.deinterlace_mode == MODE_AUTO

    def test_a_new_video_starts_on_what_the_defaults_say(self):
        Settings().set("video_defaults/deinterlace", ON)
        Settings().set("video_defaults/deinterlace_mode", YADIF)

        assert _state(Mock(video_params=Video(uri=URI))) == (ON, YADIF)

    def test_a_playlist_that_says_nothing_leaves_it_to_the_defaults(self):
        defaults = PlaylistVideoDefaults()

        assert defaults.deinterlace is None
        assert defaults.deinterlace_mode is None

    def test_a_playlist_can_carry_its_own(self):
        defaults = PlaylistVideoDefaults(deinterlace="on", deinterlace_mode="bob")

        assert defaults.deinterlace == ON
        assert defaults.deinterlace_mode == BOB


class TestPlaylistSettings:
    def _keys(self):
        return [f.settings_key for f in VIDEO_FIELDS]

    def test_it_sits_under_transform_in_the_video_section(self):
        keys = self._keys()
        at = keys.index("video_defaults/transform")

        assert keys[at + 1 : at + 3] == [
            "video_defaults/deinterlace",
            "video_defaults/deinterlace_mode",
        ]
        for key in keys[at + 1 : at + 3]:
            spec = next(f for f in VIDEO_FIELDS if f.settings_key == key)
            assert spec.section == "Video"

    def test_the_mode_is_greyed_out_while_it_is_off(self):
        spec = next(
            f
            for f in VIDEO_FIELDS
            if f.settings_key == "video_defaults/deinterlace_mode"
        )

        assert spec.enabled_by == "video_defaults/deinterlace"
        assert set(spec.enabled_by_value) == {AUTO, ON}
