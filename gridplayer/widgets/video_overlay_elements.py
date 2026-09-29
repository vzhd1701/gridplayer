import math

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRegion,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QSizePolicy, QWidget

from gridplayer.models.seek_mark import SeekMarkKind, chapter_at, segments_at
from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.utils.time_txt import get_time_txt

# A chapter is marked the way mpv marks it: a wedge cut into the top and the
# bottom edge of the bar, which leaves the middle of it to the loop marks'
# full-height lines.
CHAPTER_NOTCH_DEPTH = 3

# The wedges narrow along with the bar, down to a 1px tick, so a small cell
# is not all notches. As (bar width from, half the wedge's width): 7px wide
# from a 280px bar, which is a cell of about 440px, and a tick below 120px.
CHAPTER_NOTCH_WIDTHS = ((280, 3), (200, 2), (120, 1))

# Notches closer than this to the one before, past their own width, are
# left out, so a file with hundreds of chapters does not turn the bar into
# a comb.
CHAPTER_NOTCH_MIN_GAP = 2

# How far the chapter under the mouse stands out from the rest of the bar.
CHAPTER_HOVER_ALPHA = 70

# A chapter name cut down to less than this is no name, and is left off.
HOVER_LABEL_MIN_NAME_PX = 30

# half the width of the pointer under the hover label
HOVER_POINTER_HALF_WIDTH = 5

# Segments are drawn in a band through the middle of the bar, a third of its
# height: over the progress, which still reads above and below them, and
# clear of the edges, where the chapters are notched.
SEGMENT_BAND_FRACTION = 3

# How far off a highlight the mouse can be and still name it, a highlight
# being a place with no length to be over.
HIGHLIGHT_HOVER_PX = 4

# the square of a segment's colour in front of its name, and the gap after it
SEGMENT_SWATCH_PX = 8
SEGMENT_SWATCH_GAP_PX = 5


def chapter_notch_half_width(bar_width: int) -> int:
    """How far a chapter notch reaches either side of its middle, 0 for a tick."""

    for from_width, half_width in CHAPTER_NOTCH_WIDTHS:
        if bar_width >= from_width:
            return half_width

    return 0


