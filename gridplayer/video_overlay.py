import math
import os
import platform
import time

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QEvent, QPoint, Qt, QRect
from PyQt5.QtGui import (
    QBrush,
    QCursor,
    QInputEvent,
    QPainterPath,
    QPen,
    QResizeEvent,
    QPalette,
    QRegion,
)
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    qApp,
)

from gridplayer.settings import settings

PROPAGATED_EVENTS = {
    QEvent.MouseButtonRelease,
    QEvent.MouseButtonPress,
    QEvent.MouseMove,
    QEvent.MouseButtonDblClick,
    QEvent.Wheel,
    QEvent.ContextMenu,
}


class OverlayWidget(QtWidgets.QWidget):
    padding = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # font_height = QtGui.QFontMetrics(QFont("Hack")).height()
        font_height = 13

        self.setMinimumHeight(font_height + self.padding)


class OverlayButton(OverlayWidget):
    clicked = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            event.ignore()


class OverlayLabel(OverlayWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._label = ""

        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        label = self.label
        max_width = event.rect().width() - self.padding * 2

        metrics = QtGui.QFontMetrics(painter.font())
        size = metrics.size(0, label)

        if size.width() > max_width:
            size.setWidth(max_width)
            label = metrics.elidedText(label, QtCore.Qt.ElideMiddle, max_width)

        painter.fillRect(self.rect(), QtCore.Qt.white)
        painter.setPen(Qt.black)
        painter.drawText(self.rect(), QtCore.Qt.AlignCenter, label)

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, value):
        self._label = value
        self.update()


class OverlayShortLabel(OverlayWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._text = ""
        self._is_visuals_updated = False

        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        if not self._is_visuals_updated:
            self.update_visuals()

        painter.fillRect(self.rect(), QtCore.Qt.white)
        painter.setPen(Qt.black)
        painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self.text)

    def update_visuals(self):
        padding = 10

        metrics = QtGui.QFontMetrics(self.font())
        size = metrics.size(0, self._text)

        self.setMinimumWidth(size.width() + padding)

        self._is_visuals_updated = True

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        first_update = self._text == ""

        self._text = value

        self._is_visuals_updated = False

        if first_update:
            self.update_visuals()

        self.update()


class OverlayShortLabelFloating(OverlayShortLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.length = None

        self._clip_region = None

    def _is_inside_simple_overlay(self):
        return isinstance(self.parent(), OverlayBlockFloating) and settings.get(
            "internal/opaque_hw_overlay"
        )

    def on_mouse_over(self, pos, progress_pos):
        if self.length is None:
            return

        new_time = (self.length * progress_pos) // 1000
        self.text = get_time_txt_short(new_time)

        pos.setX(pos.x() - round(self.rect().width() / 2))
        pos.setY(pos.y() - self.rect().height())
        self.move(pos)
        self.show()

    def on_mouse_left(self):
        self.hide()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        if not self._is_visuals_updated:
            self.update_visuals()

        text_box = self.rect().translated(0, 0)
        text_box.setHeight(text_box.height() - 10)

        painter.fillRect(text_box, QtCore.Qt.white)
        painter.setPen(Qt.black)
        painter.drawText(text_box, QtCore.Qt.AlignCenter, self.text)

        if self._is_inside_simple_overlay():
            self._clip_region = QRegion(text_box)
            self.draw_triangle(painter)
            self.setMask(self._clip_region)

            return

        self.draw_triangle(painter)

    def draw_triangle(self, painter):
        rect = self.rect()

        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        path = QPainterPath()

        middle_x = round(rect.width() / 2)

        path.moveTo(middle_x - 5, rect.height() - 10)
        path.lineTo(middle_x + 5, rect.height() - 10)
        path.lineTo(middle_x, rect.height())
        path.lineTo(middle_x - 5, rect.height() - 10)

        painter.setPen(Qt.NoPen)
        painter.fillPath(path, QtCore.Qt.white)

        if self._is_inside_simple_overlay():
            painter.setClipPath(path)
            self._clip_region = self._clip_region.united(painter.clipRegion())

    def update_visuals(self):
        padding = 10

        metrics = QtGui.QFontMetrics(self.font())
        size = metrics.size(0, self._text)

        self.setFixedSize(size.width() + padding, size.height() + padding + 10)

        self._is_visuals_updated = True


class OverlayExitButton(OverlayWidget):
    clicked = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self.setMouseTracking(True)

    def underMouse(self):
        return qApp.widgetAt(QCursor.pos()) is self

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        if self.underMouse():
            color_bg = QtCore.Qt.gray
            color_fg = QtCore.Qt.white
        else:
            color_bg = QtCore.Qt.white
            color_fg = QtCore.Qt.gray

        painter.fillRect(self.rect(), color_bg)

        self.draw_cross(self.rect(), painter, color_fg)

    def draw_cross(self, rect, painter, color):
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QPen(color, 4))

        line_len = round(
            math.sqrt(
                (rect.width() - self.padding) ** 2 + (rect.width() - self.padding) ** 2
            )
        )

        painter.drawLine(
            rect.x() + 5, rect.y() + 5, rect.x() + line_len, rect.y() + line_len,
        )
        painter.drawLine(
            rect.x() + line_len, rect.y() + 5, rect.x() + 5, rect.y() + line_len,
        )


