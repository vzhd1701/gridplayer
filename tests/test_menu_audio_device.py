"""The Audio Device submenu: every way out of the machine, per video."""

from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.models.audio_device import AudioDevice
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.menu import SECTIONS
from gridplayer.player.managers.active_block import ActiveBlockManager
from gridplayer.widgets.video_block import VideoBlock

URI = "http://example.com/a.mp4"

HEADPHONES = "Headphones (ASUS XONAR PHOEBUS Audio Device)"
HEADPHONES_ID = "{7DA058ED-6619-4A72-87AD-4811890522CF}"
SPDIF = "Digital Audio (S/PDIF)"
SPDIF_ID = "{C6A16AEF-1668-44F1-B888-837900444497}"

OFFERED = (
    AudioDevice(id=HEADPHONES_ID, name=HEADPHONES),
    AudioDevice(id=SPDIF_ID, name=SPDIF),
)

DEFAULT_ROW = "System Default"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


class _Manager(ActiveBlockManager):
    """The manager's menu methods, without the rest of the player behind them."""

    def __init__(self, block):
        self._ctx = SimpleNamespace(active_block=block)

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None


def _manager(chosen=None, devices=OFFERED):
    block = SimpleNamespace(
        audio_devices=devices,
        video_params=Video(uri=URI, audio_device=chosen),
    )

    return _Manager(block)


def _menu(chosen=None, devices=OFFERED):
    return _manager(chosen, devices).menu_generator_audio_device()


def _titles(menu):
    return [item if item == "---" else item["title"] for item in menu]


def _checked(manager, menu):
    """The rows the menu would draw a tick against."""

    ticked = []

    for item in menu:
        if item == "---":
            continue

        check = item.get("check_if")

        if check is None:
            continue

        if isinstance(check, tuple):
            is_on = getattr(manager, check[0])(*check[1:])
        else:
            is_on = getattr(manager, check)()

        if is_on:
            ticked.append(item["title"])

    return ticked


class TestWhereItSits:
    def test_it_follows_the_ways_the_sound_can_be_played(self):
        """Which track, how it is mixed, and only then where it goes out."""

        audio = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Audio"
        )
        names = [item[0] if isinstance(item, tuple) else item for item in audio]

        assert names[names.index("Audio Mode") + 1] == "Audio Device"

    def test_and_comes_before_the_volume(self):
        audio = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Audio"
        )
        names = [item[0] if isinstance(item, tuple) else item for item in audio]

        assert names.index("Audio Device") < names.index("Audio Volume - Increase")

    def test_it_is_built_when_the_menu_opens(self):
        assert (
            ACTIONS["Audio Device"]["menu_generator"] == "menu_generator_audio_device"
        )

    def test_a_silent_video_is_not_offered_it(self):
        assert ACTIONS["Audio Device"]["show_if"] == "is_active_has_audio"

    def test_the_generator_is_one_the_manager_answers_to(self):
        assert hasattr(ActiveBlockManager, "menu_generator_audio_device")


class TestWhatIsOnOffer:
    def test_the_machines_own_heads_the_list(self):
        assert _titles(_menu())[0] == DEFAULT_ROW

    def test_then_every_device_the_process_can_reach(self):
        assert _titles(_menu())[1:] == ["---", HEADPHONES, SPDIF]

    def test_a_video_that_has_not_loaded_offers_nothing(self):
        """The list belongs to the process playing it, and none is."""

        assert _menu(devices=()) == {}

    def test_a_device_with_no_name_is_listed_by_its_id(self):
        nameless = (AudioDevice(id=SPDIF_ID),)

        assert _titles(_menu(devices=nameless))[-1] == SPDIF_ID


class TestWhatIsTicked:
    def test_the_machines_own_where_nothing_was_chosen(self):
        manager = _manager()

        assert _checked(manager, _menu()) == [DEFAULT_ROW]

    def test_the_device_that_was_chosen(self):
        chosen = AudioDevice(id=SPDIF_ID, name=SPDIF)

        assert _checked(_manager(chosen), _menu(chosen)) == [SPDIF]

    def test_one_found_again_under_another_id_ticks_where_it_landed(self):
        """Changing the output module renames every device at once."""

        moved = AudioDevice(id="{some other module}", name=SPDIF)

        assert _checked(_manager(moved), _menu(moved)) == [SPDIF]


class TestADeviceThatIsNotThere:
    """Silence is the alternative, and nothing else would say why."""

    def test_it_is_named_rather_than_dropped(self):
        gone = AudioDevice(id="{unplugged}", name="USB Headset")

        assert _titles(_menu(gone))[-1] == "USB Headset (not connected)"

    def test_and_it_is_the_row_that_is_ticked(self):
        gone = AudioDevice(id="{unplugged}", name="USB Headset")

        assert _checked(_manager(gone), _menu(gone)) == ["USB Headset (not connected)"]

    def test_a_device_that_is_here_adds_no_such_row(self):
        chosen = AudioDevice(id=SPDIF_ID, name=SPDIF)

        assert not [
            title for title in _titles(_menu(chosen)) if "not connected" in title
        ]


class TestWhereTheRowsLead:
    def test_every_row_asks_the_video_to_change_device(self):
        for item in _menu():
            if item == "---":
                continue

            command, method, *_ = item["func"]

            assert (command, method) == ("active", "set_audio_device")
            assert hasattr(VideoBlock, method)

    def test_a_device_row_hands_over_the_device_itself(self):
        rows = [item for item in _menu() if item != "---"]

        assert rows[1]["func"][2] == OFFERED[0]

    def test_the_machines_own_hands_over_nothing_at_all(self):
        assert _menu()[0]["func"][2] is None
