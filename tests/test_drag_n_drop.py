import time
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt5.QtGui import QDropEvent, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication, QDialog, QLineEdit, QWidget

from gridplayer.models.media_list import ListSource, MediaList
from gridplayer.params.static import DropAction, ListSourceKind
from gridplayer.player.managers.drag_n_drop import DragNDropManager
from gridplayer.utils.drag_n_drop import drop_is_replace
from gridplayer.utils.drop_zone import DropIndicator, DropZone
from gridplayer.utils.files import LIST_MIME, VIDEO_MIME


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _mouse_move():
    return QMouseEvent(
        QEvent.MouseMove,
        QPoint(1, 1),
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


def _key_press(key, modifiers=Qt.NoModifier):
    return QKeyEvent(QEvent.KeyPress, key, modifiers)


def test_drop_is_replace_insert_default_shift():
    action = DropAction.INSERT
    modifier = Qt.ShiftModifier
    assert drop_is_replace(Qt.NoModifier, action, modifier) is False
    assert drop_is_replace(Qt.ShiftModifier, action, modifier) is True
    assert drop_is_replace(Qt.ControlModifier, action, modifier) is False
    assert (
        drop_is_replace(Qt.ShiftModifier | Qt.ControlModifier, action, modifier) is True
    )


def test_drop_is_replace_insert_ctrl_or_alt():
    action = DropAction.INSERT
    assert drop_is_replace(Qt.ControlModifier, action, Qt.ControlModifier) is True
    assert drop_is_replace(Qt.ShiftModifier, action, Qt.ControlModifier) is False
    assert drop_is_replace(Qt.AltModifier, action, Qt.AltModifier) is True
    assert drop_is_replace(Qt.ShiftModifier, action, Qt.AltModifier) is False


def test_drop_is_replace_replace_default_inverts_modifier():
    action = DropAction.REPLACE
    modifier = Qt.ShiftModifier
    assert drop_is_replace(Qt.NoModifier, action, modifier) is True
    assert drop_is_replace(Qt.ShiftModifier, action, modifier) is False


def test_drop_is_replace_none_ignores_keys():
    assert drop_is_replace(Qt.ShiftModifier, DropAction.INSERT, None) is False
    assert drop_is_replace(Qt.NoModifier, DropAction.REPLACE, None) is True
    assert drop_is_replace(Qt.ControlModifier, DropAction.REPLACE, None) is True


class _Ctx:
    def __init__(self):
        self.is_drag_ui = False
        self.grid_state = SimpleNamespace(mode=None)
        self.commands = SimpleNamespace(
            get_video_block_at=lambda *_a, **_k: None,
            get_cell_at=lambda *_a, **_k: None,
            update_active_under_mouse=lambda: None,
            activate_window=lambda: None,
            get_video_block_under_mouse=lambda: object(),
            is_pan_press=lambda _event: False,
        )


def _make_manager():
    parent = QWidget()
    manager = DragNDropManager(context=_Ctx(), parent=parent)
    return manager, parent


def _left_press():
    return QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(10, 20),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.ControlModifier,
    )


def test_a_left_press_is_the_start_of_moving_the_video(mocker):
    manager, _parent = _make_manager()
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
    )

    manager.mousePressEvent(_left_press())

    assert manager._drag_start_position == QPoint(10, 20)


def test_a_press_that_drags_the_picture_moves_no_video(mocker):
    """A drag the picture is moved about with: see PanManager."""

    manager, _parent = _make_manager()
    manager._ctx.commands.is_pan_press = lambda _event: True
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
    )

    manager.mousePressEvent(_left_press())

    assert manager._drag_start_position is None


def test_linux_uses_fake_drag_by_default(mocker):
    manager, _parent = _make_manager()
    mocker.patch("gridplayer.player.managers.drag_n_drop.env.IS_LINUX", True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
    )
    mocker.patch.object(manager, "_is_drag_started", return_value=True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.Settings"
    ).return_value.get.return_value = False
    start_fake = mocker.patch.object(manager, "_start_fake_drag")
    make_qdrag = mocker.patch.object(manager, "_make_qdrag")

    assert manager.mouseMoveEvent(_mouse_move()) is True
    start_fake.assert_called_once()
    make_qdrag.assert_not_called()


