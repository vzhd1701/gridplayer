from datetime import datetime, timezone
from pathlib import Path

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QFileDialog

from gridplayer.utils.cookies import (
    CookieImportError,
    domain_summary,
    jar_or_none,
    merged_with,
    parse_cookies,
    without_domains,
)
from gridplayer.utils.qt import translate

DOMAIN_COLUMN = 0
COUNT_COLUMN = 1
EXPIRES_COLUMN = 2

COUNT_COLUMN_WIDTH = 70
EXPIRES_COLUMN_WIDTH = 170

# reads better than a hyphen between two dates that are full of them
EXPIRY_SPAN_DASH = chr(0x2013)


class CookieStoreList(QtWidgets.QWidget):
    """Where the cookie jar is looked at, added to and thinned out.

    Hosts and counts only, never a value: cookies are logins, and this page
    is as likely as any other to be read over somebody's shoulder.

    Nothing here touches the disk. What is shown is a jar of its own until
    the dialog is accepted, so Cancel undoes an import the way it undoes
    every other change in the dialog.
    """

    error = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._jar = None

        self.table = self.ui_table()
        self.summary = QtWidgets.QLabel()
        self.buttons = self.ui_buttons()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addLayout(self.buttons)
        layout.addWidget(self.table)
        layout.addWidget(self.summary)

        self.table.itemSelectionChanged.connect(self.refresh_buttons)

        self.set_jar(None)

    def ui_table(self):
        table = QtWidgets.QTableWidget(parent=self)
        table.setColumnCount(3)

        table.setHorizontalHeaderLabels(
            [
                translate("SettingsDialog", "Domain"),
                translate("SettingsDialog", "Cookies"),
                translate("SettingsDialog", "Expires"),
            ]
        )

        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.verticalHeader().hide()

        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft)
        header.setSectionResizeMode(DOMAIN_COLUMN, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(COUNT_COLUMN, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(EXPIRES_COLUMN, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(COUNT_COLUMN, COUNT_COLUMN_WIDTH)
        header.resizeSection(EXPIRES_COLUMN, EXPIRES_COLUMN_WIDTH)

        return table

    def ui_buttons(self):
        buttons = QtWidgets.QHBoxLayout()

        self.import_file_button = QtWidgets.QPushButton(
            translate("SettingsDialog", "Import from file...")
        )
        self.import_file_button.clicked.connect(self.import_from_file)

        self.paste_button = QtWidgets.QPushButton(
            translate("SettingsDialog", "Paste from clipboard")
        )
        self.paste_button.clicked.connect(self.import_from_clipboard)

        self.remove_button = QtWidgets.QPushButton(
            translate("SettingsDialog", "Remove")
        )
        self.remove_button.clicked.connect(self.remove_selected)

        self.clear_button = QtWidgets.QPushButton(
            translate("SettingsDialog", "Clear all")
        )
        self.clear_button.clicked.connect(self.clear)

        buttons.addWidget(self.import_file_button)
        buttons.addWidget(self.paste_button)
        buttons.addStretch()
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)

        return buttons

    @property
    def jar(self):
        """What the store would hold, were the dialog accepted now."""

        return self._jar

    @property
    def selected_domains(self) -> list[str]:
        rows = sorted({item.row() for item in self.table.selectedItems()})

        return [self.table.item(row, DOMAIN_COLUMN).text() for row in rows]

    def set_jar(self, jar) -> None:
        self._jar = jar_or_none(jar)

        self.refresh_table()

    def refresh_table(self) -> None:
        rows = domain_summary(self._jar)

        self.table.clearContents()
        self.table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            self._fill_row(row_idx, row)

        self.summary.setText(_summary_text(rows))

        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        self.remove_button.setEnabled(bool(self.table.selectedItems()))
        self.clear_button.setEnabled(self._jar is not None)

    def import_from_file(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            translate("SettingsDialog", "Open cookies file"),
            "",
            translate("SettingsDialog", "Cookies (*.txt *.json);;All files (*)"),
        )

        if not file_name:
            return

        try:
            text = _read_text(file_name)
        except OSError as e:
            self.error.emit(str(e))
            return

        self.import_text(text)

    def import_from_clipboard(self) -> None:
        self.import_text(QApplication.clipboard().text())

    def import_text(self, text: str) -> None:
        """Add whatever cookies are in this text to the ones already here."""

        try:
            incoming = parse_cookies(text)
        except CookieImportError as e:
            self.error.emit(str(e))
            return

        self.set_jar(merged_with(self._jar, incoming))

    def remove_selected(self) -> None:
        domains = self.selected_domains

        if not domains:
            return

        self.set_jar(without_domains(self._jar, domains))

    def clear(self) -> None:
        self.set_jar(None)

    def _fill_row(self, row_idx: int, row) -> None:
        cells = (
            (DOMAIN_COLUMN, row.domain),
            (COUNT_COLUMN, str(row.count)),
            (EXPIRES_COLUMN, _expiry_text(row)),
        )

        for column, text in cells:
            self.table.setItem(row_idx, column, QtWidgets.QTableWidgetItem(text))


def _read_text(file_name: str) -> str:
    # utf-8-sig so a byte order mark from a Windows export does not end up
    # glued to the first line the parser looks at
    return Path(file_name).read_text(encoding="utf-8-sig", errors="replace")


def _expiry_text(row) -> str:
    """Over what span this host's good cookies run out.

    An export carries the odd cookie that lapsed on the way out of the
    browser, so the span covers the ones still standing. Only when none of
    them is does the row say the whole host has gone off.
    """

    if row.expires_from is None:
        if row.is_expired:
            return translate("SettingsDialog - Cookies", "expired")

        return translate("SettingsDialog - Cookies", "session")

    first = _date_text(row.expires_from)
    last = _date_text(row.expires_to)

    if first == last:
        return first

    return f"{first} {EXPIRY_SPAN_DASH} {last}"


def _date_text(expires) -> str:
    # stored in UTC, read by somebody sitting in their own timezone
    lapses = datetime.fromtimestamp(expires, tz=timezone.utc).astimezone()

    return lapses.strftime("%Y-%m-%d")


def _summary_text(rows) -> str:
    if not rows:
        return translate("SettingsDialog - Cookies", "No cookies stored")

    cookies = sum(row.count for row in rows)

    # labelled rather than written out, so no count has to agree with a
    # noun; the project has no plural forms and this is a poor reason to
    # give translators their first
    return translate(
        "SettingsDialog - Cookies", "Cookies: {COOKIES}    Domains: {DOMAINS}"
    ).format(COOKIES=cookies, DOMAINS=len(rows))
