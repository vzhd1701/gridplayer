from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
    qApp,
)

from gridplayer.utils.darkmode import is_dark_mode


def bezier_blend(t):
    return t * t * (3.0 - 2.0 * t)  # noqa: WPS432


class JumpingBar(QWidget):
    bar_grow_speed = 1.5
    bar_wane_speed = 1

    bar_lowest_percent = 30
    animation_fps = 100

    def __init__(self, start_percent=100, is_growing=False, **kwargs):
        super().__init__(**kwargs)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.animation_fps = min(
            self.animation_fps, int(qApp.primaryScreen().refreshRate())
        )

        self._color = QColor(Qt.white) if is_dark_mode() else QColor(Qt.black)
        self._timer = None

        self.bar_percent = min(max(start_percent, self.bar_lowest_percent), 100)
        self.is_growing = is_growing

    @property
    def bar_percent_smooth(self):
        return bezier_blend(self.bar_percent / 100) * 100

    @property
    def roundness(self):
        return min(self.width() / 3, 10)

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self._color)
        painter.setBrush(self._color)

        middle = self.rect().center()

        bar_height = (self.rect().height() - 10) * (self.bar_percent_smooth / 100)

        bar_rect = QRectF(
            0,
            middle.y() - bar_height / 2,
            self.rect().width(),
            bar_height,
        )

        painter.drawRoundedRect(bar_rect, self.roundness, self.roundness)

    def timerEvent(self, event):
        if self.is_growing:
            self.bar_percent += self.bar_grow_speed

            if self.bar_percent >= 100:
                self.bar_percent = 100
                self.is_growing = False
        else:
            self.bar_percent -= self.bar_wane_speed

            if self.bar_percent <= self.bar_lowest_percent:
                self.bar_percent = self.bar_lowest_percent
                self.is_growing = True

        self.update()

    def showEvent(self, event) -> None:
        # start animation

        if self._timer is None:
            self._timer = self.startTimer(1000 // self.animation_fps)

    def hideEvent(self, event) -> None:
        # stop animation

        if self._timer is not None:
            self.killTimer(self._timer)
            self._timer = None


class LoadingBars(QWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.bars = [
            JumpingBar(start_percent=start_percent, parent=self)
            for start_percent in (100, 70, 50, 70, 100)
        ]

        for cur_bar in self.bars:
            layout.addWidget(cur_bar)
            if cur_bar != self.bars[-1]:
                layout.addStretch()

    def resizeEvent(self, event):
        # maintain 1:1 ratio

        size_min = min(event.size().width(), event.size().height())

        h_margin = round((self.size().width() - size_min) / 2)

        self.layout().setContentsMargins(h_margin, 0, h_margin, 0)


class StatusLabel(QWidget):
    def __init__(self, icon="processing", **kwargs):
        super().__init__(**kwargs)

        self.setup_ui()

        self.status_bars = LoadingBars(parent=self)
        self.status_icon = StatusIcon(parent=self)

        self.layout().addWidget(self.status_bars)
        self.layout().addWidget(self.status_icon)

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

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    def resizeEvent(self, event):
        # maintain 10% margin

        v_margin = int(event.size().height() * 0.1)
        h_margin = int(event.size().width() * 0.1)

        self.layout().setContentsMargins(h_margin, v_margin, h_margin, v_margin)

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


class StatusIcon(QLabel):
    def __init__(self, icon=None, **kwargs):
        super().__init__(**kwargs)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)

        self._pic = None

        self.icon = icon

    def resizeEvent(self, event):
        self._scale_pic(event.size())

    @property
    def icon(self):
        return self._icon

    @icon.setter
    def icon(self, icon):
        self._icon = icon

        if icon is None:
            self._pic = None
            self.clear()
        else:
            self._set_pic(QIcon.fromTheme(icon))

    def _set_pic(self, pic_path):
        reasonably_big = 512

        self._pic = QIcon(pic_path).pixmap(QSize(reasonably_big, reasonably_big))

        self._scale_pic(self.size())

    def _scale_pic(self, size):
        if self._pic is None:
            return

        self.setPixmap(
            self._pic.scaled(
                size.width(), size.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
