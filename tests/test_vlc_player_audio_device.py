"""Sending a video's sound out of the way it was told to, or not at all."""

import pickle
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from gridplayer.models.audio_device import SYSTEM_DEFAULT_DEVICE_ID, AudioDevice
from gridplayer.models.video import Video
from gridplayer.vlc_player import player_base
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import Media

URI = "http://example.com/a.mp4"

HEADPHONES = b"Headphones (ASUS XONAR PHOEBUS Audio Device)"
HEADPHONES_ID = b"{7DA058ED-6619-4A72-87AD-4811890522CF}"
SPDIF = b"Digital Audio (S/PDIF)"
SPDIF_ID = b"{C6A16AEF-1668-44F1-B888-837900444497}"

# what libVLC puts at the head of the list: the way out the machine is
# using, which has a description and no id of its own
MACHINES_OWN = (None, b"Default")

OFFERED = (MACHINES_OWN, (HEADPHONES_ID, HEADPHONES), (SPDIF_ID, SPDIF))


class _Ptr:
    """A pointer into the list, the way ctypes hands one over."""

    def __init__(self, contents):
        self.contents = contents


class _Entry:
    def __init__(self, device, description, next_ptr):
        self.device = device
        self.description = description
        self.next = next_ptr


def _device_list(entries):
    head = None

    for device, description in reversed(entries):
        head = _Ptr(_Entry(device, description, head))

    return head


class _FakeMediaPlayer:
    def __init__(self, entries=OFFERED):
        self._entries = entries
        self.devices_set = []

    def audio_output_device_enum(self):
        return _device_list(self._entries)

    def audio_output_device_set(self, module, device_id):
        self.devices_set.append((module, device_id))


@pytest.fixture(autouse=True)
def released_lists(monkeypatch):
    """The list is freed through libVLC, which these entries are not from."""

    released = []

    monkeypatch.setattr(
        player_base.vlc,
        "libvlc_audio_output_device_list_release",
        released.append,
    )

    return released


class _Player:
    """The player's device methods, without the rest of the player behind them."""

    _audio_devices = VlcPlayerBase._audio_devices
    _apply_wanted_audio_device = VlcPlayerBase._apply_wanted_audio_device
    set_audio_device = VlcPlayerBase.set_audio_device

    def __init__(self, chosen=None, entries=OFFERED):
        self._media_player = _FakeMediaPlayer(entries)
        self.media_input = SimpleNamespace(video=Video(uri=URI, audio_device=chosen))
        self._log = Mock()


def _player(chosen=None, entries=OFFERED):
    return _Player(chosen, entries)


def _devices(player):
    return player._audio_devices


def _apply(player):
    player._apply_wanted_audio_device(player._audio_devices)


class TestWhatTheProcessCanReach:
    def test_every_way_out_the_module_offers(self):
        assert _devices(_player()) == (
            AudioDevice(id=HEADPHONES_ID.decode(), name=HEADPHONES.decode()),
            AudioDevice(id=SPDIF_ID.decode(), name=SPDIF.decode()),
        )

    def test_the_machines_own_is_not_one_of_them(self):
        """It is what a video that chose nothing already has."""

        assert all(device.id for device in _devices(_player()))

    def test_a_name_that_will_not_decode_keeps_its_device(self):
        """A driver wrote it, and it is still a jack that can be picked."""

        entries = (MACHINES_OWN, (SPDIF_ID, b"Digital \xff Audio"))

        assert _devices(_player(entries=entries))[0].id == SPDIF_ID.decode()

    def test_the_list_is_handed_back_to_libvlc(self, released_lists):
        _devices(_player())

        assert len(released_lists) == 1

    def test_a_module_that_enumerates_nothing_offers_nothing(self):
        player = _player(entries=())

        assert _devices(player) == ()


class TestGettingTheListToTheWindow:
    """The window keeps no VLC of its own, so the list is carried to it."""

    def test_it_survives_the_trip_out_of_the_process(self):
        devices = _devices(_player())

        media = Media(
            length=1000, video_tracks={}, audio_tracks={}, audio_devices=devices
        )

        assert pickle.loads(pickle.dumps(media)).audio_devices == devices


class TestSendingTheSoundThatWay:
    def test_the_device_that_was_picked_is_asked_for(self):
        player = _player(AudioDevice(id=SPDIF_ID.decode(), name=SPDIF.decode()))

        _apply(player)

        assert player._media_player.devices_set == [(None, SPDIF_ID.decode())]

    def test_no_module_is_named_with_it(self):
        """Which is what moves the sound now rather than the next time."""

        player = _player(AudioDevice(id=SPDIF_ID.decode()))

        _apply(player)

        module, _ = player._media_player.devices_set[0]

        assert module is None

    def test_a_video_that_chose_nothing_is_left_alone(self):
        player = _player()

        _apply(player)

        assert player._media_player.devices_set == []

    def test_one_found_again_by_name_goes_to_its_new_id(self):
        moved = AudioDevice(id="{some other module}", name=SPDIF.decode())

        player = _player(moved)

        _apply(player)

        assert player._media_player.devices_set == [(None, SPDIF_ID.decode())]


class TestADeviceThatIsNotThere:
    """libVLC takes the id, reports it back, and plays in silence."""

    def test_it_is_never_passed_on(self):
        player = _player(AudioDevice(id="{unplugged}", name="USB Headset"))

        _apply(player)

        assert player._media_player.devices_set == []

    def test_and_it_is_said_out_loud(self):
        player = _player(AudioDevice(id="{unplugged}", name="USB Headset"))

        _apply(player)

        player._log.warning.assert_called_once()

        assert "USB Headset" in player._log.warning.call_args[0][0]


class TestPuttingItBack:
    def test_the_machines_own_is_asked_for_by_an_empty_id(self):
        """Asking for nothing would leave the player where it is."""

        player = _player(AudioDevice(id=SPDIF_ID.decode()))

        player.set_audio_device(None)

        assert player._media_player.devices_set == [(None, SYSTEM_DEFAULT_DEVICE_ID)]

    def test_and_the_video_stops_asking_for_the_old_one(self):
        player = _player(AudioDevice(id=SPDIF_ID.decode()))

        player.set_audio_device(None)

        assert player.media_input.video.audio_device is None

    def test_picking_one_while_it_plays_moves_it_and_is_remembered(self):
        player = _player()

        picked = AudioDevice(id=SPDIF_ID.decode(), name=SPDIF.decode())

        player.set_audio_device(picked)

        assert player.media_input.video.audio_device == picked
        assert player._media_player.devices_set == [(None, SPDIF_ID.decode())]
