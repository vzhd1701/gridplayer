from PyQt5.QtCore import QEvent, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListView,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params.languages import Language
from gridplayer.params.theme import current_colors, selection_fill
from gridplayer.utils.qt import translate

_MIN_TEXT_WIDTH = 80
_LTR_ALIGN = Qt.AlignLeft | Qt.AlignAbsolute | Qt.AlignVCenter


def _selection_tint() -> QColor:
    return selection_fill()


def _colorized_theme_icon(name: str, size: QSize, color: QColor) -> QPixmap:
    source = QIcon.fromTheme(name).pixmap(size)

    tinted = QPixmap(source.size())
    tinted.fill(Qt.transparent)

    painter = QPainter(tinted)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()

    return tinted


def _ltr_html(inner: str) -> str:
    return f'<div dir="ltr">{inner}</div>'


def _language_title_html(language: Language) -> str:
    if language.completion == 100:
        completion_txt = ""
    else:
        completion_txt = f" [{language.completion} %]"

    return _ltr_html(
        f"<b>{language.title_native}</b> ({language.country_native}){completion_txt}"
    )


def _author_tooltip(authors) -> str:
    return "\n".join(author.name for author in authors)


def _overflow_label(count: int) -> str:
    if count == 1:
        return translate("LanguageList", "+{count} other").format(count=count)
    return translate("LanguageList", "+{count} others").format(count=count)


def _author_plain(authors, shown_count: int) -> str:
    names = ", ".join(author.name for author in authors[:shown_count])
    hidden = len(authors) - shown_count
    if hidden:
        return f"{names} {_overflow_label(hidden)}"
    return names


def _shown_author_count(authors, font: QFont, max_width: int) -> int:
    if not authors:
        return 0

    fm = QFontMetrics(font)
    total = len(authors)
    if fm.horizontalAdvance(_author_plain(authors, total)) <= max_width:
        return total

    for shown in range(total - 1, 0, -1):
        if fm.horizontalAdvance(_author_plain(authors, shown)) <= max_width:
            return shown

    return 1


def _author_credit_html(authors, shown_count: int) -> str:
    if not authors or shown_count <= 0:
        return ""

    links = ", ".join(
        f'<a href="{author.url}">{author.name}</a>' for author in authors[:shown_count]
    )
    hidden = len(authors) - shown_count
    if hidden:
        return _ltr_html(f"{links} {_overflow_label(hidden)}")
    return _ltr_html(links)


