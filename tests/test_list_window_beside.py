"""The List window opened on a cell stays open beside the player, one at a
time, the cell it plays in marked while it is."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QObject, QRect, QSettings, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.media_list import ListItem, MediaList
from gridplayer.player.managers import lists as lists_module
from gridplayer.player.managers.lists import ListsManager
from gridplayer.settings import Settings
from gridplayer.widgets.video_overlay import OverlayBlock
from gridplayer.widgets.video_overlay_elements import OverlayListWindowTag


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


class _Cell(QObject):
    list_place_change = pyqtSignal(str)
    closing = pyqtSignal()

    def __init__(self, registry, media_list):
        super().__init__()

        self._registry = registry
        self.video_params = SimpleNamespace(list_id=media_list.id)
        self.is_closing = False
        self.marks = []

    @property
    def media_list(self):
        return self._registry.get(self.video_params.list_id)

    @property
    def list_item(self):
        media_list = self.media_list
        return None if media_list is None else media_list.items[0]

    def set_list_window_shown(self, is_shown):
        self.marks.append(is_shown)


@pytest.fixture
def manager():
    parent = QWidget()
    ctx = SimpleNamespace(
        commands=MagicMock(), active_block=None, video_blocks=MagicMock()
    )
    ctx.video_blocks.blocks_for_ids.return_value = []

    manager = ListsManager(context=ctx, parent=parent)

    yield manager

    manager.close_list_window()
    QApplication.processEvents()
    parent.deleteLater()


def _a_list(manager, name="Channels"):
    return manager._ctx.lists.add(
        MediaList(name=name, items=(ListItem(uri="http://tv/1"),))
    )


def _cell(manager, media_list):
    cell = _Cell(manager._ctx.lists, media_list)
    manager._ctx.active_block = cell
    return cell


def test_open_beside_the_player(manager):
    cell = _cell(manager, _a_list(manager))

    manager.cmd_manage_list()

    window = manager._window
    assert window.isVisible()
    assert not window.isModal()
    assert window.block is cell
    assert cell.marks == [True]


def test_brought_up_again_rather_than_opened_twice(manager):
    _cell(manager, _a_list(manager))
    manager.cmd_manage_list()
    first = manager._window

    manager.cmd_manage_list()

    assert manager._window is first


def test_opened_on_the_cell_its_place_was_clicked_in(manager):
    clicked = _Cell(manager._ctx.lists, _a_list(manager))
    _cell(manager, _a_list(manager, "Films"))

    manager.list_window_for(clicked)

    assert manager._window.block is clicked
    assert clicked.marks == [True]


def test_brought_up_again_from_its_cell(manager):
    cell = _cell(manager, _a_list(manager))
    manager.list_window_for(cell)
    first = manager._window

    manager.list_window_for(cell)

    assert manager._window is first
    assert cell.marks == [True]


def test_one_at_a_time(manager):
    first_cell = _cell(manager, _a_list(manager))
    manager.cmd_manage_list()
    first = manager._window

    second_cell = _cell(manager, _a_list(manager, "Films"))
    manager.cmd_manage_list()

    assert manager._window is not first
    assert manager._window.block is second_cell
    assert first_cell.marks == [True, False]
    assert second_cell.marks == [True]


@pytest.fixture
def answer(manager, mocker):
    """What the viewer answers, asked whether to keep the changes made in
    the window that gives way to another: keep them, by default."""

    return mocker.patch.object(manager, "_ask_keep_changes", return_value=True)


def _edited(manager, media_list):
    _cell(manager, media_list)
    manager.cmd_manage_list()
    manager._window._name_edit.textEdited.emit("Renamed")

    return manager._window


def test_the_edits_kept_by_the_one_closed_for_another(manager, answer):
    media_list = _a_list(manager)
    _edited(manager, media_list)

    _cell(manager, _a_list(manager, "Films"))
    manager.cmd_manage_list()

    answer.assert_called_once()
    assert manager._ctx.lists.get(media_list.id).name == "Renamed"


def test_or_undone_where_the_viewer_says_so(manager, answer):
    answer.return_value = False
    media_list = _a_list(manager)
    _edited(manager, media_list)

    second_cell = _cell(manager, _a_list(manager, "Films"))
    manager.cmd_manage_list()

    assert manager._ctx.lists.get(media_list.id).name == "Channels"
    assert manager._window.block is second_cell


def test_left_open_where_the_viewer_thinks_better_of_it(manager, answer):
    answer.return_value = None
    media_list = _a_list(manager)
    first = _edited(manager, media_list)
    first_cell = first.block

    second_cell = _cell(manager, _a_list(manager, "Films"))
    manager.list_window_for(second_cell)

    assert manager._window is first
    assert first.isVisible()
    assert manager._ctx.lists.get(media_list.id).name == "Renamed"
    assert first_cell.marks == [True]
    assert second_cell.marks == []


def test_not_asked_where_nothing_was_changed(manager, answer):
    _cell(manager, _a_list(manager))
    manager.cmd_manage_list()

    _cell(manager, _a_list(manager, "Films"))
    manager.cmd_manage_list()

    answer.assert_not_called()


def test_the_next_opened_where_the_last_one_was(manager):
    _cell(manager, _a_list(manager))
    manager.cmd_manage_list()
    place = QRect(40, 50, 520, 420)
    manager._window.setGeometry(place)

    _cell(manager, _a_list(manager, "Films"))
    manager.cmd_manage_list()

    assert manager._window.geometry() == place


def test_the_lists_of_the_playlist_wait_for_the_answer(manager, answer, mocker):
    answer.return_value = None
    first = _edited(manager, _a_list(manager))
    viewer = mocker.patch.object(lists_module, "PlaylistListsDialog")

    manager.cmd_lists_in_playlist()

    viewer.assert_not_called()
    assert manager._window is first


def test_the_mark_gone_once_closed(manager):
    cell = _cell(manager, _a_list(manager))
    manager.cmd_manage_list()

    manager._window.reject()

    assert manager._window is None
    assert cell.marks == [True, False]


def test_a_closing_cell_is_left_alone(manager):
    cell = _cell(manager, _a_list(manager))
    manager.cmd_manage_list()

    cell.is_closing = True
    cell.closing.emit()

    assert manager._window is None
    assert cell.marks == [True]


def test_closed_for_the_lists_of_the_playlist(manager, answer, mocker):
    _cell(manager, _a_list(manager))
    manager.cmd_manage_list()
    window = manager._window
    viewer = mocker.patch.object(lists_module, "PlaylistListsDialog")

    manager.cmd_lists_in_playlist()

    assert manager._window is None
    assert window.isHidden()
    viewer.return_value.exec_.assert_called_once()


class TestTheTag:
    def test_said_under_the_title(self):
        overlay = OverlayBlock()

        overlay.set_list_window_shown(True)

        assert overlay.label_list_window.isVisibleTo(overlay)
        assert overlay.label_list_window.text == "Current list"
        assert overlay.info_bar.indexOf(overlay.label_list_window) == 0

    def test_rimmed_in_the_overlay_s_colour_round_its_dark_box(self):
        tag = OverlayListWindowTag()
        tag.color = "#ffffff"
        tag.text = "Current list"
        tag.resize(120, 23)

        image = tag.grab().toImage()

        assert QColor(image.pixel(0, 11)).lightness() > 200
        assert QColor(image.pixel(4, 4)).lightness() < 60

    def test_gone_once_closed(self):
        overlay = OverlayBlock()

        overlay.set_list_window_shown(True)
        overlay.set_list_window_shown(False)

        assert not overlay.label_list_window.isVisibleTo(overlay)

    def test_not_there_to_begin_with(self):
        assert not OverlayBlock().label_list_window.isVisibleTo(OverlayBlock())
