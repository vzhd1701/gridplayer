"""The navigation part of a video block goes by the cell it is part of."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from gridplayer.widgets.video_block_navigation import NavigationControl


def _cells(*uris):
    cells = []

    for uri in uris:
        cell = Mock()
        cell.video_params = SimpleNamespace(uri=uri, is_local_file=True)
        cell._ctx.video_blocks = cells
        cells.append(cell)

    return cells


def test_the_files_open_elsewhere_leave_out_its_own():
    """Its own is not one to skip on the way to the next file."""

    own, _ = _cells(Path("/videos/a.mp4"), Path("/videos/b.mp4"))

    navigation = NavigationControl(own)

    assert navigation._files_open_elsewhere() == [Path("/videos/b.mp4")]


def test_the_links_open_elsewhere_leave_out_its_own():
    own, _ = _cells("https://site.example/a", "https://site.example/b")

    navigation = NavigationControl(own)

    assert navigation._uris_open_elsewhere() == ["https://site.example/b"]


def test_the_list_window_is_opened_on_the_cell():
    (own,) = _cells(Path("/videos/a.mp4"))
    own.media_list = Mock()

    NavigationControl(own).show_list_window()

    own._ctx.commands.list_window_for.assert_called_once_with(own)
