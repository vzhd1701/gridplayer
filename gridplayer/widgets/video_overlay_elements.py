import math

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QRegion,
)
from PyQt5.QtWidgets import QSizePolicy, QWidget

from gridplayer.utils.time_txt import get_time_txt_short


class OverlayWidget(QWidget):
    padding = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        font_height = 13
        self._color = QColor(Qt.white)

        self.setMinimumHeight(font_height + self.padding)

    @property
    def color(self):
        return self._color

    @property
    def color_contrast(self):
        lightness = 0 if self.color.lightness() > 127 else 255  # noqa: WPS432

        return QColor.fromHsl(self.color.hue(), self.color.saturation(), lightness)

    @property
    def color_contrast_mid(self):
        if self.color.lightness() > 127:  # noqa: WPS432
            lightness = self.color.lightness() - 100
        else:
            lightness = self.color.lightness() + 100

        return QColor.fromHsl(self.color.hue(), self.color.saturation(), lightness)

    @color.setter
    def color(self, color):
        self._color = QColor(color)
        self.update()


class OverlayLabel(OverlayWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._label = ""

        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)

        label = self.printable_label(event.rect().width(), painter.font())

        painter.fillRect(self.rect(), self.color)
        painter.setPen(self.color_contrast)
        painter.drawText(self.rect(), Qt.AlignCenter, label)

    def printable_label(self, width, font):
        label = self.label

        max_width = width - self.padding * 2
        metrics = QFontMetrics(font)

        size = metrics.size(0, label)
        if size.width() > max_width:
            size.setWidth(max_width)
            label = metrics.elidedText(label, Qt.ElideMiddle, max_width)

        return label

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, label_txt):
        self._label = label_txt
        self.update()


class OverlayShortLabel(OverlayWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._text = ""
        self._is_visuals_updated = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)

        if not self._is_visuals_updated:
            self.update_visuals()

        painter.fillRect(self.rect(), self.color)
        painter.setPen(self.color_contrast)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text)

    def update_visuals(self):
        padding = 10

        metrics = QFontMetrics(self.font())
        size = metrics.size(0, self._text)

        self.setMinimumWidth(size.width() + padding)

        self._is_visuals_updated = True

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        first_update = self._text == ""

        self._text = text

        self._is_visuals_updated = False

        if first_update:
            self.update_visuals()

        self.update()


class OverlayShortLabelFloating(OverlayShortLabel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.length = None

        self.is_opaque = False

        self._clip_region = None

    def on_mouse_over(self, pos, progress_pos):
        if self.length is None:
            return

        new_time = (self.length * progress_pos) // 1000
        self.text = get_time_txt_short(new_time)

        x_middle = round(self.rect().width() / 2)

        pos.setX(pos.x() - x_middle)
        pos.setY(pos.y() - self.rect().height())
        self.move(pos)
        self.show()

    def on_mouse_left(self):
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)

        if not self._is_visuals_updated:
            self.update_visuals()

        text_box = self.rect().translated(0, 0)
        text_box.setHeight(text_box.height() - 10)

        painter.fillRect(text_box, self.color)
        painter.setPen(self.color_contrast)
        painter.drawText(text_box, Qt.AlignCenter, self.text)

        if self.is_opaque:
            self._clip_region = QRegion(text_box)
            self.draw_triangle(painter, self.rect())
            self.setMask(self._clip_region)

            return

        self.draw_triangle(painter, self.rect())

    def draw_triangle(self, painter, rect):
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = QPainterPath()

        middle_x = round(rect.width() / 2)

        path.moveTo(middle_x - 5, rect.height() - 10)
        path.lineTo(middle_x + 5, rect.height() - 10)
        path.lineTo(middle_x, rect.height())
        path.lineTo(middle_x - 5, rect.height() - 10)

        painter.setPen(Qt.NoPen)
        painter.fillPath(path, self.color)

        if self.is_opaque:
            painter.setClipPath(path)
            self._clip_region = self._clip_region.united(painter.clipRegion())

    def update_visuals(self):
        padding = 10

        metrics = QFontMetrics(self.font())
        size = metrics.size(0, self._text)

        width = size.width() + padding
        height = size.height() + padding + 10

        self.setFixedSize(width, height)

        self._is_visuals_updated = True


class OverlayBar(OverlayWidget):
    @property
    def color_progress(self):
        is_color_reddish = (
            0 <= self.color.hue() <= 50  # noqa: WPS432
            or 310 <= self.color.hue() <= 360  # noqa: WPS221, WPS432
        )

        if is_color_reddish:
            return QColor(Qt.green)

        return QColor(Qt.red)