class OverlayPlayPauseButton(OverlayWidget):
    clicked = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self.setMouseTracking(True)

        self._is_paused = False

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        if self.underMouse():
            color_bg = QtCore.Qt.gray
            color_fg = QtCore.Qt.white
        else:
            color_bg = QtCore.Qt.white
            color_fg = QtCore.Qt.gray

        painter.fillRect(self.rect(), color_bg)

        if self.is_paused:
            self.draw_play(self.rect(), painter, color_fg)
        else:
            self.draw_pause(self.rect(), painter, color_fg)

    def draw_pause(self, rect, painter, color):
        painter.fillRect(rect.x() + 5, rect.y() + 4, 5, rect.height() - 8, color)
        painter.fillRect(
            rect.width() - 5 - 5, rect.y() + 4, 5, rect.height() - 8, color
        )

    def draw_play(self, rect, painter, color):
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        path = QPainterPath()

        path.moveTo(rect.x() + 5, rect.y() + 4)
        path.lineTo(rect.width() - 5, round(rect.height() / 2))
        path.lineTo(rect.x() + 5, rect.height() - 4)
        path.lineTo(rect.x() + 5, rect.y() + 4)

        painter.setPen(Qt.NoPen)
        painter.fillPath(path, QBrush(color))

    @property
    def is_paused(self):
        return self._is_paused

    @is_paused.setter
    def is_paused(self, value):
        self._is_paused = value
        self.update()


class OverlayVolumeButton(OverlayWidget):
    clicked = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumSize(self.minimumWidth(), self.minimumHeight())

        self.setMouseTracking(True)

        self._is_muted = True

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        if self.underMouse():
            color_bg = QtCore.Qt.gray
            color_fg = QtCore.Qt.white
        else:
            color_bg = QtCore.Qt.white
            color_fg = QtCore.Qt.gray

        painter.fillRect(self.rect(), color_bg)

        self.draw_volume(self.rect(), painter, color_fg)

        if not self.is_muted:
            self.draw_volume_on(self.rect(), painter, color_fg)

    def draw_volume(self, rect, painter, color):
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        path = QPainterPath()

        path.moveTo(rect.x() + 5, round(rect.height() / 2) - 3)

        path.lineTo(rect.x() + 5 + 3, round(rect.height() / 2) - 3)
        path.lineTo(rect.x() + 5 + 6, 4)
        path.lineTo(rect.x() + 5 + 6, rect.height() - 4)
        path.lineTo(rect.x() + 5 + 3, round(rect.height() / 2) + 3)
        path.lineTo(rect.x() + 5, round(rect.height() / 2) + 3)

        path.lineTo(rect.x() + 5, round(rect.height() / 2) - 3)

        painter.setPen(Qt.NoPen)
        painter.fillPath(path, QBrush(color))

    def draw_volume_on(self, rect, painter, color):
        painter.fillRect(
            rect.x() + 5 + 6 + 3, rect.y() + 6, 4, rect.height() - 12, color
        )

    @property
    def is_muted(self):
        return self._is_muted

    @is_muted.setter
    def is_muted(self, value):
        self._is_muted = value
        self.update()