def test_linux_force_native_drag_uses_qdrag(mocker):
    manager, _parent = _make_manager()
    manager._ctx.active_block = object()
    mocker.patch("gridplayer.player.managers.drag_n_drop.env.IS_LINUX", True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
    )
    mocker.patch.object(manager, "_is_drag_started", return_value=True)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.Settings"
    ).return_value.get.return_value = True
    start_fake = mocker.patch.object(manager, "_start_fake_drag")
    drag = mocker.Mock()
    mocker.patch.object(manager, "_make_qdrag", return_value=drag)
    mocker.patch.object(manager, "_ensure_drag_ui")
    mocker.patch.object(manager, "_set_source")
    mocker.patch.object(manager, "_end_drag_ui")

    manager.mouseMoveEvent(_mouse_move())

    start_fake.assert_not_called()
    drag.exec.assert_called_once()


def test_fake_drag_mouse_move_does_not_use_event_keyboard_modifiers(mocker):
    """Qt5 QMouseEvent has modifiers(), not keyboardModifiers() — that used to crash."""
    manager, _parent = _make_manager()
    manager._is_fake_drag_active = True
    manager._ctx.is_drag_ui = True
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.ShiftModifier
    )

    assert manager.mouseMoveEvent(_mouse_move()) is True


def test_fake_drag_key_press_shift_does_not_use_event_keyboard_modifiers(mocker):
    manager, _parent = _make_manager()
    manager._is_fake_drag_active = True
    manager._ctx.is_drag_ui = True
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.ShiftModifier
    )

    assert manager.keyPressEvent(_key_press(Qt.Key_Shift, Qt.ShiftModifier)) is True


def _patch_drop_settings(
    mocker,
    internal=DropAction.INSERT,
    external=DropAction.INSERT,
    modifier=Qt.ShiftModifier,
):
    mocker.patch(
        "gridplayer.playlist_settings.Settings"
    ).return_value.get.side_effect = lambda key: {
        "playlist/drop_action_internal": internal,
        "playlist/drop_action_external": external,
    }[key]
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.drop_switch_modifier",
        return_value=modifier,
    )


def test_is_replace_reads_os_keyboard_state(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(mocker)
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.query_drop_modifiers",
        return_value=Qt.NoModifier,
    )
    assert manager._is_replace(True) is False
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.query_drop_modifiers",
        return_value=Qt.ShiftModifier,
    )
    assert manager._is_replace(True) is True


def test_is_replace_uses_dnd_move_action_as_shift(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.NoModifier
    )
    event = SimpleNamespace(
        keyboardModifiers=lambda: Qt.NoModifier,
        proposedAction=lambda: Qt.MoveAction,
        possibleActions=lambda: Qt.CopyAction | Qt.MoveAction,
        mimeData=lambda: SimpleNamespace(
            hasFormat=lambda fmt: fmt == "text/uri-list",
            hasUrls=lambda: True,
        ),
    )
    assert manager._is_replace(False, event) is True


def test_is_replace_uses_event_modifiers_when_query_empty(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(mocker)
    mocker.patch.object(
        QApplication, "queryKeyboardModifiers", return_value=Qt.NoModifier
    )
    event = SimpleNamespace(keyboardModifiers=lambda: Qt.ShiftModifier)
    assert manager._is_replace(True, event) is True
    assert manager._is_replace(True) is False


def test_is_replace_internal_and_external_use_separate_defaults(mocker):
    manager, _parent = _make_manager()
    _patch_drop_settings(
        mocker, internal=DropAction.REPLACE, external=DropAction.INSERT
    )
    mocker.patch(
        "gridplayer.player.managers.drag_n_drop.query_drop_modifiers",
        return_value=Qt.NoModifier,
    )
    assert manager._is_replace(True) is True
    assert manager._is_replace(False) is False


def _file_drag_event():
    return SimpleNamespace(
        mimeData=lambda: SimpleNamespace(
            hasFormat=lambda fmt: fmt == "text/uri-list",
            hasUrls=lambda: True,
            urls=lambda: [
                SimpleNamespace(
                    isLocalFile=lambda: False,
                    url=lambda: "http://example.com/video.mp4",
                )
            ],
            hasText=lambda: False,
            formats=lambda: ["text/uri-list"],
        ),
        acceptProposedAction=lambda: None,
        pos=lambda: QPoint(1, 1),
        keyboardModifiers=lambda: Qt.NoModifier,
        proposedAction=lambda: Qt.CopyAction,
        possibleActions=lambda: Qt.CopyAction,
    )


def test_drag_leave_ends_drag_ui_after_event_loop(mocker):
    manager, _parent = _make_manager()
    manager._ctx.is_drag_ui = True
    mocker.patch.object(manager, "_is_pointer_over_player", return_value=False)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))

    assert ended == []
    assert manager._drag_leave_timer.isActive()

    # at once everywhere but Linux, where X11 is given a grace period
    deadline = time.monotonic() + 2
    while not ended and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)

    assert ended == [False]
    assert not manager._drag_leave_timer.isActive()