class OverlayProgressBar(OverlayBar):
    position_changed = pyqtSignal(float)

    mouse_over = pyqtSignal(QPoint, float)
    mouse_left = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMouseTracking(True)

        self._position = 0
        self._loop_start = 0
        self._loop_end = 100
        self.progress_select_x = None

    def leaveEvent(self, event):
        self.update()

        self.mouse_left.emit()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.progress_select_x = self._get_x_within_bounds(event.pos().x())

        self.update()

        top_edge = self.mapToParent(QPoint(self.progress_select_x, 0))
        mouse_position = self.progress_select_x / self.width()

        self.mouse_over.emit(top_edge, mouse_position)

        if QGuiApplication.mouseButtons() == Qt.LeftButton:
            self._update_position(self.progress_select_x)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        """Consume mouse release to avoid pausing from parent event"""

        if event.button() == Qt.LeftButton:
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._update_position(event.pos().x())

        event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Consume to avoid parent event"""
        self.mousePressEvent(event)

        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.fillRect(self.rect(), self.color)

        progress_rect = self.rect().translated(0, 0)

        cur_fill = math.ceil(self.rect().width() * self.position)

        progress_rect.setWidth(cur_fill)

        painter.fillRect(progress_rect, self.color_progress)

        if self.progress_select_x is not None and self.underMouse():
            self.draw_progress_bar_select(painter, self.rect(), progress_rect)

        if self.loop_start > 0:
            self.draw_loop_mark(painter, self.rect(), self.loop_start)

        if self.loop_end < 100:
            self.draw_loop_mark(painter, self.rect(), self.loop_end)

    def draw_progress_bar_select(self, painter, rect, progress_rect):
        progress_rect_sel = rect.translated(0, 0)
        progress_rect_sel.setRight(self.progress_select_x - 1)

        if progress_rect_sel.right() <= progress_rect.right():
            painter.fillRect(progress_rect_sel, Qt.blue)
        else:
            painter.fillRect(progress_rect_sel, self.color_contrast_mid)
            painter.fillRect(progress_rect, Qt.blue)

    def draw_loop_mark(self, painter, rect, loop_mark_percent):
        cur_start_loop_rect = rect.translated(0, 0)
        cur_start_loop = math.ceil(rect.width() * loop_mark_percent)

        cur_start_loop_rect.setX(cur_start_loop)
        cur_start_loop_rect.setWidth(1)

        painter.fillRect(cur_start_loop_rect, Qt.green)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position):
        self._position = position
        self.update()

    @property
    def loop_start(self):
        return self._loop_start

    @loop_start.setter
    def loop_start(self, loop_start):
        self._loop_start = loop_start
        self.update()

    @property
    def loop_end(self):
        return self._loop_end

    @loop_end.setter
    def loop_end(self, loop_end):
        self._loop_end = loop_end
        self.update()

    def _update_position(self, x):
        self.progress_select_x = x
        new_position = self.progress_select_x / self.width()
        self.position_changed.emit(new_position)

    def _get_x_within_bounds(self, x):
        if x < 0:
            return 0
        elif x > self.width():
            return self.width()
        return x


class OverlayVolumeBar(OverlayBar):
    position_changed = pyqtSignal(float)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMaximumHeight(self.minimumHeight() * 4)
        self.setMinimumHeight(10)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.setMouseTracking(True)

        self._position = 0
        self.progress_select_y = None

    def leaveEvent(self, event):
        self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.progress_select_y = self._get_y_within_bounds(event.pos().y())

        self.update()

        if QGuiApplication.mouseButtons() == Qt.LeftButton:
            self._update_position(self.progress_select_y)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._update_position(event.pos().y())
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Consume to avoid parent event"""
        self.mousePressEvent(event)

        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.fillRect(self.rect(), self.color)

        progress_rect = self.rect().translated(0, 0)

        cur_fill = math.ceil(self.rect().height() * self.position)

        progress_rect.setY(self.rect().height() - cur_fill)
        progress_rect.setHeight(cur_fill)

        painter.fillRect(progress_rect, self.color_progress)

        if self.progress_select_y is not None and self.underMouse():
            self.draw_progress_bar_select(painter, self.rect(), progress_rect)

    def draw_progress_bar_select(self, painter, rect, progress_rect):
        progress_rect_sel = rect.translated(0, 0)
        progress_rect_sel.setTop(self.progress_select_y)

        if progress_rect_sel.top() >= progress_rect.top():
            painter.fillRect(progress_rect_sel, Qt.blue)
        else:
            painter.fillRect(progress_rect_sel, self.color_contrast_mid)
            painter.fillRect(progress_rect, Qt.blue)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position):
        self._position = position
        self.update()

    def _update_position(self, y):
        self.progress_select_y = y
        new_position = 1.0 - (self.progress_select_y / self.height())
        self.position_changed.emit(new_position)

    def _get_y_within_bounds(self, y):
        if y < 0:
            return 0
        elif y > self.height():
            return self.height()
        return y
