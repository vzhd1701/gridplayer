"""Which audio output VLC is asked for on Linux.

VLC's PipeWire output (vlc-plugin-pipewire 3, as shipped by Fedora) never
sets its stream pointer when it opens, only when the first audio is played.
A mute or a volume change before then follows whatever the allocator left
there and the VLC process dies. Every player is muted the moment it is made,
and a video without sound never starts the output at all, so there is no
safe moment to wait for. PulseAudio is asked for first instead, which on a
PipeWire desktop is served by pipewire-pulse.
"""

import logging

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.vlc_player.instance import InstanceVLC


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


@pytest.fixture
def _on_linux(monkeypatch):
    monkeypatch.setattr(env, "IS_LINUX", True)
    monkeypatch.setattr(env, "IS_WINDOWS", False)
    monkeypatch.setattr(env, "IS_APPIMAGE", False)


@pytest.fixture
def _on_macos(monkeypatch):
    monkeypatch.setattr(env, "IS_LINUX", False)
    monkeypatch.setattr(env, "IS_WINDOWS", False)
    monkeypatch.setattr(env, "IS_APPIMAGE", False)


def _init_options():
    instance = InstanceVLC(0, [])
    instance._logger = logging.getLogger("test")

    return instance.init_options


def _aout_options(options):
    return [opt for opt in options if opt.startswith("--aout")]


@pytest.mark.usefixtures("_on_linux")
class TestOnLinux:
    def test_pulse_is_asked_for_first(self):
        assert _aout_options(_init_options()) == ["--aout=pulse,any"]

    def test_what_was_typed_by_hand_still_wins(self):
        """Last on the command line is what VLC goes by."""

        Settings().set("misc/vlc_options", "--aout=alsa")

        assert _aout_options(_init_options()) == ["--aout=pulse,any", "--aout=alsa"]


@pytest.mark.usefixtures("_on_macos")
class TestElsewhere:
    def test_the_platform_default_is_left_alone(self):
        assert _aout_options(_init_options()) == []