class OverlayWidget(QWidget):
    padding = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        font_height = 13
        self._color = QColor(Qt.white)

        # These widgets paint their own pixels. A system/style fill would be
        # opaque and shows up as a solid box under translucent compositing.
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)

        self.setMinimumHeight(font_height + self.padding)

    def set_overlay_opacity(self, opacity):
        # Fade the finished widget, not each stroke. Painter opacity makes
        # text/icons 50% on top of a 50% fill, which is much too dim.
        # A per-widget effect keeps the original contrast (opaque draw, then
        # one 0.5 pass) without a parent-level pixmap that recaches siblings.
        if opacity >= 1:
            self.setGraphicsEffect(None)
        else:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(opacity)
            self.setGraphicsEffect(effect)
        self.update()

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, color):
        self._color = QColor(color)
        self.update()

    @property
    def color_contrast(self):
        lightness = 0 if self.color.lightness() > 127 else 255

        return QColor.fromHsl(self.color.hue(), self.color.saturation(), lightness)

    @property
    def color_contrast_mid(self):
        if self.color.lightness() > 127:
            lightness = self.color.lightness() - 100
        else:
            lightness = self.color.lightness() + 100

        return QColor.fromHsl(self.color.hue(), self.color.saturation(), lightness)


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
        self.marks = ()

        # the segments under the mouse, named on a line of their own below
        # the time: their names and the colour of the first; None for none
        self.segment_line: tuple[str, QColor] | None = None

        self.is_opaque = False

        self._clip_region = None

        # where the pointer sits along the label, None for the middle
        self._pointer_x = None

    def on_mouse_over(self, pos, progress_pos, bar_width):
        if self.length is None:
            return

        time_ms = int(self.length * progress_pos)
        self.text = self._hover_text(time_ms)

        near_ms = self.length * HIGHLIGHT_HOVER_PX / bar_width
        self.segment_line = self._hover_segment_line(time_ms, near_ms)

        # sized now rather than at the next paint, since where it goes
        # depends on how wide it is
        self.update_visuals()

        # a cell too short for a second line above the bar goes without it
        if self.segment_line is not None and pos.y() < self.height():
            self.segment_line = None
            self.update_visuals()

        # kept inside the overlay, with the pointer still under the mouse
        width = self.width()
        overlay_width = self.parentWidget().width()

        left = min(max(pos.x() - width // 2, 0), max(overlay_width - width, 0))

        self._pointer_x = min(
            max(pos.x() - left, HOVER_POINTER_HALF_WIDTH),
            width - HOVER_POINTER_HALF_WIDTH,
        )

        self.move(left, pos.y() - self.height())
        self.show()
        self.update()

    def _hover_text(self, time_ms: int) -> str:
        """The time under the mouse, and the chapter it is in where there is one."""

        time_txt = get_time_txt(time_ms // 1000, strip=True)

        chapter = chapter_at(self.marks, time_ms, self.length)

        if chapter is None:
            return time_txt

        prefix = f"{time_txt} - "

        metrics = QFontMetrics(self.font())

        room = (
            self.parentWidget().width()
            - OverlayWidget.padding * 2
            - metrics.horizontalAdvance(prefix)
        )

        if room < HOVER_LABEL_MIN_NAME_PX:
            return time_txt

        name = metrics.elidedText(chapter[0].label, Qt.ElideRight, room)

        return f"{prefix}{name}"

    def _hover_segment_line(self, time_ms: int, near_ms: float):
        """The segments under the mouse, for the line below the time."""

        segments = segments_at(self.marks, time_ms, near_ms)

        if not segments:
            return None

        metrics = QFontMetrics(self.font())

        room = (
            self.parentWidget().width()
            - OverlayWidget.padding * 2
            - SEGMENT_SWATCH_PX
            - SEGMENT_SWATCH_GAP_PX
        )

        if room < HOVER_LABEL_MIN_NAME_PX:
            return None

        # pieces of one kind that overlap are one kind to name
        names = ", ".join(dict.fromkeys(mark.label for mark in segments))

        return (
            metrics.elidedText(names, Qt.ElideRight, room),
            QColor(segments[0].color),
        )

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

        if self.segment_line is None:
            painter.drawText(text_box, Qt.AlignCenter, self.text)
        else:
            self.draw_two_lines(painter, text_box)

        if self.is_opaque:
            self._clip_region = QRegion(text_box)
            self.draw_triangle(painter, self.rect())
            self.setMask(self._clip_region)

            return

        self.draw_triangle(painter, self.rect())

    def draw_two_lines(self, painter, text_box):
        """The time, over the segments under the mouse by their colour."""

        metrics = QFontMetrics(self.font())
        line_height = metrics.height()

        top = text_box.top() + (text_box.height() - line_height * 2) // 2

        painter.drawText(
            QRect(text_box.left(), top, text_box.width(), line_height),
            Qt.AlignCenter,
            self.text,
        )

        name, color = self.segment_line

        name_left = SEGMENT_SWATCH_PX + SEGMENT_SWATCH_GAP_PX
        line_width = name_left + metrics.horizontalAdvance(name)

        left = text_box.left() + (text_box.width() - line_width) // 2
        top += line_height

        swatch = QRect(
            left,
            top + (line_height - SEGMENT_SWATCH_PX) // 2,
            SEGMENT_SWATCH_PX,
            SEGMENT_SWATCH_PX,
        )

        painter.fillRect(swatch, color)

        # rimmed in the colour of the text, or yellow on white is nowhere
        painter.drawRect(swatch.adjusted(0, 0, -1, -1))

        painter.drawText(
            QRect(left + name_left, top, line_width - name_left, line_height),
            Qt.AlignVCenter | Qt.AlignLeft,
            name,
        )

    def draw_triangle(self, painter, rect):
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = QPainterPath()

        middle_x = self._pointer_x
        if middle_x is None:
            middle_x = round(rect.width() / 2)

        half_width = HOVER_POINTER_HALF_WIDTH

        path.moveTo(middle_x - half_width, rect.height() - 10)
        path.lineTo(middle_x + half_width, rect.height() - 10)
        path.lineTo(middle_x, rect.height())
        path.lineTo(middle_x - half_width, rect.height() - 10)

        painter.setPen(Qt.NoPen)
        painter.fillPath(path, self.color)

        if self.is_opaque:
            painter.setClipPath(path)
            self._clip_region = self._clip_region.united(painter.clipRegion())

    def update_visuals(self):
        padding = 10

        metrics = QFontMetrics(self.font())
        size = metrics.size(0, self._text)

        width = size.width()
        height = size.height()

        if self.segment_line is not None:
            name, _ = self.segment_line

            width = max(
                width,
                SEGMENT_SWATCH_PX
                + SEGMENT_SWATCH_GAP_PX
                + metrics.horizontalAdvance(name),
            )
            height += metrics.height()

        self.setFixedSize(width + padding, height + padding + 10)

        self._is_visuals_updated = True


class OverlayBar(OverlayWidget):
    @property
    def color_progress(self):
        is_color_reddish = 0 <= self.color.hue() <= 50 or 310 <= self.color.hue() <= 360

        if is_color_reddish:
            return QColor(Qt.green)

        return QColor(Qt.red)


class OverlayProgressBar(OverlayBar):
    position_changed = pyqtSignal(float)

    # where the mouse is over the top edge of the bar, how far along it, and
    # how wide the bar is, which says how much of the video a pixel covers
    mouse_over = pyqtSignal(QPoint, float, int)
    mouse_left = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setMinimumWidth(self.minimumHeight())
        self.setMouseTracking(True)

        self._position = 0
        self._loop_start = 0
        self._loop_end = 100
        self._marks = ()
        self.progress_select_x = None

        # the video's length in ms, which the marks are placed against;
        # kept up to date along with the position, and repainted with it
        self.length = 0

    def leaveEvent(self, event):
        self.update()

        self.mouse_left.emit()

        event.ignore()

    def mouseMoveEvent(self, event):
        self.progress_select_x = self._get_x_within_bounds(event.pos().x())

        self.update()

        top_edge = self.mapToParent(QPoint(self.progress_select_x, 0))
        mouse_position = self.progress_select_x / self.width()

        self.mouse_over.emit(top_edge, mouse_position, self.width())

        if QGuiApplication.mouseButtons() == Qt.LeftButton:
            self._update_position(self.progress_select_x)
            event.accept()

            # Send activity event to keep overlay visible
            QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))
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
            self.draw_hovered_chapter(painter)

        self.draw_segments(painter)
        self.draw_chapter_notches(painter)

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

    def draw_hovered_chapter(self, painter):
        """Set the chapter under the mouse apart from the rest of the bar."""

        if not self.length:
            return

        hover_ms = self.progress_select_x / self.width() * self.length

        chapter = chapter_at(self._marks, hover_ms, self.length)

        if chapter is None:
            return

        _, start_ms, end_ms = chapter

        left = self._x_at(start_ms)
        right = self._x_at(end_ms)

        highlight = QColor(self.color_contrast)
        highlight.setAlpha(CHAPTER_HOVER_ALPHA)

        painter.fillRect(QRect(left, 0, right - left, self.height()), highlight)

    def draw_segments(self, painter):
        """Colour the segments in, and put a diamond on each highlight."""

        if not self.length:
            return

        band_top = self.height() // SEGMENT_BAND_FRACTION
        band_height = self.height() - band_top * 2

        highlights = []

        for mark in self._marks:
            if mark.kind == SeekMarkKind.HIGHLIGHT:
                highlights.append(mark)
                continue

            if mark.kind != SeekMarkKind.SEGMENT:
                continue

            left = self._x_at(mark.time_ms)
            right = self._x_at(min(mark.end_ms, self.length))

            # one too short for a pixel of its own is still there
            painter.fillRect(
                QRect(left, band_top, max(right - left, 1), band_height),
                QColor(mark.color),
            )

        if not highlights:
            return

        # taller than the band, so that it stands out of it
        half_size = band_height // 2 + 2
        middle_y = self.height() / 2

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        for mark in highlights:
            x = self._x_at(mark.time_ms)

            painter.setBrush(QColor(mark.color))
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, middle_y - half_size),
                        QPointF(x + half_size, middle_y),
                        QPointF(x, middle_y + half_size),
                        QPointF(x - half_size, middle_y),
                    ]
                )
            )

        painter.restore()

    def draw_chapter_notches(self, painter):
        if not self.length:
            return

        half_width = chapter_notch_half_width(self.width())
        min_gap = half_width * 2 + CHAPTER_NOTCH_MIN_GAP

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color_contrast)

        last_x = None

        for mark in self._marks:
            if mark.kind != SeekMarkKind.CHAPTER:
                continue

            x = self._x_at(mark.time_ms)

            # the ends of the bar mark those places well enough already
            if x <= half_width or x >= self.width() - half_width:
                continue

            if last_x is not None and x - last_x < min_gap:
                continue

            last_x = x

            self._draw_chapter_notch(painter, x, half_width)

        painter.restore()

    def _draw_chapter_notch(self, painter, x, half_width):
        depth = CHAPTER_NOTCH_DEPTH
        bottom = self.height()

        if not half_width:
            # a wedge with no width is no wedge; a tick is what is left
            painter.fillRect(QRect(x, 0, 1, depth), self.color_contrast)
            painter.fillRect(QRect(x, bottom - depth, 1, depth), self.color_contrast)
            return

        # (the edge it is cut into, how far in its point reaches)
        for edge_y, tip_y in ((0, depth), (bottom, bottom - depth)):
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x - half_width, edge_y),
                        QPointF(x + half_width, edge_y),
                        QPointF(x, tip_y),
                    ]
                )
            )

    def _x_at(self, time_ms) -> int:
        return math.ceil(self.width() * time_ms / self.length)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position):
        self._position = position
        self.update()

    @property
    def marks(self):
        return self._marks

    @marks.setter
    def marks(self, marks):
        self._marks = tuple(marks)
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

            # Send activity event to keep overlay visible
            QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))
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