def test_drag_leave_while_over_player_keeps_drag_ui(mocker):
    manager, _parent = _make_manager()
    manager._ctx.is_drag_ui = True
    mocker.patch.object(manager, "_is_pointer_over_player", return_value=True)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))
    QApplication.processEvents()

    assert ended == []


def test_drag_enter_after_leave_keeps_drag_ui(mocker):
    manager, parent = _make_manager()
    manager._ctx.is_drag_ui = True
    _patch_drop_settings(mocker)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))
    assert manager._drag_leave_timer.isActive()

    assert manager.dragEnterEvent(_file_drag_event(), parent) is True
    assert not manager._drag_leave_timer.isActive()

    QApplication.processEvents()

    assert ended == []


def test_fake_drag_leave_does_not_end_drag_ui(mocker):
    manager, _parent = _make_manager()
    manager._ctx.is_drag_ui = True
    manager._is_fake_drag_active = True
    mocker.patch.object(manager, "_is_pointer_over_player", return_value=False)
    ended = []
    manager.set_drag_ui.connect(ended.append)

    manager.dragLeaveEvent(QEvent(QEvent.DragLeave))
    QApplication.processEvents()

    assert ended == []
    assert not manager._drag_leave_timer.isActive()


def test_fake_drag_released_moves_the_cell_it_started_on():
    """Linux drags a cell without QDrag: let go, it is put where it was
    over, the way a QDrag drop puts it."""

    manager, _parent = _make_manager()
    source, target = (
        SimpleNamespace(set_drop_indicator=lambda _indicator: None) for _ in range(2)
    )
    dropped = []
    manager._ctx.commands.layout_drop = lambda *args: dropped.append(args)
    manager._ctx.commands.add_recent_videos = lambda _videos: None
    manager._is_fake_drag_active = True
    manager._source_block = source
    manager._drop_block = target
    manager._drop_zone = DropZone.BEFORE
    manager._drop_is_replace = True

    manager.mouseReleaseEvent(
        QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(1, 1),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
    )

    assert dropped == [([], source, target, DropZone.BEFORE, True)]
    assert not manager._is_fake_drag_active


