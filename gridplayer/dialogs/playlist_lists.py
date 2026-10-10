"""Every list the playlist keeps: to see what is there and which cells play
what, to open a list in a cell, edit it, copy it, save it for other players,
and to clear away the lists no cell plays.

Removals and copies are made as they go, and Cancel takes them back. What is
done in a list's own window is that window's, and stays.
"""

import contextlib
from collections.abc import Callable
from enum import IntEnum
from uuid import UUID

from PyQt5.QtCore import QPoint, QSize, Qt, QTimer
from PyQt5.QtGui import (
    QContextMenuEvent,
    QPainter,
    QPalette,
    QStandardItem,
    QStandardItemModel,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeView,
    QVBoxLayout,
)

from gridplayer.dialogs.bookmarks import (
    ROW_HEIGHT,
    STATUS_MS,
    dialog_button,
    paint_empty_txt,
)
from gridplayer.dialogs.media_list import export_m3u
from gridplayer.models.media_list import MediaList
from gridplayer.params.static import ListSourceKind
from gridplayer.utils.qt import count_txt, translate
from gridplayer.widgets.custom_menu import CustomMenu

DIALOG_SIZE = QSize(660, 470)
DIALOG_MIN_SIZE = QSize(520, 340)

LIST_ID_ROLE = Qt.UserRole


class Column(IntEnum):
    NAME = 0
    ITEMS = 1
    SOURCE = 2
    CELLS = 3


