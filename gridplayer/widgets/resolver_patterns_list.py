from typing import Optional

from PyQt5 import QtWidgets
from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QDropEvent

from gridplayer.models.resolver_patterns import (
    ResolverPattern,
    ResolverPatterns,
    ResolverPatternType,
)
from gridplayer.params.static import URLResolver
from gridplayer.utils.qt import translate


def _set_combo_box(combo_box, data_value):
    idx = combo_box.findData(data_value)
    combo_box.setCurrentIndex(idx)


class RowDropIndicatorStyle(QtWidgets.QProxyStyle):
    """
    Draws drop indicator for the whole row
    """

    def drawPrimitive(self, element, option, painter, widget=None):
        is_indicator = element == QtWidgets.QStyle.PE_IndicatorItemViewItemDrop

        if is_indicator and not option.rect.isNull():
            option.rect.setLeft(0)
            if widget:
                option.rect.setWidth(widget.width())
            option.rect.setHeight(1)

        super().drawPrimitive(element, option, painter, widget)


class TableWidgetDragRows(QtWidgets.QTableWidget):
    is_something_selected = pyqtSignal(bool)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.ui_init()

        self.itemSelectionChanged.connect(self._on_selection_changed)

    def ui_init(self):  # noqa: WPS213
        self.setStyle(RowDropIndicatorStyle())

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)

        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)

        self.verticalHeader().hide()

    @property
    def selected_row_ids(self):
        return sorted({t_item.row() for t_item in self.selectedItems()})

    @property
    def header_view(self):
        return self.horizontalHeader()

    def dropEvent(self, event: QDropEvent):
        if event.isAccepted() or event.source() != self:
            return super().dropEvent(event)

        drop_row = self._drop_on(event)

        self._move_selected_to(drop_row)

        event.accept()

    def set_current_row_idx(self, row_idx):
        self.setCurrentItem(self.item(row_idx, 0))

    def remove_selected(self):
        for row_index in reversed(self.selected_row_ids):
            self.removeRow(row_index)

    def move_selected_up(self):
        if not self.selected_row_ids:
            return

        cur_idx = self.selected_row_ids[0]
        move_to_idx = max(cur_idx - 1, 0)

        if cur_idx == move_to_idx:
            return

        self._move_selected_to(move_to_idx)

    def move_selected_down(self):
        if not self.selected_row_ids:
            return

        cur_idx = self.selected_row_ids[-1] + 1
        move_to_idx = min(cur_idx + 1, self.rowCount())

        if cur_idx == move_to_idx:
            return

        self._move_selected_to(move_to_idx)

    def add_new_row(self) -> int:
        self.insertRow(self.rowCount())
        return self.rowCount() - 1

    def _on_selection_changed(self):
        self.is_something_selected.emit(bool(self.selected_row_ids))

    def _move_selected_to(self, dst_row_idx):
        rows_to_move = self._take_selected_rows()

        self._insert_rows_after(rows_to_move, dst_row_idx)

        self._remove_empty_rows()

        self._set_current_rows(rows_to_move)

    def _take_selected_rows(self):
        return [
            [
                {
                    "item": self.takeItem(row_index, column_index),
                    "widget": self.cellWidget(row_index, column_index),
                }
                for column_index in range(self.columnCount())
            ]
            for row_index in self.selected_row_ids
        ]

    def _insert_rows_after(self, rows, dst_row_idx):
        for row_idx, row in enumerate(rows, dst_row_idx):
            self.insertRow(row_idx)
            for column_idx, column in enumerate(row):
                self.setItem(row_idx, column_idx, column["item"])
                if column["widget"]:
                    self.setCellWidget(row_idx, column_idx, column["widget"])

    def _remove_empty_rows(self):
        empty_rows = [
            row_idx for row_idx in range(self.rowCount()) if not self.item(row_idx, 0)
        ]
        for row_idx in reversed(empty_rows):
            self.removeRow(row_idx)

    def _set_current_rows(self, rows):
        for row_idx, row in enumerate(rows):
            if row_idx == 0:
                self.setCurrentItem(row[0]["item"])

            for col in row:
                col["item"].setSelected(True)

    def _drop_on(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            return self.rowCount()

        if self._is_below(event.pos(), index):
            return index.row() + 1

        return index.row()

    def _is_below(self, pos, index):
        rect = self.visualRect(index)
        margin = 2
        if pos.y() - rect.top() < margin:
            return False
        elif rect.bottom() - pos.y() < margin:
            return True

        return (
            rect.contains(pos, True)
            and not (int(self.model().flags(index)) & Qt.ItemIsDropEnabled)
            and pos.y() >= rect.center().y()
        )


class ResolverPatternsList(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.table = self.ui_table()
        self.buttons = self.ui_buttons()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addLayout(self.buttons)
        layout.addWidget(self.table)

    def ui_table(self):
        table = TableWidgetDragRows(parent=self)
        table.setColumnCount(3)

        table.setHorizontalHeaderLabels(
            [
                translate("SettingsDialog", "Pattern"),
                translate("SettingsDialog", "Pattern Type"),
                translate("SettingsDialog", "Resolver"),
            ]
        )

        table.header_view.setDefaultAlignment(Qt.AlignLeft)
        table.header_view.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for col_idx in range(1, table.columnCount()):
            table.header_view.setSectionResizeMode(col_idx, QtWidgets.QHeaderView.Fixed)
            table.header_view.resizeSection(col_idx, 100)

        return table

    def ui_buttons(self):
        buttons = QtWidgets.QHBoxLayout()

        buttons.addWidget(self._create_button("+", self.add_row, False))
        buttons.addWidget(self._create_button("-", self.table.remove_selected))
        buttons.addWidget(self._create_button("▲", self.table.move_selected_up))
        buttons.addWidget(self._create_button("▼", self.table.move_selected_down))

        buttons.addStretch()

        return buttons

    @property
    def empty_row_idx(self):
        return next(
            (
                row_idx
                for row_idx, row in enumerate(self.rows_data())
                if row.pattern == ""
            ),
            None,
        )

    def rows_data(self) -> ResolverPatterns:
        return ResolverPatterns(
            __root__=[
                ResolverPattern(
                    pattern=self.table.item(row_idx, 0).text(),
                    pattern_type=self.table.cellWidget(row_idx, 1).currentData(),
                    resolver=self.table.cellWidget(row_idx, 2).currentData(),
                )
                for row_idx in range(self.table.rowCount())
            ]
        )

    def setDataRows(self, data_rows: ResolverPatterns):
        for row in data_rows:
            self.add_row(row)

    def add_row(self, row_data: Optional[ResolverPattern] = None):
        if self.empty_row_idx is not None:
            self.table.set_current_row_idx(self.empty_row_idx)
            return

        row_idx = self.table.add_new_row()

        self._init_row(row_idx)

        if row_data:
            self._set_row_data(row_idx, row_data)

        self.table.setCurrentItem(self.table.item(row_idx, 0))

        self.table.resizeColumnToContents(1)
        self.table.resizeColumnToContents(2)

    def _init_row(self, row_idx: int):
        columns = [
            QtWidgets.QTableWidgetItem("") for _ in range(self.table.columnCount())
        ]

        for col_idx, col in enumerate(columns):
            if col_idx > 0:
                col.setFlags(col.flags() ^ Qt.ItemIsEditable)

            # allow drop only in between rows
            col.setFlags(col.flags() ^ Qt.ItemIsDropEnabled)

            self.table.setItem(row_idx, col_idx, col)

            if col_idx == 1:
                self.table.setCellWidget(
                    row_idx, col_idx, self._create_pattern_type_combo()
                )
            elif col_idx == 2:
                self.table.setCellWidget(
                    row_idx, col_idx, self._create_resolver_combo()
                )

    def _set_row_data(self, row_idx, row_data: ResolverPattern):
        self.table.item(row_idx, 0).setText(row_data.pattern)
        _set_combo_box(self.table.cellWidget(row_idx, 1), row_data.pattern_type)
        _set_combo_box(self.table.cellWidget(row_idx, 2), row_data.resolver)

    def _create_button(self, text, callback, is_selection_needed=True):
        button = QtWidgets.QPushButton(text)
        button.setFixedSize(QSize(24, 24))
        button.clicked.connect(callback)
        if is_selection_needed:
            button.setEnabled(False)
            self.table.is_something_selected.connect(button.setEnabled)
        return button

    def _create_pattern_type_combo(self):
        patterns = {
            ResolverPatternType.WILDCARD_HOST: translate(
                "SettingsDialog - Resolver Pattern Type", "Host Wildcard"
            ),
            ResolverPatternType.WILDCARD_URL: translate(
                "SettingsDialog - Resolver Pattern Type", "URL Wildcard"
            ),
            ResolverPatternType.REGEX: translate(
                "SettingsDialog - Resolver Pattern Type", "URL Regex"
            ),
            ResolverPatternType.DISABLED: translate(
                "SettingsDialog - Resolver Pattern Type", "Disabled"
            ),
        }

        combo = QtWidgets.QComboBox(self)
        for pattern_id, pattern_name in patterns.items():
            combo.addItem(pattern_name, pattern_id)

        return combo

    def _create_resolver_combo(self):
        resolvers = {
            URLResolver.STREAMLINK: "Streamlink",
            URLResolver.YT_DLP: "yt-dlp",
            URLResolver.DIRECT: translate("SettingsDialog", "Direct"),
        }

        combo = QtWidgets.QComboBox(self)
        for resolver_id, resolver_name in resolvers.items():
            combo.addItem(resolver_name, resolver_id)

        return combo
