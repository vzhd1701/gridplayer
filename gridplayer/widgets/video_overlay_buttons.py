from abc import abstractmethod

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QPainter
from PyQt5.QtWidgets import qApp

from gridplayer.utils.misc import QABC
from gridplayer.widgets.video_overlay_elements import OverlayWidget
from gridplayer.widgets.video_overlay_icons import (
    draw_cross,
    draw_pause,
    draw_play,
    draw_volume_off,
    draw_volume_on,
)


class OverlayButton(OverlayWidget, metaclass=QABC):
    clicked = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMouseTracking(True)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self._is_off = False

    @abstractmethod
    def icon(self, rect, painter, color):
        ...

    @abstractmethod
    def icon_off(self, rect, painter, color):
        ...

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.underMouse():
            color_bg = self.color_contrast_mid
            color_fg = self.color
        else:
            color_bg = self.color
            color_fg = self.color_contrast_mid

        painter.fillRect(self.rect(), color_bg)

        if self._is_off:
            self.icon_off(self.rect(), painter, color_fg)
        else:
            self.icon(self.rect(), painter, color_fg)

    def underMouse(self):
        return qApp.widgetAt(QCursor.pos()) is self

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        """Consume to avoid parent event"""

        if event.button() == Qt.LeftButton:
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

        event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Consume to avoid parent event"""
        self.mousePressEvent(event)

        event.accept()

    @property
    def is_off(self):
        return self._is_off

    @is_off.setter
    def is_off(self, is_off):
        self._is_off = is_off
        self.update()


class OverlayExitButton(OverlayButton):
    def icon(self, rect, painter, color):
        return draw_cross(rect, painter, color)

    def icon_off(self, rect, painter, color):
        ...


class OverlayPlayPauseButton(OverlayButton):
    def icon(self, rect, painter, color):
        return draw_play(rect, painter, color)

    def icon_off(self, rect, painter, color):
        return draw_pause(rect, painter, color)


class OverlayVolumeButton(OverlayButton):
    def icon(self, rect, painter, color):
        return draw_volume_on(rect, painter, color)

    def icon_off(self, rect, painter, color):
        return draw_volume_off(rect, painter, color)