class _ListRows(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self.setStyleSheet(
            f"""
            QTreeView::item {{
                height: {ROW_HEIGHT}px;
                padding-left: 4px;
                padding-right: 8px;
            }}
            """
        )

        self.empty_txt = ("", "")
        self.menu_handler = None
        self.delete_handler = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.delete_handler is not None:
            self.delete_handler()
            event.accept()
            return

        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        if event.reason() == QContextMenuEvent.Keyboard:
            index = self.currentIndex()
            pos = self.visualRect(index).bottomLeft() if index.isValid() else QPoint()
        else:
            index = self.indexAt(event.pos())
            pos = event.pos()
            if index.isValid():
                self.setCurrentIndex(index)

        if index.isValid() and self.menu_handler is not None:
            self.menu_handler(self.viewport().mapToGlobal(pos))

        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.model() is None or self.model().rowCount():
            return

        painter = QPainter(self.viewport())
        paint_empty_txt(self, painter, *self.empty_txt)
        painter.end()


class PlaylistListsDialog(QDialog):
    def __init__(
        self,
        registry,
        cells: Callable[[], list],
        edit_list: Callable,
        open_in_new_cell: Callable,
        parent=None,
    ):
        """The registry's lists. cells tells the cells open, first to last
        in the grid; edit_list(list_id) opens a list's own window, and
        open_in_new_cell(list_id, place) plays it in a new cell."""

        super().__init__(parent)

        self._registry = registry
        self._cells = cells
        self._edit_list = edit_list
        self._open_in_new_cell = open_in_new_cell

        # what was removed here, for Cancel to put back as it was, with
        # whether a cell had played from it; and what was added
        self._removed: dict[UUID, tuple[MediaList, bool]] = {}
        self._added: set = set()

        self.setWindowTitle(
            translate("Dialog - Playlist lists", "Lists in Playlist", "Header")
        )
        self.setMinimumSize(DIALOG_MIN_SIZE)
        self.resize(DIALOG_SIZE)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(STATUS_MS)
        self._status_timer.timeout.connect(self._show_count)

        self._ui_setup()
        self._ui_connect()

        self._reload()
        self._show_count()

        self._list.setFocus()

    def _ui_setup(self):
        self._model = QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(
            [
                translate("Dialog - Playlist lists", "List"),
                translate("Dialog - Playlist lists", "Items"),
                translate("Dialog - Playlist lists", "From"),
                translate("Dialog - Playlist lists", "Cells"),
            ]
        )

        self._list = _ListRows()
        self._list.setModel(self._model)
        self._list.empty_txt = (
            translate("Dialog - Playlist lists", "No lists in this playlist"),
            translate(
                "Dialog - Playlist lists",
                "Folders and playlist files you add play as lists. To make one in any"
                " cell, use List… in its Playback menu.",
            ),
        )
        self._list.menu_handler = self._show_row_menu
        self._list.delete_handler = self._remove

        header = self._list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(Column.NAME, QHeaderView.Stretch)
        for column in (Column.ITEMS, Column.SOURCE, Column.CELLS):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        self._hint = QLabel()
        self._hint.setWordWrap(True)

        self._open_button = dialog_button(
            "add", translate("Dialog - Playlist lists", "Open in a New Cell")
        )
        self._edit_button = dialog_button(
            "list", translate("Dialog - Playlist lists", "Edit…")
        )
        self._duplicate_button = dialog_button(
            "copy", translate("Dialog - Playlist lists", "Duplicate")
        )
        self._export_button = dialog_button(
            "save-playlist", translate("Dialog - Playlist lists", "Export…")
        )
        self._remove_button = dialog_button(
            "close", translate("Dialog - Playlist lists", "Remove")
        )
        self._remove_unused_button = dialog_button(
            "close-playlist",
            translate("Dialog - Playlist lists", "Remove Unused"),
            translate(
                "Dialog - Playlist lists", "Remove every list that no cell plays"
            ),
        )

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(self._open_button)
        tools.addWidget(self._edit_button)
        tools.addWidget(self._duplicate_button)
        tools.addStretch(1)
        tools.addWidget(self._export_button)
        tools.addWidget(self._remove_button)

        bottom = QHBoxLayout()
        bottom.addWidget(self._remove_unused_button)
        bottom.addStretch(1)
        bottom.addWidget(self._buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(10)
        root.addWidget(self._list, 1)
        root.addSpacing(-4)
        root.addWidget(self._hint)
        root.addLayout(tools)
        root.addSpacing(4)
        root.addLayout(bottom)

    def _ui_connect(self):
        self._list.selectionModel().currentChanged.connect(self._update_buttons)
        self._list.doubleClicked.connect(lambda _index: self._edit())

        self._open_button.clicked.connect(self._open)
        self._edit_button.clicked.connect(self._edit)
        self._duplicate_button.clicked.connect(self._duplicate)
        self._export_button.clicked.connect(self._export)
        self._remove_button.clicked.connect(self._remove)
        self._remove_unused_button.clicked.connect(self._remove_unused)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

    def reject(self):
        # all but one opened in a new cell meanwhile, played there now
        in_use = self._in_use()

        for list_id in self._added - in_use:
            with contextlib.suppress(KeyError):
                self._registry.remove(list_id)

        for media_list, is_taken_up in self._removed.values():
            self._registry.put(media_list)

            if is_taken_up:
                self._registry.take_up(media_list.id)

        super().reject()

    # showing the lists

    def _cell_numbers(self) -> dict:
        numbers = {}

        for number, block in enumerate(self._cells(), 1):
            params = block.video_params

            if params is not None and params.list_id is not None:
                numbers.setdefault(params.list_id, []).append(number)

        return numbers

    def _reload(self, current_id=None):
        if current_id is None:
            current_id = self._current_id()

        numbers = self._cell_numbers()

        self._model.removeRows(0, self._model.rowCount())

        dim = self._list.palette().color(QPalette.PlaceholderText)

        for media_list in self._registry.lists():
            cells = numbers.get(media_list.id)

            name_item = QStandardItem(
                media_list.name or translate("Dialog - Playlist lists", "Untitled")
            )
            name_item.setData(media_list.id, LIST_ID_ROLE)

            count_item = QStandardItem(count_txt(len(media_list.items)))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            source_item = QStandardItem(_source_txt(media_list))
            if media_list.source is not None:
                source_item.setToolTip(str(media_list.source.location))

            if cells:
                cells_item = QStandardItem(", ".join(map(str, cells)))
            else:
                cells_item = QStandardItem(translate("Dialog - Playlist lists", "none"))
                cells_item.setForeground(dim)
                cells_item.setToolTip(
                    translate(
                        "Dialog - Playlist lists",
                        "No cell plays it. It will be removed when the playlist is"
                        " saved.",
                    )
                    if self._registry.is_taken_up(media_list.id)
                    else translate(
                        "Dialog - Playlist lists",
                        "Its cells didn't open. It stays in the playlist.",
                    )
                )
            cells_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self._model.appendRow([name_item, count_item, source_item, cells_item])

        self._pick(current_id)
        self._update_buttons()

    def _pick(self, list_id):
        row = self._row_of(list_id)

        if row is None and self._model.rowCount():
            row = 0

        if row is not None:
            self._list.setCurrentIndex(self._model.index(row, 0))

    def _row_of(self, list_id):
        for row in range(self._model.rowCount()):
            if self._model.item(row, 0).data(LIST_ID_ROLE) == list_id:
                return row

        return None

    def _current_id(self):
        index = self._list.currentIndex()

        if not index.isValid():
            return None

        return self._model.item(index.row(), 0).data(LIST_ID_ROLE)

    def _current(self) -> MediaList | None:
        return self._registry.get(self._current_id())

    def _in_use(self) -> set:
        return set(self._cell_numbers())

    def _show_count(self):
        lists = self._registry.lists()

        self._hint.setText(
            translate(
                "Dialog - Playlist lists", "Lists: {LISTS} · Items: {ITEMS}"
            ).format(
                LISTS=count_txt(len(lists)),
                ITEMS=count_txt(sum(len(media_list.items) for media_list in lists)),
            )
        )

    def _say(self, text: str):
        self._hint.setText(text)
        self._status_timer.start()

    def _update_buttons(self, *_):
        media_list = self._current()
        is_picked = media_list is not None
        is_in_use = is_picked and media_list.id in self._in_use()

        self._open_button.setEnabled(is_picked and bool(media_list.items))
        self._edit_button.setEnabled(is_picked)
        self._duplicate_button.setEnabled(is_picked)
        self._export_button.setEnabled(is_picked and bool(media_list.items))
        self._remove_button.setEnabled(is_picked and not is_in_use)
        self._remove_button.setToolTip(
            translate(
                "Dialog - Playlist lists",
                "A cell is playing it",
            )
            if is_in_use
            else ""
        )

        in_use = self._in_use()
        self._remove_unused_button.setEnabled(
            any(media_list.id not in in_use for media_list in self._registry.lists())
        )

    # what is done

    def _open(self):
        media_list = self._current()

        if media_list is None or not media_list.items:
            return

        self._open_in_new_cell(media_list.id, 0)

        self._reload()

    def _edit(self):
        media_list = self._current()

        if media_list is None:
            return

        self._edit_list(media_list.id)

        self._reload(media_list.id)
        self._show_count()

    def _duplicate(self):
        media_list = self._current()

        if media_list is None:
            return

        copy = self._registry.add(
            media_list.model_copy(
                update={
                    "id": MediaList().id,
                    "name": translate(
                        "Dialog - Playlist lists", "{NAME} (copy)"
                    ).format(
                        NAME=media_list.name
                        or translate("Dialog - Playlist lists", "Untitled")
                    ),
                }
            )
        )

        self._added.add(copy.id)

        self._reload(copy.id)
        self._say(translate("Dialog - Playlist lists", "Duplicated"))

    def _export(self):
        media_list = self._current()

        if media_list is None:
            return

        exported, error = export_m3u(self, media_list)

        if error is not None:
            self._say(
                translate("Dialog - List", "Could not be exported: {WHAT}").format(
                    WHAT=error
                )
            )
        elif exported is not None:
            self._say(
                translate("Dialog - List", "Exported: {FILE}").format(
                    FILE=exported.name
                )
            )

    def _remove(self):
        media_list = self._current()

        if media_list is None or media_list.id in self._in_use():
            return

        self._take_away([media_list])

    def _remove_unused(self):
        in_use = self._in_use()

        unused = [
            media_list
            for media_list in self._registry.lists()
            if media_list.id not in in_use
        ]

        if unused:
            self._take_away(unused)

    def _take_away(self, lists):
        for media_list in lists:
            is_taken_up = self._registry.is_taken_up(media_list.id)

            self._registry.remove(media_list.id)

            if media_list.id in self._added:
                self._added.discard(media_list.id)
            else:
                self._removed[media_list.id] = (media_list, is_taken_up)

        self._reload()
        self._say(
            translate("Dialog - Playlist lists", "Lists removed: {COUNT}").format(
                COUNT=count_txt(len(lists))
            )
        )

    def _show_row_menu(self, global_pos):
        menu = CustomMenu(parent=self)

        for button in (
            self._open_button,
            self._edit_button,
            self._duplicate_button,
            None,
            self._export_button,
            None,
            self._remove_button,
        ):
            if button is None:
                menu.addSeparator()
                continue

            action = menu.addAction(button.icon(), button.text(), button.click)
            action.setEnabled(button.isEnabled())

        menu.exec_(global_pos)
        menu.deleteLater()


def _source_txt(media_list: MediaList) -> str:
    source = media_list.source

    if source is None:
        return translate("Dialog - Playlist lists", "Added")

    kind = {
        ListSourceKind.FOLDER: translate("Dialog - Playlist lists", "Folder"),
        ListSourceKind.FILE: translate("Dialog - Playlist lists", "File"),
        ListSourceKind.URL: translate("Dialog - Playlist lists", "Link"),
    }[source.kind]

    # read again from it each time the playlist opens
    if media_list.is_linked:
        return translate("Dialog - Playlist lists", "{SOURCE}, linked").format(
            SOURCE=kind
        )

    return kind
