from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from gridplayer.params.languages import Language
from gridplayer.widgets.video_status import StatusIcon


class LanguageRowWidget(QWidget):
    flag_size = QSize(48, 36)
    font_size = 14
    spacing = 12

    def __init__(self, text, icon, **kwargs):
        super().__init__(**kwargs)

        self.icon_flag = self._ui_icon_flag(icon)
        self.text = self._ui_text(text)

        self.icon_checkmark = StatusIcon("checkmark", parent=self)
        self.icon_checkmark.setFixedSize(
            self.flag_size.height(), self.flag_size.height()
        )
        self.icon_checkmark.hide()

        layout = QHBoxLayout(self)
        layout.setSpacing(self.spacing)

        layout.addWidget(self.icon_flag)
        layout.addWidget(self.text)
        layout.addStretch()
        layout.addWidget(self.icon_checkmark)

    def show_checkmark(self):
        self.icon_checkmark.show()

    def hide_checkmark(self):
        self.icon_checkmark.hide()

    def _ui_icon_flag(self, icon):
        icon_flag = QSvgWidget(icon, self)
        icon_flag.setFixedSize(self.flag_size)

        icon_flag_bg = QWidget(self)
        icon_flag_bg.setStyleSheet("background-color: #666;")

        icon_flag_bg_layout = QHBoxLayout(icon_flag_bg)
        icon_flag_bg_layout.setContentsMargins(1, 1, 1, 1)
        icon_flag_bg_layout.setSizeConstraint(QLayout.SetFixedSize)
        icon_flag_bg_layout.addWidget(icon_flag)

        return icon_flag_bg

    def _ui_text(self, text):
        text_label = QLabel(text, self)
        font = text_label.font()
        font.setPixelSize(self.font_size)
        text_label.setFont(font)
        text_label.setOpenExternalLinks(True)

        return text_label


class LanguageList(QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        bg_color = QPalette().color(QPalette.Base).name()

        self.setStyleSheet(
            f"QListWidget::item:selected {{background-color: {bg_color};}}"
        )

        self.currentItemChanged.connect(self._set_language_checkmark)

    def add_language_row(self, language: Language):
        if language.completion == 100:
            completion_txt = ""
        else:
            completion_txt = f" [{language.completion} %]"

        if language.authors:
            item_title = (
                "<p style='margin-bottom: 5px;'>"
                "<b>{language}</b> ({country}){completion_txt}</p>"
                "<p style='margin: 0;'>Author: {author}</p>".format(
                    language=language.title_native,
                    country=language.country_native,
                    completion_txt=completion_txt,
                    author=", ".join(language.author_links),
                )
            )
        else:
            item_title = f"<p><b>{language.title_native}</b> ({language.country_native}){completion_txt}</p>"

        row_item_w = LanguageRowWidget(item_title, language.icon_path)

        row_item = QListWidgetItem(self)
        row_item.setData(Qt.UserRole, language.code)
        row_item.setSizeHint(row_item_w.sizeHint())
        self.setItemWidget(row_item, row_item_w)

    def setValue(self, data_value):
        for i in range(self.count()):
            cur_item = self.item(i)
            if cur_item.data(Qt.UserRole) == data_value:
                self.setCurrentItem(cur_item)
                self.scrollToItem(cur_item)
                break

    def value(self):
        selected_item = self.currentItem()
        if selected_item:
            return selected_item.data(Qt.UserRole)

    def _set_language_checkmark(self, cur, prev):
        if prev:
            self.itemWidget(prev).hide_checkmark()
        if cur:
            self.itemWidget(cur).show_checkmark()
