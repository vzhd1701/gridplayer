from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QIcon, QPainter
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gridplayer.widgets.video_status_info import StatusInfo
from gridplayer.widgets.video_status_loading import LoadingBars


class VideoStatus(QWidget):
    def __init__(self, icon="processing", status_text="", **kwargs):
        super().__init__(**kwargs)

        self.setup_ui()

        self.status_bars = LoadingBars(parent=self)
        self.status_icon = StatusIcon(parent=self)
        self.status_info = StatusInfo(parent=self)

        self.layout().addWidget(self.status_bars, 1)
        self.layout().addWidget(self.status_icon, 1)

        self.status_info_box = QHBoxLayout()
        self.layout().addLayout(self.status_info_box)

        self.status_info_box.addStretch(1)
        self.status_info_box.addWidget(self.status_info, 4)
        self.status_info_box.addStretch(1)

        self.status_text = status_text
        self.icon = icon

    def setup_ui(self):
        self.setAutoFillBackground(True)

        # Due to VLC video block glitch, cannot hide video block
        # workaround - make overlay loading screen 99% opaque
        # so it will appear visually solid while video block is invisible
        effect = QGraphicsOpacityEffect(self)
        almost_opaque = 0.99
        effect.setOpacity(almost_opaque)
        self.setGraphicsEffect(effect)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)  # noqa: WPS432

    def resizeEvent(self, event):
        # maintain 10% margin

        if self.status_text:
            if self.can_fit_info:
                status_info_min_height = min(
                    int(self.height() * 0.1), 40  # noqa: WPS432
                )
                status_info_max_height = int(
                    status_info_min_height * 1.5  # noqa: WPS432
                )

                self.status_info.setMinimumHeight(status_info_min_height)
                self.status_info.setMaximumHeight(status_info_max_height)

                self.status_info.show()
            else:
                self.status_info.hide()

        v_margin = int(event.size().height() * 0.1)
        h_margin = int(event.size().width() * 0.1)

        self.layout().setContentsMargins(h_margin, v_margin, h_margin, v_margin)

    @property
    def can_fit_info(self):
        return self.height() >= 150  # noqa: WPS432

    @property
    def icon(self):
        return self._icon

    @icon.setter
    def icon(self, icon):
        self._icon = icon

        if icon == "processing":
            self.status_bars.show()

            self.status_icon.hide()
        else:
            self.status_bars.hide()

            self.status_icon.icon = icon
            self.status_icon.show()

    @property
    def status_text(self):
        return self.status_info.text

    @status_text.setter
    def status_text(self, text):
        self.status_info.text = text

        if text and self.can_fit_info:
            self.status_info.show()
        else:
            self.status_info.hide()

    @property
    def percent(self):
        return self.status_info.percent

    @percent.setter
    def percent(self, percent):
        self.status_info.percent = percent


class StatusIcon(QWidget):
    def __init__(self, icon=None, **kwargs):
        super().__init__(**kwargs)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.icon = icon

    @property
    def icon(self):
        return self._icon

    @icon.setter
    def icon(self, icon):
        self._icon = icon

        if icon is None:
            self._icon = None
        else:
            self._icon = QIcon.fromTheme(icon)

    def paintEvent(self, event):
        if not self.icon:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # paint icon in the middle with 1:1 ratio
        side = min(event.rect().width(), event.rect().height())
        rect = QRect(0, 0, side, side)
        rect.moveCenter(event.rect().center())

        self.icon.paint(painter, rect)
