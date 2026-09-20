"""Clicking the Audio Track submenu, from the menu entry down to the driver.

Every layer of this was covered on its own and the chain still broke, so
this drives the whole of it: the generated entry, the command lookup, the
gate that drops commands while a video loads, the block, and the driver.
"""

import logging
from functools import partial
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.audio_selection import (
    AudioDisabled,
    AudioLanguage,
)
from gridplayer.models.stream import Stream, Streams
from gridplayer.models.video import Video
from gridplayer.player.manager import Commands
from gridplayer.player.managers.actions import ActionsManager
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.vlc_player.static import (
    DISABLED_TRACK,
    AudioTrack,
    wanted_audio_track_id,
)
from gridplayer.widgets.video_block import VideoBlock


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _ladder():
    """The dubbed ladder yt-dlp returns for a multi-language video."""

    return Streams(
        {
            f"720p ({language})": Stream(
                url=f"http://host/720-{language}",
                protocol="hls_proxy",
                language=language,
                is_original_language=language == "en",
            )
            for language in ("cop", "tlh", "en")
        }
    )


class _TracksManager:
    """The player side of a track switch, refusing the same way VLC's does."""

    def __init__(self, video_track, audio_track):
        self.video_track = video_track
        self.audio_track = audio_track
        self._is_video_switched_off = False

    def set_audio_track_id(self, track_id):
        if track_id == DISABLED_TRACK and self._is_video_switched_off:
            return

        self.audio_track = track_id


class _Driver:
    """Stands in for the VLC driver, recording what it was told."""

    def __init__(self):
        self.cur_audio_track_id = 0
        self.cur_video_track_id = 1
        self.is_video_initialized = True
        self.audio_tracks = {
            # the real rungs carry no language on the audio track itself
            0: AudioTrack(
                codec="mp4a",
                bitrate=1,
                language=None,
                description=None,
                channels=2,
                rate=48000,
            )
        }
        self.calls = []
        # an adaptive stream renumbers its streams as it runs, and from
        # then on libVLC answers -1 for a picture that is still on screen
        self.tracks_manager = _TracksManager(video_track=-1, audio_track=2)

    def set_audio_track(self, track_id):
        self.calls.append(track_id)
        self.tracks_manager.set_audio_track_id(track_id)
        self.cur_audio_track_id = self.tracks_manager.audio_track


class _Block:
    """A block with the real audio methods and the reload stubbed out."""

    _language_variants = VideoBlock._language_variants
    audio_language_options = VideoBlock.audio_language_options
    audio_language = VideoBlock.audio_language
    preferred_audio_language = VideoBlock.preferred_audio_language
    preferred_audio_track_id = VideoBlock.preferred_audio_track_id
    stream_ladder = VideoBlock.stream_ladder
    audio_tracks = VideoBlock.audio_tracks
    is_video_initialized = VideoBlock.is_video_initialized
    is_local_file = VideoBlock.is_local_file
    audio_track_playing = VideoBlock.audio_track_playing
    audio_language_playing = VideoBlock.audio_language_playing
    apply_audio_default = VideoBlock.apply_audio_default
    default_audio_track_id = VideoBlock.default_audio_track_id
    offered_audio_files = VideoBlock.offered_audio_files
    discovered_audio_files = VideoBlock.discovered_audio_files
    attached_audio_file = VideoBlock.attached_audio_file
    external_audio_track_ids = VideoBlock.external_audio_track_ids

    set_audio_language = VideoBlock.set_audio_language
    apply_audio_preference = VideoBlock.apply_audio_preference
    _apply_wanted_audio_track = VideoBlock._apply_wanted_audio_track
    set_audio_track = VideoBlock.set_audio_track
    _audio_selection_for = VideoBlock._audio_selection_for
    _wanted_audio_track_id = VideoBlock._wanted_audio_track_id
    _is_video_track_off = VideoBlock._is_video_track_off
    _track_language_key = VideoBlock._track_language_key
    get_audio_languages = VideoBlock.get_audio_languages

    def __init__(self):
        self._log = logging.getLogger("test-block")
        self.streams = _ladder()
        self.video_params = Video(uri="http://example.com/v")
        self.video_driver = _Driver()
        self._audio_language_playing = None
        self._quality_adapt_timer = SimpleNamespace(stop=lambda: None)
        self._ctx = SimpleNamespace(
            commands=SimpleNamespace(
                warning=lambda message: self.warnings.append(message)
            )
        )
        self.warnings = []
        self.reloads = []
        # a stream with nothing beside it, so every track is one of its own
        self.external_audio_tracks = {}
        self.video_track_unmapped = False

        self.load_stream_quality("best")

    @property
    def is_playable(self):
        return self.is_video_initialized

    def reset(self):
        pass

    def load_stream_quality(self, wanted):
        quality, _ = self.stream_ladder.by_quality(wanted)

        self.video_params.stream_quality = quality
        self._audio_language_playing = self.audio_language
        self.reloads.append(quality)

        # what the player settles on when the new media comes up
        wanted_track = wanted_audio_track_id(
            self.video_params, self.video_driver.audio_tracks
        )
        self.video_driver.cur_audio_track_id = (
            wanted_track if wanted_track is not None else 0
        )

        # what load_video_finish records afterwards; the video track comes
        # back unmapped whenever the picture is not up yet
        self.video_params.video_track_id = (
            None if self.video_track_unmapped else self.video_driver.cur_video_track_id
        )


