"""Reading how long files are, on a player that may not be on VLC."""

import os

from gridplayer.utils import item_info, libvlc
from gridplayer.utils.media_libs import LibProblem


def test_no_process_is_started_with_no_vlc_to_read_with(monkeypatch, tmp_path):
    monkeypatch.setattr(item_info, "lib_problem", lambda _lib: LibProblem.MISSING)
    reader = item_info.FileLengths()

    lengths = reader.lengths([tmp_path / "a.mp4", tmp_path / "b.mp4"])

    assert lengths == [None, None]
    assert reader._pool is None


def test_the_vlc_that_came_with_the_app_is_set_without_loading_it(
    monkeypatch, tmp_path
):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    library = tmp_path / "libvlc.dll"
    library.touch()
    monkeypatch.setenv("PYTHON_VLC_MODULE_PATH", "")
    monkeypatch.setenv("PYTHON_VLC_LIB_PATH", "")
    monkeypatch.setattr(libvlc, "get_embed_vlc_paths", lambda: (plugins, library))

    libvlc.set_embed_vlc_env()

    assert os.environ["PYTHON_VLC_MODULE_PATH"] == str(plugins)
    assert os.environ["PYTHON_VLC_LIB_PATH"] == str(library)