class TestADropFromAnotherInstance:
    """A cell dragged over from another window comes with its bookmarks,
    kept by the playlist apart from the video."""

    def _drop(self, tmp_path, is_taken, media_list=None, lists=None):
        from gridplayer.models.bookmark import Bookmark
        from gridplayer.models.video import Video, VideoBlockMime
        from gridplayer.player.managers.bookmarks import BookmarksRegistry
        from gridplayer.player.managers.lists import MediaListsRegistry

        (tmp_path / "movie.mkv").touch()
        video = Video(
            uri=tmp_path / "movie.mkv",
            list_id=None if media_list is None else media_list.id,
        )
        bookmarks = (Bookmark(time_ms=30000, name="Goal"),)
        placed = {}

        ctx = _Ctx()
        ctx.bookmarks = BookmarksRegistry()
        ctx.lists = lists if lists is not None else MediaListsRegistry()
        ctx.video_blocks = SimpleNamespace(
            by_id=lambda _id: None,
            by_video_id=lambda _id: placed.get(str(_id)),
        )

        def layout_drop(videos, *_args):
            if is_taken:
                placed[str(videos[0].id)] = object()

        ctx.commands.layout_drop = layout_drop
        ctx.commands.add_recent_videos = lambda _videos: None

        # the parent kept alive while it drops
        manager, _parent = _make_manager()
        manager._ctx = ctx

        # as it comes over: in text, from another process, its list apart
        mime_data = QMimeData()
        mime_data.setData(
            VIDEO_MIME,
            VideoBlockMime(id="other", video=video, bookmarks=bookmarks)
            .model_dump_json()
            .encode(),
        )
        if media_list is not None:
            mime_data.setData(LIST_MIME, media_list.model_dump_json().encode())

        dropped, dropped_list = manager._dropped_video(mime_data)
        manager._drop_video_block(dropped, dropped_list, None, None, False)

        self.ctx = ctx
        self.dropped = dropped

        return ctx.bookmarks, dropped.video, bookmarks

    def test_its_bookmarks_come_with_it(self, tmp_path):
        registry, video, bookmarks = self._drop(tmp_path, is_taken=True)

        assert registry.get(video.uri, video.id) == bookmarks

    def test_turned_away_by_a_full_grid_it_leaves_none(self, tmp_path):
        registry, _video, _bookmarks = self._drop(tmp_path, is_taken=False)

        assert registry.entries() == []

    def test_its_file_is_a_file_here_too(self, tmp_path):
        _registry, video, _bookmarks = self._drop(tmp_path, is_taken=True)

        assert video.uri == tmp_path / "movie.mkv"
        assert video.is_local_file

    def test_the_list_it_plays_from_comes_with_it(self, tmp_path):
        from gridplayer.models.media_list import ListItem, MediaList

        media_list = MediaList(
            name="Channels", items=[ListItem(uri=tmp_path / "movie.mkv")]
        )

        _registry, video, _bookmarks = self._drop(
            tmp_path, is_taken=True, media_list=media_list
        )

        here = self.ctx.lists.get(video.list_id)
        assert here.name == "Channels"
        assert here.items[0].uri == tmp_path / "movie.mkv"

    def test_under_an_id_of_its_own_where_it_is_taken(self, tmp_path):
        from gridplayer.models.media_list import ListItem, MediaList
        from gridplayer.player.managers.lists import MediaListsRegistry

        lists = MediaListsRegistry()
        mine = lists.add(MediaList(name="Mine"))
        theirs = MediaList(id=mine.id, name="Theirs", items=[ListItem(uri="x://y")])

        _registry, video, _bookmarks = self._drop(
            tmp_path, is_taken=True, media_list=theirs, lists=lists
        )

        assert video.list_id != mine.id
        assert lists.get(mine.id).name == "Mine"
        assert lists.get(video.list_id).name == "Theirs"

    def test_a_list_read_from_a_file_or_a_folder_comes_too(self, tmp_path):
        from gridplayer.models.media_list import ListItem, ListSource, MediaList
        from gridplayer.params.static import ListSourceKind

        media_list = MediaList(
            name="Channels",
            items=[ListItem(uri=tmp_path / "movie.mkv"), ListItem(uri="http://tv/1")],
            source=ListSource(kind=ListSourceKind.FOLDER, location=tmp_path),
            removed=(tmp_path / "gone.mkv", "http://tv/2"),
        )

        _registry, video, _bookmarks = self._drop(
            tmp_path, is_taken=True, media_list=media_list
        )

        here = self.ctx.lists.get(video.list_id)
        assert here.source.location == tmp_path
        assert here.removed == (tmp_path / "gone.mkv", "http://tv/2")
        assert [item.uri for item in here.items] == [
            tmp_path / "movie.mkv",
            "http://tv/1",
        ]

    def test_turned_away_its_list_is_not_kept(self, tmp_path):
        from gridplayer.models.media_list import MediaList

        self._drop(tmp_path, is_taken=False, media_list=MediaList(name="Channels"))

        assert self.ctx.lists.lists() == []


