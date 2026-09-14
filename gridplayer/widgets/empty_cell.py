from PyQt5.QtCore import QEvent, QRectF, QSize, Qt
from PyQt5.QtGui import (
    QFont,
    QPainter,
    QPainterPath,
)
from PyQt5.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from gridplayer.params.static import FONT_SIZE_BIG_INFO, INFO_LABEL_MIN_SIZE
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.widgets.cell_chrome import (
    TEXT_ALPHA,
    chrome_color,
    chrome_color_on_cell,
    dashed_frame,
    paint_dashed_outline,
)
from gridplayer.widgets.video_overlay_elements import OverlayDropIndicator


class EmptyCell(QWidget):
    is_empty_cell = True

    def __init__(self, message=None, **kwargs):
        super().__init__(**kwargs)

        self._message = message

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._drop_indicator = OverlayDropIndicator(parent=self)
        layout.addWidget(self._drop_indicator)

        self._message_label = None

        if self._message:
            self._message_label = QLabel(
                self._message,
                parent=self.parent(),
            )
            self._message_label.setAlignment(Qt.AlignCenter)
            self._message_label.setWordWrap(True)
            self._message_label.setMargin(20)
            font = QFont("Hack", FONT_SIZE_BIG_INFO, QFont.Bold)
            self._message_label.setFont(font)

            layout.addWidget(self._message_label)

        self._apply_colors()

    def set_drop_indicator(self, indicator: DropIndicator):
        self._drop_indicator.set_indicator(indicator)
        self._sync_message_label()
        if indicator != DropIndicator.NONE:
            self._drop_indicator.raise_()
        self.update()

    def _sync_message_label(self):
        if not self._message_label:
            return

        fits = (
            self.width() >= INFO_LABEL_MIN_SIZE[0]
            and self.height() >= INFO_LABEL_MIN_SIZE[1]
        )
        self._message_label.setVisible(
            fits and self._drop_indicator.indicator == DropIndicator.NONE
        )

    def minimumSizeHint(self):
        return QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_label_margins()
        self._sync_message_label()

    def _update_label_margins(self):
        if not self._message_label:
            return
        _, stroke, _ = dashed_frame(self)
        margin = max(6.0, min(self.width(), self.height()) / 24)
        inset = stroke * 5
        pad = round(margin + inset)
        self.layout().setContentsMargins(pad, pad, pad, pad)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            self._apply_colors()

    def _apply_colors(self):
        self._drop_indicator.set_colors(
            chrome_color_on_cell(self),
            self.palette().color(self.backgroundRole()),
        )

        if self._message_label:
            color = chrome_color(self, TEXT_ALPHA)
            self._message_label.setStyleSheet(
                f"color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
            )

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        paint_dashed_outline(self, painter)

        if self._drop_indicator.isVisible():
            return

        if self._message:
            return

        rect, stroke, _ = dashed_frame(self)
        self._paint_plus(painter, rect, stroke)

    def _paint_plus(self, painter, rect, stroke):
        plus = max(8.0, min(rect.width(), rect.height()) / 4)
        bar = stroke
        cx, cy = rect.center().x(), rect.center().y()
        cap = bar / 2

        horizontal = QPainterPath()
        horizontal.addRoundedRect(
            QRectF(cx - plus, cy - bar / 2, plus * 2, bar), cap, cap
        )
        vertical = QPainterPath()
        vertical.addRoundedRect(
            QRectF(cx - bar / 2, cy - plus, bar, plus * 2), cap, cap
        )

        painter.setPen(Qt.NoPen)
        painter.fillPath(horizontal.united(vertical), chrome_color(self))