class OverlayBorder(OverlayWidget):
    border_width = 5

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def showEvent(self, event) -> None:
        self._apply_ring_mask()
        super().showEvent(event)

    def resizeEvent(self, event) -> None:
        self._apply_ring_mask()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.color))

        if getattr(self.parent(), "is_opaque", False):
            # Same idea as OverlayShortLabelFloating: clip the paint, then
            # setMask so the opaque parent only maps this ring (not the
            # full stacked-layout rect, which would cover the video).
            painter.setClipPath(self._ring_path())
            painter.drawRect(self.rect())
            self._apply_ring_mask()
            return

        painter.drawRect(self.rect())

    def _apply_ring_mask(self):
        self.setMask(self._ring_region())

    def _ring_path(self) -> QPainterPath:
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        inset = float(self.border_width)
        path.addRect(
            QRectF(
                inset,
                inset,
                max(0.0, self.width() - inset * 2),
                max(0.0, self.height() - inset * 2),
            )
        )
        return path

    def _ring_region(self) -> QRegion:
        inset = self.border_width
        return QRegion(self.rect()) - QRegion(
            QRect(
                inset,
                inset,
                max(0, self.width() - inset * 2),
                max(0, self.height() - inset * 2),
            )
        )


class OverlayDiscBadge(OverlayWidget):
    """Centered disc badge used by drag targets."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setMinimumSize(0, 0)

        self._circle_color = QColor(0, 0, 0)
        self._glyph_color = QColor(255, 255, 255)
        self.hide()

    def set_colors(self, circle: QColor, glyph: QColor) -> None:
        self._circle_color = QColor(circle)
        self._glyph_color = QColor(glyph)
        self.update()

    def resizeEvent(self, event) -> None:
        self._update_mask()

    def paintEvent(self, event) -> None:
        if not self._is_badge_visible():
            return

        painter = QPainter(self)
        painter.setPen(Qt.NoPen)

        if self._is_parent_opaque():
            # Fill the exact X11 mask pixels. drawEllipse() does not match
            # QRegion.Ellipse 1:1, so leftover mask dots showed Window white.
            disc_rect = self._glyph_mask_rect()
            mask = QRegion(disc_rect, QRegion.Ellipse)
            self._set_mask_if_changed(mask)
            painter.setClipRegion(mask)
            painter.fillRect(disc_rect, self._circle_color)
            painter.setRenderHint(QPainter.Antialiasing)
            self._draw_glyph(painter, QRectF(disc_rect))
            return

        circle = self._glyph_rect()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self._circle_color))
        painter.drawEllipse(circle)
        self._draw_glyph(painter, circle)

    def _is_badge_visible(self) -> bool:
        return self.isVisible()

    def _draw_glyph(self, painter: QPainter, circle: QRectF):
        raise NotImplementedError

    def _is_parent_opaque(self) -> bool:
        return bool(getattr(self.parent(), "is_opaque", False))

    def _glyph_rect(self) -> QRectF:
        side = max(min(self.width(), self.height()) * 0.6, 24.0)
        return QRectF(
            (self.width() - side) / 2,
            (self.height() - side) / 2,
            side,
            side,
        )

    def _glyph_mask_rect(self) -> QRect:
        return self._glyph_rect().toAlignedRect()

    def _update_mask(self):
        if not self._is_parent_opaque() or not self._is_badge_visible():
            if not self.mask().isEmpty():
                self.clearMask()
            return

        self._set_mask_if_changed(QRegion(self._glyph_mask_rect(), QRegion.Ellipse))

    def _set_mask_if_changed(self, mask: QRegion) -> None:
        # X11 Shape setMask briefly unmasks the widget; the opaque parent
        # fills Window (default white) over the whole cell.
        if mask != self.mask():
            self.setMask(mask)

    def _show_badge(self):
        self._update_mask()
        self.show()
        self.update()

    def _hide_badge(self):
        self.hide()
        if not self.mask().isEmpty():
            self.clearMask()


class OverlayDropIndicator(OverlayDiscBadge):
    """Full-block drag target glyph: arrows, swap, source asterisk, or dot."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._indicator = DropIndicator.NONE

    @property
    def indicator(self) -> DropIndicator:
        return self._indicator

    def set_indicator(self, indicator: DropIndicator):
        if self._indicator == indicator:
            if indicator == DropIndicator.NONE:
                self._hide_badge()
            return

        was_visible = self._indicator != DropIndicator.NONE
        self._indicator = indicator

        if indicator == DropIndicator.NONE:
            self._hide_badge()
            return

        if was_visible:
            # Same disc mask, new glyph. Re-applying X11 Shape flashes the cell.
            self.update()
            return

        self._show_badge()

    def _is_badge_visible(self) -> bool:
        return self._indicator != DropIndicator.NONE

    def _draw_glyph(self, painter: QPainter, circle: QRectF):
        painter.setBrush(QBrush(self._glyph_color))
        if self._indicator == DropIndicator.SWAP:
            self._draw_swap(painter, circle)
        elif self._indicator == DropIndicator.SOURCE:
            self._draw_asterisk(painter, circle)
        elif self._indicator == DropIndicator.DOT:
            self._draw_dot(painter, circle)
        elif self._indicator == DropIndicator.REPLACE:
            self._draw_replace(painter, circle)
        else:
            self._draw_arrow(painter, circle)

    def _arrow_tip_degrees(self) -> float:
        return {
            DropIndicator.ARROW_RIGHT: 0.0,
            DropIndicator.ARROW_UP: 90.0,
            DropIndicator.ARROW_LEFT: 180.0,
            DropIndicator.ARROW_DOWN: 270.0,
        }[self._indicator]

    def _draw_dot(self, painter: QPainter, circle: QRectF):
        cx, cy = circle.center().x(), circle.center().y()
        radius = circle.width() / 2 * 0.22
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _draw_replace(self, painter: QPainter, circle: QRectF):
        cx, cy = circle.center().x(), circle.center().y()
        arm = circle.width() / 2 * 0.38
        stroke = max(2.0, circle.width() / 2 * 0.145)
        painter.setPen(QPen(self._glyph_color, stroke, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(cx - arm, cy - arm), QPointF(cx + arm, cy + arm))
        painter.drawLine(QPointF(cx + arm, cy - arm), QPointF(cx - arm, cy + arm))

    def _draw_asterisk(self, painter: QPainter, circle: QRectF):
        cx, cy = circle.center().x(), circle.center().y()
        radius = circle.width() / 2
        length = radius * 0.52
        stroke = max(2.0, radius * 0.145)
        painter.setPen(QPen(self._glyph_color, stroke, Qt.SolidLine, Qt.RoundCap))
        for deg in (90.0, 150.0, 210.0):
            rad = math.radians(deg)
            dx = math.cos(rad) * length
            dy = -math.sin(rad) * length
            painter.drawLine(QPointF(cx - dx, cy - dy), QPointF(cx + dx, cy + dy))

    def _draw_arrow(self, painter: QPainter, circle: QRectF):
        # Head plus a short shaft so it reads as an arrow, not a play icon.
        cx, cy = circle.center().x(), circle.center().y()
        scale = circle.width() / 2
        rad = math.radians(self._arrow_tip_degrees())
        ux, uy = math.cos(rad), -math.sin(rad)
        vx, vy = -uy, ux

        # (forward, side) in units of the badge radius; stays inside the disc.
        local = (
            (0.60, 0.00),
            (-0.10, 0.50),
            (-0.10, 0.16),
            (-0.56, 0.16),
            (-0.56, -0.16),
            (-0.10, -0.16),
            (-0.10, -0.50),
        )
        points = [
            QPointF(
                cx + (fwd * ux + side * vx) * scale, cy + (fwd * uy + side * vy) * scale
            )
            for fwd, side in local
        ]
        painter.drawPolygon(QPolygonF(points))

    def _draw_swap(self, painter: QPainter, circle: QRectF):
        cx, cy = circle.center().x(), circle.center().y()
        radius = circle.width() / 2
        arc_r = radius * 0.44
        stroke = max(2.0, radius * 0.145)
        color = self._glyph_color

        pen = QPen(color, stroke, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        arc_rect = QRectF(cx - arc_r, cy - arc_r, 2 * arc_r, 2 * arc_r)
        span = 118
        starts = (42, 222)
        painter.drawArc(arc_rect, int(starts[0] * 16), span * 16)
        painter.drawArc(arc_rect, int(starts[1] * 16), span * 16)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        self._draw_arc_arrow_head(painter, cx, cy, arc_r, starts[0] + span, stroke)
        self._draw_arc_arrow_head(painter, cx, cy, arc_r, starts[1] + span, stroke)

    def _draw_arc_arrow_head(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        r: float,
        angle_deg: float,
        stroke: float,
    ):
        rad = math.radians(angle_deg)
        tx, ty = -math.sin(rad), -math.cos(rad)
        nx, ny = -ty, tx

        px = cx + r * math.cos(rad)
        py = cy - r * math.sin(rad)
        tip = QPointF(px + tx * stroke * 1.55, py + ty * stroke * 1.55)
        half = stroke * 1.35
        back = stroke * 0.45
        bx, by = px - tx * back, py - ty * back
        painter.drawPolygon(
            QPolygonF(
                [
                    tip,
                    QPointF(bx + nx * half, by + ny * half),
                    QPointF(bx - nx * half, by - ny * half),
                ]
            )
        )