class _Manager(ActiveBlockManager):
    def __init__(self, block):
        self._log = logging.getLogger("test-manager")
        self._ctx = SimpleNamespace(active_block=block)

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None


# an unparented QAction is collected the moment the test lets go of it,
# and Qt deletes it out from under the signal it was just connected to
_PARENTS = []


def _submenu(block):
    """Build the real QActions the Audio Track submenu would show."""

    manager = _Manager(block)

    parent = QWidget()
    _PARENTS.append(parent)

    commands = Commands()
    commands.update(
        {
            "active": manager.cmd_active,
            "is_active_initialized": lambda: block.is_video_initialized,
            "is_active_param_set_to": lambda attr, value: (
                getattr(block.video_params, attr) == value
            ),
            "is_active_audio_language": manager.is_active_audio_language,
            "is_active_audio_track": manager.is_active_audio_track,
            "is_active_audio_preferred": manager.is_active_audio_preferred,
            "is_active_audio_disabled": manager.is_active_audio_disabled,
            "is_active_audio_default": manager.is_active_audio_default,
        }
    )

    actions_manager = SimpleNamespace(
        _ctx=SimpleNamespace(commands=commands),
        parent=lambda: parent,
        _invoking=False,
    )
    actions_manager._map_dynamic_functions = partial(
        ActionsManager._map_dynamic_functions, actions_manager
    )
    actions_manager._run_action = partial(ActionsManager._run_action, actions_manager)

    entries = {}
    for template in manager.menu_generator_audio_track():
        if template == "---":
            continue
        action = ActionsManager._make_action(actions_manager, template)
        action.adapt()
        entries[action.text()] = action

    return entries


def _click(block, title):
    entries = _submenu(block)
    action = next(a for text, a in entries.items() if text.startswith(title))

    assert not action.is_skipped, f"{title} is not on the menu"

    action.trigger()


def test_disable_audio_works_on_a_freshly_opened_video():
    block = _Block()

    _click(block, "Disable Audio")

    assert block.video_params.audio_selection == AudioDisabled()
    assert block.video_driver.calls == [DISABLED_TRACK]


def test_disable_audio_works_after_a_language_was_picked():
    """The reported failure: it did nothing once any language was chosen."""

    block = _Block()

    _click(block, "Klingon")
    assert block.video_params.audio_selection == AudioLanguage(tag="tlh")

    _click(block, "Disable Audio")

    assert block.video_params.audio_selection == AudioDisabled()
    assert block.video_driver.calls[-1] == DISABLED_TRACK
    assert block.warnings == []


def test_disable_audio_works_after_going_back_to_preferred():
    block = _Block()

    _click(block, "Coptic")
    _click(block, "Preferred")
    _click(block, "Disable Audio")

    assert block.video_params.audio_selection == AudioDisabled()
    assert block.video_driver.calls[-1] == DISABLED_TRACK


def test_a_language_can_be_picked_again_after_disabling():
    block = _Block()

    _click(block, "Disable Audio")
    _click(block, "Klingon")

    assert block.video_params.audio_selection == AudioLanguage(tag="tlh")
    assert block.audio_language == "tlh"


def test_disable_audio_works_when_the_video_track_came_back_unmapped():
    """load_video_finish records None whenever the picture is not up yet.

    That is "nothing read back", not "the video track is off", and taking
    it for the latter left Disable Audio refusing for the life of the
    media: every reload records it again.
    """

    block = _Block()
    block.video_track_unmapped = True

    _click(block, "Klingon")
    assert block.video_params.video_track_id is None

    _click(block, "Disable Audio")

    assert block.warnings == []
    assert block.video_params.audio_selection == AudioDisabled()
    assert block.video_driver.calls[-1] == DISABLED_TRACK


def test_disable_audio_reaches_the_player_after_a_language_was_picked():
    """The click has to survive both guards, not just the one in the block.

    Each of them read an unknown track id as a disabled one, at a
    different layer, and each on its own let the click through while the
    pair of them still swallowed it.
    """

    block = _Block()
    block.video_track_unmapped = True

    _click(block, "Coptic")
    _click(block, "Disable Audio")

    assert block.video_driver.tracks_manager.audio_track == DISABLED_TRACK


def test_disabling_audio_is_still_refused_when_the_picture_is_off():
    block = _Block()
    block.video_driver.cur_video_track_id = DISABLED_TRACK
    block.load_stream_quality("best")

    _click(block, "Disable Audio")

    assert block.warnings
    assert block.video_params.audio_selection != AudioDisabled()


def test_the_language_already_playing_still_turns_the_sound_back_on():
    """Coptic, Disable Audio, Coptic again.

    The rung on screen is already the Coptic one, so there is nothing to
    reload and the click used to stop there -- leaving the sound off,
    with only a different language able to bring it back.
    """

    block = _Block()

    _click(block, "Coptic")
    reloads_before = len(block.reloads)

    _click(block, "Disable Audio")
    assert block.video_driver.tracks_manager.audio_track == DISABLED_TRACK

    _click(block, "Coptic")

    assert block.video_params.audio_selection == AudioLanguage(tag="cop")
    assert block.video_driver.tracks_manager.audio_track != DISABLED_TRACK
    assert len(block.reloads) == reloads_before, "the same rung needs no reload"