class OverlayProgressBar(OverlayWidget):
    emit_new_position = QtCore.pyqtSignal(float)

    mouse_over = QtCore.pyqtSignal(QPoint, float)
    mouse_left = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMouseTracking(True)

        self._position = 0.0
        self._loop_start = 0.0
        self._loop_end = 100.0
        self.progress_select_x = None

    def leaveEvent(self, event):
        self.update()

        self.mouse_left.emit()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.progress_select_x = event.pos().x()
        self.update()

        top_edge = self.mapToParent(event.pos())
        top_edge.setY(self.pos().y())

        mouse_position = self.progress_select_x / self.width()
        self.mouse_over.emit(top_edge, mouse_position)

        event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.progress_select_x = event.pos().x()
            new_position = self.progress_select_x / self.width()
            self.emit_new_position.emit(new_position)

            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        painter.fillRect(self.rect(), QtCore.Qt.white)

        progress_rect = self.rect().translated(0, 0)

        cur_fill = math.ceil(self.rect().width() * self.position)

        progress_rect.setWidth(cur_fill)

        painter.fillRect(progress_rect, QtCore.Qt.red)

        if self.progress_select_x is not None and self.underMouse():
            self.draw_progress_bar_select(painter, self.rect(), progress_rect)

        if self.loop_start > 0.0:
            self.draw_loop_mark(painter, self.rect(), self.loop_start)

        if self.loop_end < 100.0:
            self.draw_loop_mark(painter, self.rect(), self.loop_end)

    def draw_progress_bar_select(self, painter, rect, progress_rect):
        progress_rect_sel = rect.translated(0, 0)
        progress_rect_sel.setRight(self.progress_select_x - 1)

        if progress_rect_sel.right() <= progress_rect.right():
            painter.fillRect(progress_rect_sel, QtCore.Qt.blue)
        else:
            painter.fillRect(progress_rect_sel, QtCore.Qt.gray)
            painter.fillRect(progress_rect, QtCore.Qt.blue)

    def draw_loop_mark(self, painter, rect, loop_mark_percent):
        cur_start_loop_rect = rect.translated(0, 0)
        cur_start_loop = math.ceil(rect.width() * loop_mark_percent)

        cur_start_loop_rect.setX(cur_start_loop)
        cur_start_loop_rect.setWidth(1)

        painter.fillRect(cur_start_loop_rect, QtCore.Qt.green)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = value
        self.update()

    @property
    def loop_start(self):
        return self._loop_start

    @loop_start.setter
    def loop_start(self, value):
        self._loop_start = value
        self.update()

    @property
    def loop_end(self):
        return self._loop_end

    @loop_end.setter
    def loop_end(self, value):
        self._loop_end = value
        self.update()


class OverlayVolumeBar(OverlayWidget):
    emit_new_position = QtCore.pyqtSignal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumHeight(self.minimumHeight() * 4)
        self.setMinimumHeight(10)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.setMouseTracking(True)

        self._position = 0.0
        self.progress_select_y = None

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.progress_select_y = event.pos().y()
        self.update()

        event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.progress_select_y = event.pos().y()
            new_position = 1.0 - (self.progress_select_y / self.height())
            self.emit_new_position.emit(new_position)

            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        painter.fillRect(self.rect(), QtCore.Qt.white)

        progress_rect = self.rect().translated(0, 0)

        cur_fill = math.ceil(self.rect().height() * self.position)

        progress_rect.setY(self.rect().height() - cur_fill)
        progress_rect.setHeight(cur_fill)

        painter.fillRect(progress_rect, QtCore.Qt.red)

        if self.progress_select_y is not None and self.underMouse():
            self.draw_progress_bar_select(painter, self.rect(), progress_rect)

    def draw_progress_bar_select(self, painter, rect, progress_rect):
        progress_rect_sel = rect.translated(0, 0)
        progress_rect_sel.setTop(self.progress_select_y)

        if progress_rect_sel.top() >= progress_rect.top():
            painter.fillRect(progress_rect_sel, QtCore.Qt.blue)
        else:
            painter.fillRect(progress_rect_sel, QtCore.Qt.gray)
            painter.fillRect(progress_rect, QtCore.Qt.blue)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = value
        self.update()


def get_time_txt_short(seconds):
    if seconds > 3600:
        return time.strftime("%H:%M:%S", time.gmtime(seconds)).lstrip("0")
    elif seconds > 60:
        return time.strftime("%M:%S", time.gmtime(seconds)).lstrip("0")
    else:
        return time.strftime("0:%S", time.gmtime(seconds))


