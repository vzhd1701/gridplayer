"""Lists in Playlist: every list, which cells play it, and the lists taken
away or copied, Cancel taking that back."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.dialogs.playlist_lists import Column, PlaylistListsDialog
from gridplayer.models.media_list import ListItem, ListSource, MediaList
from gridplayer.params.static import ListSourceKind
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.settings import Settings


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


def _cell(list_id):
    return SimpleNamespace(video_params=SimpleNamespace(list_id=list_id))


@pytest.fixture
def registry():
    return MediaListsRegistry()


@pytest.fixture
def lists(registry):
    played = registry.add(
        MediaList(
            name="Season",
            items=(ListItem(uri=Path("/s/1.mkv")), ListItem(uri=Path("/s/2.mkv"))),
            source=ListSource(kind=ListSourceKind.FOLDER, location=Path("/s")),
        )
    )
    unused = registry.add(MediaList(name="", items=(ListItem(uri="http://tv/1"),)))
    registry.take_up(unused.id)

    return played, unused


@pytest.fixture
def make_dialog(registry, lists):
    played, _unused = lists
    calls = SimpleNamespace(edited=[], opened=[])
    cells = [_cell(None), _cell(played.id), _cell(played.id)]
    made = []

    def _open_in_new_cell(list_id, place):
        calls.opened.append((list_id, place))
        cells.append(_cell(list_id))

    def _make():
        dialog = PlaylistListsDialog(
            registry=registry,
            cells=lambda: cells,
            edit_list=calls.edited.append,
            open_in_new_cell=_open_in_new_cell,
        )
        dialog.calls = calls
        made.append(dialog)
        return dialog

    yield _make

    for dialog in made:
        dialog.done(0)
        dialog.deleteLater()


def _rows(dialog):
    model = dialog._model
    return [
        [model.item(row, column).text() for column in Column]
        for row in range(model.rowCount())
    ]


def _pick(dialog, row):
    dialog._list.setCurrentIndex(dialog._model.index(row, 0))


class TestShowing:
    def test_each_list_and_its_cells(self, make_dialog):
        assert _rows(make_dialog()) == [
            ["Season", "2", "Folder", "2, 3"],
            ["Untitled", "1", "Added", "none"],
        ]

    def test_counted(self, make_dialog):
        assert make_dialog()._hint.text() == "Lists: 2 · Items: 3"


class TestRemoving:
    def test_not_a_list_a_cell_plays(self, make_dialog):
        dialog = make_dialog()
        _pick(dialog, 0)

        assert not dialog._remove_button.isEnabled()

    def test_one_no_cell_plays(self, make_dialog, registry, lists):
        _played, unused = lists
        dialog = make_dialog()
        _pick(dialog, 1)

        dialog._remove()

        assert registry.get(unused.id) is None
        assert len(_rows(dialog)) == 1

    def test_every_one_no_cell_plays(self, make_dialog, registry, lists):
        played, _unused = lists

        make_dialog()._remove_unused()

        assert [media_list.id for media_list in registry.lists()] == [played.id]

    def test_put_back_with_cancel(self, make_dialog, registry, lists):
        _played, unused = lists
        dialog = make_dialog()

        dialog._remove_unused()
        dialog.reject()

        assert registry.get(unused.id) == unused

    def test_put_back_as_it_was_left_by_its_cells(self, make_dialog, registry, lists):
        played, unused = lists
        dialog = make_dialog()

        dialog._remove_unused()
        dialog.reject()

        # left, it goes when the playlist is saved, as it would have
        assert registry.is_taken_up(unused.id)
        assert registry.kept({played.id}) == [played]


class TestDuplicating:
    def test_a_copy_of_its_own(self, make_dialog, registry, lists):
        played, _unused = lists
        dialog = make_dialog()
        _pick(dialog, 0)

        dialog._duplicate()

        copy = registry.lists()[-1]
        assert copy.id != played.id
        assert copy.name == "Season (copy)"
        assert copy.items == played.items
        assert _rows(dialog)[-1] == ["Season (copy)", "2", "Folder", "none"]

    def test_taken_back_with_cancel(self, make_dialog, registry):
        dialog = make_dialog()
        _pick(dialog, 0)

        dialog._duplicate()
        dialog.reject()

        assert len(registry.lists()) == 2

    def test_not_one_opened_in_a_new_cell_meanwhile(self, make_dialog, registry):
        dialog = make_dialog()
        _pick(dialog, 0)
        dialog._duplicate()

        dialog._open()
        dialog.reject()

        assert registry.lists()[-1].name == "Season (copy)"


class TestOpening:
    def test_edited_in_its_window(self, make_dialog, lists):
        played, _unused = lists
        dialog = make_dialog()
        _pick(dialog, 0)

        dialog._edit()

        assert dialog.calls.edited == [played.id]

    def test_in_a_new_cell_from_the_first(self, make_dialog, lists):
        _played, unused = lists
        dialog = make_dialog()
        _pick(dialog, 1)

        dialog._open()

        assert dialog.calls.opened == [(unused.id, 0)]
