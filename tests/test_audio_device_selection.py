"""Which way out of the machine a video's sound was told to take."""

import json

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.models.audio_device import AudioDevice, resolve_device_id
from gridplayer.models.playlist import Playlist
from gridplayer.models.video import Video
from gridplayer.settings import Settings

URI = "http://example.com/a.mp4"

# one jack, as each output module happens to name it, and the description
# both of them give it word for word; see models/audio_device.py
HEADPHONES = "Headphones (ASUS XONAR PHOEBUS Audio Device)"
DIRECTSOUND_ID = "{7DA058ED-6619-4A72-87AD-4811890522CF}"
MMDEVICE_ID = "{0.0.0.00000000}.{7da058ed-6619-4a72-87ad-4811890522cf}"

SPDIF = "Digital Audio (S/PDIF) (ASUS XONAR PHOEBUS Audio Device)"
SPDIF_ID = "{C6A16AEF-1668-44F1-B888-837900444497}"

CHOSEN = AudioDevice(id=DIRECTSOUND_ID, name=HEADPHONES)

DIRECTSOUND_LIST = (
    CHOSEN,
    AudioDevice(id=SPDIF_ID, name=SPDIF),
)

# the same two after somebody put --aout=mmdevice in the VLC options
MMDEVICE_LIST = (
    AudioDevice(id=MMDEVICE_ID, name=HEADPHONES),
    AudioDevice(id="{0.0.0.00000000}.{c6a16aef}", name=SPDIF),
)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _saved(**kwargs):
    """A video written into a playlist and read back out of it."""

    video = Video(uri=URI, **kwargs)

    return Playlist.parse(Playlist(videos=[video]).dumps()).videos[0]


class TestAVideoNobodyAsked:
    def test_it_has_no_way_out_of_its_own(self):
        assert Video(uri=URI).audio_device is None

    def test_and_so_nothing_is_asked_of_vlc(self):
        """Which leaves the player wherever the machine already had it."""

        assert resolve_device_id(None, DIRECTSOUND_LIST) is None


class TestFindingTheDeviceAgain:
    def test_the_one_it_named(self):
        assert resolve_device_id(CHOSEN, DIRECTSOUND_LIST) == DIRECTSOUND_ID

    def test_under_an_id_it_did_not_have_before(self):
        """Changing the output module renames every device at once."""

        assert resolve_device_id(CHOSEN, MMDEVICE_LIST) == MMDEVICE_ID

    def test_a_device_that_is_not_here_asks_for_nothing(self):
        """Rather than an id libVLC would take and then play in silence."""

        unplugged = AudioDevice(id="{gone}", name="USB Headset")

        assert resolve_device_id(unplugged, DIRECTSOUND_LIST) is None

    def test_nor_is_a_name_it_does_not_answer_to_enough(self):
        gone = AudioDevice(id="{gone}", name="Speakers")

        assert resolve_device_id(gone, DIRECTSOUND_LIST) is None

    def test_one_that_was_never_named_has_only_its_id_to_go_on(self):
        nameless = AudioDevice(id="{gone}")

        assert resolve_device_id(nameless, DIRECTSOUND_LIST) is None
        assert resolve_device_id(AudioDevice(id=SPDIF_ID), DIRECTSOUND_LIST) == SPDIF_ID

    def test_nothing_on_offer_at_all_is_no_reason_to_guess(self):
        assert resolve_device_id(CHOSEN, ()) is None


class TestWhatOutlivesTheFile:
    def test_the_choice_comes_back_as_it_went_in(self):
        assert _saved(audio_device=CHOSEN).audio_device == CHOSEN

    def test_both_names_are_written_down(self):
        """The id for this machine, the description for any other."""

        written = json.loads(
            Playlist(videos=[Video(uri=URI, audio_device=CHOSEN)]).dumps()
        )

        assert written["videos"][0]["audio_device"] == {
            "id": DIRECTSOUND_ID,
            "name": HEADPHONES,
        }

    def test_a_playlist_written_before_this_existed_asks_for_nothing(self):
        assert _saved().audio_device is None

    def test_two_of_the_same_device_are_the_same_device(self):
        assert AudioDevice(id=SPDIF_ID, name=SPDIF) == AudioDevice(
            id=SPDIF_ID, name=SPDIF
        )
        assert CHOSEN != AudioDevice(id=SPDIF_ID, name=SPDIF)
