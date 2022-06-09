from itertools import starmap
from typing import Dict, Iterable

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from gridplayer.utils.qt import tr

DIALOG_WIDTH = 500
MULTILINE_HEIGHT = 300


class QAddURLsDialog(QDialog):
    def __init__(
        self,
        supported_schemas: Iterable[str],
        supported_urls: Dict[str, str],
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._input_single = QLineEdit(self)
        self._input_multiline = QTextEdit(self)

        self._supported_info = self._init_info(supported_schemas, supported_urls)

        self._buttons = self._init_buttons()

        self._expand_button = self._buttons.addButton("+", QDialogButtonBox.ResetRole)
        self._expand_button.clicked.connect(self._switch_multiline)

        self._is_expanded = False

        self._ui_setup()

    @property
    def urls(self):
        if self._is_expanded:
            return [
                url.strip()
                for url in self._input_multiline.toPlainText().splitlines()
                if url.strip()
            ]

        url = self._input_single.text().strip()
        return [url] if url else []

    @classmethod
    def get_urls(
        cls,
        parent,
        title: str,
        supported_schemas: Iterable[str],
        supported_urls: Dict[str, str],
    ):
        dialog = cls(
            parent=parent,
            supported_schemas=supported_schemas,
            supported_urls=supported_urls,
        )

        dialog.setWindowTitle(title)

        if dialog.exec():
            return dialog.urls

        return []

    def _init_info(self, schemas: Iterable[str], supported_urls: Dict[str, str]):
        supported_info = QLabel(self)

        info_txt = _init_info_txt(schemas, supported_urls)

        supported_info.setText(info_txt)

        return supported_info

    def _init_buttons(self):
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        for btn in buttons.buttons():
            btn.setIcon(QIcon())

        return buttons

    def _ui_setup(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSizeConstraint(QLayout.SetFixedSize)

        self._supported_info.setOpenExternalLinks(True)

        self._input_single.setMinimumWidth(DIALOG_WIDTH)

        self._input_multiline.setMinimumSize(DIALOG_WIDTH, MULTILINE_HEIGHT)
        self._input_multiline.setAcceptRichText(False)
        self._input_multiline.hide()

        main_layout_stack = [
            self._input_single,
            self._input_multiline,
            self._supported_info,
            self._buttons,
        ]

        for widget in main_layout_stack:
            main_layout.addWidget(widget)

    def _switch_multiline(self):
        url = self.urls[0] if self.urls else ""

        if self._is_expanded:
            self._input_single.setText(url)

            self._input_single.show()
            self._input_multiline.hide()
            self._expand_button.setText("+")
        else:
            self._input_multiline.setText(url)

            self._input_single.hide()
            self._input_multiline.show()
            self._expand_button.setText("-")

        self._is_expanded = not self._is_expanded


def _init_info_txt(schemas, supported_urls):
    supported_info_template = "<br>".join(
        (tr("Supported URL schemas: {SCHEMAS}"), tr("Supported sites: {SERVICES}"))
    )

    tokens = {
        "{SCHEMAS}": ", ".join(sorted(schemas)),
        "{SERVICES}": ", ".join(_convert_urls(supported_urls)),
    }

    for token, token_value in tokens.items():
        supported_info_template = supported_info_template.replace(token, token_value)

    return supported_info_template


def _convert_urls(urls: Dict[str, str]) -> Iterable[str]:
    url_template = "<a href='{1}'>{0}</a>"
    return starmap(url_template.format, urls.items())
