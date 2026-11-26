import sysconfig
from pathlib import Path

import pytest

from gridplayer.params import env
from gridplayer.utils import libvlc


@pytest.fixture
def in_snap(monkeypatch):
    monkeypatch.setattr(env, "IS_PYINSTALLER", False)
    monkeypatch.setattr(env, "IS_SNAP", True)
    monkeypatch.setenv("SNAP", "/snap/gridplayer/x1")

    def multiarch_is(name):
        real = sysconfig.get_config_var
        monkeypatch.setattr(
            sysconfig,
            "get_config_var",
            lambda key: name if key == "MULTIARCH" else real(key),
        )

    return multiarch_is


@pytest.mark.parametrize("multiarch", ["x86_64-linux-gnu", "aarch64-linux-gnu"])
def test_a_snap_finds_vlc_in_the_folder_of_its_architecture(in_snap, multiarch):
    in_snap(multiarch)

    root = libvlc.get_embed_vlc_root()

    assert root == Path("/snap/gridplayer/x1/usr/lib") / multiarch


def test_a_python_naming_no_architecture_leaves_vlc_to_be_looked_for(in_snap):
    in_snap(None)

    assert libvlc.get_embed_vlc_root() is None