class LanguageRowWidget(QWidget):
    flag_size = QSize(48, 36)
    check_slot_size = QSize(36, 36)
    check_icon_size = QSize(32, 32)
    font_size = 14
    author_font_size = 12
    spacing = 12

    def __init__(self, language: Language, **kwargs):
        super().__init__(**kwargs)

        self._selected = False
        self._authors = language.authors

        self.setObjectName("LanguageRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setLayoutDirection(Qt.LeftToRight)

        self.icon_checkmark = self._ui_checkmark()
        self.icon_flag = self._ui_icon_flag(language.icon_path)
        self.title = self._ui_title(_language_title_html(language))
        self.authors = self._ui_authors(language)
        if self.authors is not None:
            self.authors.installEventFilter(self)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addWidget(self.title)
        if self.authors is not None:
            text_col.addWidget(self.authors)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(self.spacing)
        layout.addWidget(self.icon_checkmark, 0, Qt.AlignVCenter)
        layout.addWidget(self.icon_flag, 0, Qt.AlignVCenter)
        layout.addLayout(text_col, 1)

        self._apply_background()
        self._refresh_checkmark()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return

        self._selected = selected
        self._apply_background()
        self._refresh_checkmark()

    def refresh_theme(self) -> None:
        self._apply_background()
        self._refresh_checkmark()

    def adjust_width(self, viewport_width: int) -> None:
        layout = self.layout()
        margins = layout.contentsMargins()
        used = (
            margins.left()
            + margins.right()
            + self.check_slot_size.width()
            + self.icon_flag.sizeHint().width()
            + layout.spacing() * 2
        )
        text_width = max(viewport_width - used, _MIN_TEXT_WIDTH)
        self.title.setFixedWidth(text_width)
        if self.authors is not None:
            self.authors.setFixedWidth(text_width)
            self._fit_authors(text_width)

    def sizeHint(self) -> QSize:
        layout = self.layout()
        margins = layout.contentsMargins()
        text_width = max(self.title.width(), _MIN_TEXT_WIDTH)
        text_height = max(self.title.heightForWidth(text_width), self.font_size)
        if self.authors is not None:
            text_height += self.authors.sizeHint().height() + 2
        content_height = max(
            text_height,
            self.check_slot_size.height(),
            self.icon_flag.sizeHint().height(),
        )
        return QSize(
            (
                self.check_slot_size.width()
                + self.icon_flag.sizeHint().width()
                + text_width
                + layout.spacing() * 2
                + margins.left()
                + margins.right()
            ),
            content_height + margins.top() + margins.bottom(),
        )

    def _apply_background(self) -> None:
        if not self._selected:
            self.setStyleSheet("QWidget#LanguageRow { background-color: transparent; }")
            return

        tint = _selection_tint()
        self.setStyleSheet(
            f"QWidget#LanguageRow {{ background-color: {tint.name()}; }}"
        )

    def _refresh_checkmark(self) -> None:
        if not self._selected:
            self.icon_checkmark.clear()
            return

        # Theme table, not widget palette — PaletteChange arrives before
        # inherited WindowText updates, so the check would stay one theme behind.
        color = QColor(current_colors()["text"])
        self.icon_checkmark.setPixmap(
            _colorized_theme_icon("checkmark", self.check_icon_size, color)
        )

    def _ui_icon_flag(self, icon):
        icon_flag = QSvgWidget(icon, self)
        icon_flag.setFixedSize(self.flag_size)

        icon_flag_bg = QWidget(self)
        icon_flag_bg.setObjectName("LanguageFlagBg")
        icon_flag_bg.setStyleSheet("QWidget#LanguageFlagBg { background-color: #666; }")

        icon_flag_bg_layout = QHBoxLayout(icon_flag_bg)
        icon_flag_bg_layout.setContentsMargins(1, 1, 1, 1)
        icon_flag_bg_layout.setSizeConstraint(QLayout.SetFixedSize)
        icon_flag_bg_layout.addWidget(icon_flag)

        return icon_flag_bg

    def _ui_title(self, text):
        text_label = QLabel(text, self)
        font = text_label.font()
        font.setPixelSize(self.font_size)
        text_label.setFont(font)
        text_label.setTextFormat(Qt.RichText)
        text_label.setWordWrap(True)
        text_label.setLayoutDirection(Qt.LeftToRight)
        text_label.setAlignment(_LTR_ALIGN)
        text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_label.setStyleSheet("QLabel { background: transparent; }")

        return text_label

    def _ui_authors(self, language: Language):
        if not language.authors:
            return None

        text_label = QLabel(self)
        font = text_label.font()
        font.setPixelSize(self.author_font_size)
        text_label.setFont(font)
        text_label.setTextFormat(Qt.RichText)
        text_label.setOpenExternalLinks(True)
        text_label.setWordWrap(False)
        text_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        text_label.setFocusPolicy(Qt.NoFocus)
        text_label.setLayoutDirection(Qt.LeftToRight)
        text_label.setAlignment(_LTR_ALIGN)
        text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text_label.setStyleSheet("QLabel { background: transparent; }")
        self._apply_author_credit(text_label, len(language.authors))

        return text_label

    def eventFilter(self, watched, event):
        authors = getattr(self, "authors", None)
        if (
            authors is not None
            and watched is authors
            and event.type()
            in (
                QEvent.MouseButtonPress,
                QEvent.MouseButtonDblClick,
            )
        ):
            self._select_in_list()
        return super().eventFilter(watched, event)

    def _select_in_list(self) -> None:
        parent = self.parent()
        while parent is not None and not isinstance(parent, QListWidget):
            parent = parent.parent()
        if parent is None:
            return

        for i in range(parent.count()):
            item = parent.item(i)
            if parent.itemWidget(item) is self:
                parent.setCurrentItem(item)
                return

    def _fit_authors(self, text_width: int) -> None:
        shown = _shown_author_count(self._authors, self.authors.font(), text_width - 4)
        self._apply_author_credit(self.authors, shown)

    def _apply_author_credit(self, label: QLabel, shown_count: int) -> None:
        label.setText(_author_credit_html(self._authors, shown_count))
        if shown_count < len(self._authors):
            label.setToolTip(_author_tooltip(self._authors))
        else:
            label.setToolTip("")

    def _ui_checkmark(self):
        icon_checkmark = QLabel(self)
        icon_checkmark.setAlignment(Qt.AlignCenter)
        icon_checkmark.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        icon_checkmark.setFixedSize(self.check_slot_size)
        icon_checkmark.setStyleSheet("QLabel { background: transparent; }")

        return icon_checkmark


class LanguageList(QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._last_viewport_width = 0

        self.setLayoutDirection(Qt.LeftToRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(False)

        self._apply_list_style()
        self.currentItemChanged.connect(self._on_current_item_changed)

    def add_language_row(self, language: Language):
        row_item_w = LanguageRowWidget(language)

        row_item = QListWidgetItem(self)
        row_item.setData(Qt.UserRole, language.code)
        row_item.setSizeHint(row_item_w.sizeHint())
        self.setItemWidget(row_item, row_item_w)

        viewport_width = self.viewport().width()
        if viewport_width > 0:
            row_item_w.adjust_width(viewport_width)
            row_item.setSizeHint(row_item_w.sizeHint())

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_rows()

    def showEvent(self, event):
        super().showEvent(event)
        self._relayout_rows(force=True)

    def changeEvent(self, event):
        if event.type() == QEvent.PaletteChange:
            self._apply_list_style()
            for i in range(self.count()):
                widget = self.itemWidget(self.item(i))
                if widget:
                    widget.refresh_theme()

        super().changeEvent(event)

    def _apply_list_style(self) -> None:
        bg_color = current_colors()["base"]
        self.setStyleSheet(
            f"QListWidget::item:selected {{background-color: {bg_color};}}"
            f"QListWidget::item:hover {{background-color: {bg_color};}}"
        )

    def _relayout_rows(self, force: bool = False) -> None:
        width = self.viewport().width()
        if width <= 0:
            return
        if not force and width == self._last_viewport_width:
            return

        self._last_viewport_width = width

        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget is None:
                continue
            widget.adjust_width(width)
            item.setSizeHint(widget.sizeHint())

    def _on_current_item_changed(self, cur, prev):
        if prev:
            widget = self.itemWidget(prev)
            if widget:
                widget.set_selected(False)
        if cur:
            widget = self.itemWidget(cur)
            if widget:
                widget.set_selected(True)