class TestAWindowOverThePlayer:
    """The List window, open beside the player and over a video: its mouse
    and its drops are its own."""

    @pytest.fixture
    def manager(self, mocker):
        mocker.patch(
            "gridplayer.player.managers.drag_n_drop.is_modal_open", return_value=False
        )
        manager, self.player = _make_manager()
        self.activated = []
        manager._ctx.commands.activate_window = lambda: self.activated.append(True)
        self.window = QDialog(self.player)
        return manager

    def test_a_press_there_moves_no_video_and_keeps_its_focus(self, manager):
        field = QLineEdit(self.window)

        assert manager.eventFilter(field, _left_press()) is False

        assert manager._drag_start_position is None
        assert self.activated == []

    def test_seen_at_its_window_first_too(self, manager):
        self.window.winId()

        manager.eventFilter(self.window.windowHandle(), _left_press())

        assert manager._drag_start_position is None
        assert self.activated == []

    def test_what_is_dropped_there_is_its_own(self, manager, mocker):
        finish = mocker.patch.object(manager, "_finish_drop")
        data = QMimeData()
        data.setText("http://tv/1")
        drop = QDropEvent(
            QPointF(5, 5), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier
        )

        assert manager.eventFilter(QWidget(self.window), drop) is False
        QApplication.processEvents()

        finish.assert_not_called()
        assert not drop.isAccepted()

    def test_the_player_s_own_still_moves_the_video(self, manager):
        manager.eventFilter(QWidget(self.player), _left_press())

        assert manager._drag_start_position == QPoint(10, 20)
        assert self.activated == [True]

    def test_a_drag_gone_on_to_it_is_off_the_player(self, manager, mocker):
        mocker.patch("gridplayer.player.managers.drag_n_drop.env.IS_LINUX", False)
        mocker.patch.object(QApplication, "topLevelAt", return_value=self.window)
        self.player.setGeometry(0, 0, 4000, 4000)

        assert manager._is_pointer_over_player() is False


class _ListCell:
    def __init__(self, media_list):
        self.media_list = media_list
        self.shown = []

    def set_drop_indicator(self, indicator):
        self.shown.append(indicator)


def _dragged(mime):
    return SimpleNamespace(mimeData=lambda: mime)


def _files():
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/videos/a.mp4")])
    return _dragged(mime)


class TestTheMarkOverACellPlayingAList:
    @pytest.fixture
    def shown(self, mocker):
        def _shown(media_list, zone, event, is_internal=False, is_replace=False):
            manager, _parent = _make_manager()
            cell = _ListCell(media_list)
            mocker.patch.object(manager, "_hover_at", return_value=(cell, zone))
            mocker.patch.object(manager, "_is_replace", return_value=is_replace)

            manager._update_drop_target(QPoint(), is_internal=is_internal, event=event)

            return cell.shown[-1]

        return _shown

    def test_files_in_its_middle_go_on_its_list(self, shown):
        assert shown(MediaList(), DropZone.CENTER, _files()) == (
            DropIndicator.ADD_TO_LIST
        )

    def test_at_its_edge_in_a_cell_of_their_own(self, shown):
        assert shown(MediaList(), DropZone.AFTER, _files()) == DropIndicator.ARROW_RIGHT

    def test_to_replace_its_video(self, shown):
        assert (
            shown(MediaList(), DropZone.CENTER, _files(), is_replace=True)
            == DropIndicator.REPLACE
        )

    def test_not_for_a_linked_list(self, shown):
        linked = MediaList(
            source=ListSource(kind=ListSourceKind.URL, location="http://tv/l"),
            is_linked=True,
        )

        assert shown(linked, DropZone.CENTER, _files()) == DropIndicator.DOT

    def test_not_for_a_cell_from_another_player(self, shown):
        mime = QMimeData()
        mime.setData(VIDEO_MIME, b"{}")

        assert shown(MediaList(), DropZone.CENTER, _dragged(mime)) == (
            DropIndicator.DOT
        )

    def test_not_for_a_cell_of_this_one(self, shown):
        assert (
            shown(MediaList(), DropZone.CENTER, _files(), is_internal=True)
            == DropIndicator.SWAP
        )