def get_time_txt(seconds, max_seconds=None):
    seconds_cnt = max_seconds or seconds

    if seconds_cnt > 3600:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    elif seconds_cnt > 60:
        return time.strftime("%M:%S", time.gmtime(seconds))
    else:
        return time.strftime("0:%S", time.gmtime(seconds))


class OverlayBlock(QtWidgets.QWidget):
    set_vid_pos = QtCore.pyqtSignal(float)
    set_volume = QtCore.pyqtSignal(float)
    exit_clicked = QtCore.pyqtSignal()
    play_pause_clicked = QtCore.pyqtSignal()
    mute_unmute_clicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

        # self.setWindowOpacity(0.5)

        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.5)
        self.setGraphicsEffect(effect)

        QVBoxLayout(self)

        self.top_bar = QVBoxLayout()
        self.middle = QHBoxLayout()
        self.bottom_bar = QHBoxLayout()

        self.layout().addLayout(self.top_bar)
        self.layout().addLayout(self.middle, 1)
        self.layout().addLayout(self.bottom_bar)

        self.label_text = OverlayLabel()
        self.exit_button = OverlayExitButton()

        self.title_bar = QHBoxLayout()
        self.title_bar.addWidget(self.label_text, 1)
        self.title_bar.addWidget(self.exit_button)

        self.label_info = OverlayShortLabel()
        self.label_info.hide()

        self.label_info_hide_timer = QtCore.QTimer()
        self.label_info_hide_timer.setSingleShot(True)
        self.label_info_hide_timer.timeout.connect(self.label_info.hide)

        self.info_bar = QHBoxLayout()
        self.info_bar.addWidget(self.label_info)
        self.info_bar.addStretch()

        self.top_bar.addLayout(self.title_bar)
        self.top_bar.addLayout(self.info_bar)

        self.right_bar = QVBoxLayout()

        self.middle.addStretch()
        self.middle.addLayout(self.right_bar)

        self.volume_bar = OverlayVolumeBar()

        self.right_bar.addStretch()
        self.right_bar.addWidget(self.volume_bar, 1)

        self.play_pause_button = OverlayPlayPauseButton()
        self.label_progress = OverlayShortLabel()
        self.progress_bar = OverlayProgressBar()
        self.volume_button = OverlayVolumeButton()

        self.bottom_bar.addWidget(self.play_pause_button)
        self.bottom_bar.addWidget(self.label_progress)
        self.bottom_bar.addWidget(self.progress_bar, 1)
        self.bottom_bar.addWidget(self.volume_button)

        self.floating_progress = OverlayShortLabelFloating(self)
        self.floating_progress.hide()

        self.progress_bar.mouse_over.connect(self.floating_progress.on_mouse_over)
        self.progress_bar.mouse_left.connect(self.floating_progress.on_mouse_left)

        self.exit_button.clicked.connect(self.exit)
        self.play_pause_button.clicked.connect(self.play_pause)
        self.progress_bar.emit_new_position.connect(self.emit_position)
        self.volume_button.clicked.connect(self.mute_unmute)
        self.volume_bar.emit_new_position.connect(self.emit_volume_position)

        self.play_pause_button.installEventFilter(self)
        self.progress_bar.installEventFilter(self)
        self.volume_button.installEventFilter(self)
        self.volume_bar.installEventFilter(self)

    def resizeEvent(self, event):
        elements = {
            "label_progress": True,
            "label_text": True,
            "exit_button": True,
            "volume_bar": True,
            "play_pause_button": True,
            "progress_bar": True,
            "volume_button": True,
        }

        is_wide = event.size().width() > 250

        elements["label_progress"] = is_wide

        self.label_progress.setVisible(elements["label_progress"])
        # self.label_text.setVisible(elements["label_text"])
        # self.exit_button.setVisible(elements["exit_button"])
        # self.volume_bar.setVisible(elements["volume_bar"])
        # self.play_pause_button.setVisible(elements["play_pause_button"])
        # self.progress_bar.setVisible(elements["progress_bar"])
        # self.volume_button.setVisible(elements["volume_button"])

    @QtCore.pyqtSlot(int, int)
    def set_position(self, position, length):
        position_percent = position / length

        position_txt = get_time_txt(position // 1000, length // 1000)
        length_txt = get_time_txt(length // 1000)

        self.floating_progress.length = length
        self.label_progress.text = f"{position_txt} / {length_txt}"
        self.progress_bar.position = position_percent

    @QtCore.pyqtSlot(float)
    def set_loop_start(self, position):
        self.progress_bar.loop_start = position

    @QtCore.pyqtSlot(float)
    def set_loop_end(self, position):
        self.progress_bar.loop_end = position

    @QtCore.pyqtSlot(str)
    def set_label(self, label):
        self.label_text.label = label

    @QtCore.pyqtSlot(str)
    def set_info_label(self, info_text):
        self.label_info.text = info_text
        self.label_info.show()
        self.label_info_hide_timer.start(2000)

    @QtCore.pyqtSlot(bool)
    def set_is_paused(self, is_paused):
        self.play_pause_button.is_paused = is_paused

    @QtCore.pyqtSlot(bool)
    def set_is_muted(self, is_muted):
        self.volume_button.is_muted = is_muted

        self.volume_bar.setHidden(self.volume_button.is_muted)

    @QtCore.pyqtSlot(float)
    def set_volume_position(self, position):
        self.volume_bar.position = position

    @QtCore.pyqtSlot()
    def exit(self):
        self.exit_clicked.emit()

    @QtCore.pyqtSlot()
    def play_pause(self):
        self.play_pause_clicked.emit()

    @QtCore.pyqtSlot()
    def mute_unmute(self):
        self.mute_unmute_clicked.emit()

    @QtCore.pyqtSlot(float)
    def emit_position(self, position):
        self.set_vid_pos.emit(position)

    @QtCore.pyqtSlot(float)
    def emit_volume_position(self, position):
        self.set_volume.emit(position)

    def eventFilter(self, event_object, event) -> bool:
        """Show cursor on any mouse event for children"""

        if isinstance(event, QInputEvent):
            return self.parent().eventFilter(event_object, event)

        return False


class OverlayBlockFloating(OverlayBlock):
    def __init__(self, parent=None):
        super().__init__(parent)

        pal = self.palette()
        col = pal.color(QPalette.Active, QPalette.ButtonText)
        pal.setColor(QPalette.Inactive, QPalette.Text, col)
        self.setPalette(pal)

        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        # Allow window to move beyond screen edge
        self.setAttribute(QtCore.Qt.WA_X11NetWmWindowTypeDesktop)
        self.setAttribute(QtCore.Qt.WA_X11DoNotAcceptFocus)

        # Drag and drop doesn't get through floating overlay on X11
        # need to redirect drag events to Player window
        if os.name != "nt":
            self.setAcceptDrops(True)

        self.setWindowFlags(
            QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowDoesNotAcceptFocus
            # | QtCore.Qt.WindowStaysOnTopHint
        )

        if settings.get("internal/opaque_hw_overlay"):
            self.setAttribute(QtCore.Qt.WA_NoSystemBackground, False)
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)

            self.setGraphicsEffect(None)

        self.parent().window().installEventFilter(self)

    def setGeometry(self, rect):
        new_pos = self.parent().mapToGlobal(QPoint())
        rect.moveTopLeft(new_pos)

        self.setFixedSize(rect.size())

        super().setGeometry(rect)

    def moveEvent(self, event):
        self.move_to_parent()

        event.accept()

    def paintEvent(self, event):
        self.move_to_parent()

        if settings.get("internal/opaque_hw_overlay"):
            mask = self.childrenRegion()
            # 0 coord to keep children from sliding off
            mask = mask.united(QRegion(QRect(0, 0, 1, 1)))

            self.setMask(mask)

        event.ignore()

    def move_to_parent(self):
        new_pos = self.parent().mapToGlobal(QPoint())

        if new_pos != self.pos():
            self.move(new_pos)

    def eventFilter(self, event_object, event) -> bool:
        """Show cursor on any mouse event for children"""

        if event_object == self.parent().window():
            if event.type() == QEvent.Move:
                QApplication.sendEvent(self, event)
            if event.type() == QEvent.LayoutRequest:
                self.move_to_parent()

        return super().eventFilter(event_object, event)

    def event(self, event):
        """Events are not propagated for independent windows (like this one),
        so have to do it manually to emulate regular child widget behaviour.

        https://stackoverflow.com/a/3184510/13100286
        https://forum.qt.io/post/352629"""

        if event.type() in PROPAGATED_EVENTS:
            QApplication.sendEvent(self.parent(), event)

        return super().event(event)

    def dragEnterEvent(self, event):
        self.parent().window().dragEnterEvent(event)

    def dropEvent(self, event):
        self.parent().window().dropEvent(event)
