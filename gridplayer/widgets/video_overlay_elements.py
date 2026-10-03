import math
from typing import NamedTuple

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBitmap,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRegion,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QSizePolicy, QWidget

from gridplayer.models.seek_mark import SeekMarkKind, chapter_at, segments_at
from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.utils.bookmarks import bookmark_on
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.utils.qt import translate
from gridplayer.utils.time_txt import ms_time_txt

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

# half the width of the pointer under the hover label, and its height
HOVER_POINTER_HALF_WIDTH = 5
HOVER_POINTER_HEIGHT = 10

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


class MarkerSize(NamedTuple):
    """The size of a bookmark's marker."""

    # how far it reaches either side of its middle
    half_width: float
    # how far down it hangs, to the tip of its point
    height: float
    # how much of that is the point, below its sides
    point: float


# A bookmark is marked by a marker pointing down at its place on the bar, the
# kind a video editor puts on its timeline: amber, or the colour the viewer
# gave it, where chapters are notched in the bar's own contrast colour, and
# rimmed in that colour so that it reads over the video behind it. The
# markers stand on a strip of their own right above the bar rather than on
# it, which leaves a click on the bar to seek exactly where it is, and a
# click on a marker to go exactly to its bookmark.
BOOKMARK_COLOR = "#ffab00"
BOOKMARK_MARKER = MarkerSize(half_width=3, height=9, point=4)

# the strip the markers stand on, their points on its last row
BOOKMARK_STRIP_HEIGHT = 13

# The one under the mouse becomes the hover label's pointer, grown, standing
# where it did with its point on the same row: the label names it where it
# is, and sits as low over it as it does over the bar.
BOOKMARK_TAIL = MarkerSize(half_width=4, height=BOOKMARK_STRIP_HEIGHT - 0.5, point=5)

# How far off a marker's middle the mouse can be and still be over it: half
# the width it grows to, and a pixel to spare.
BOOKMARK_HOVER_PX = BOOKMARK_TAIL.half_width + 1

# A marker standing for bookmarks of different colours is striped with them
# side by side, as many as there is room for across it: a pixel or two each.
BOOKMARK_STRIPES_MAX = 3

# In the hover label, the bookmarks of a marker are a row each, each name
# after its marker in its colour, as the bar draws it: at most this many
# rows, the last saying how many more there are past them.
BOOKMARK_ROWS_MAX = 4
BOOKMARK_ROW_MARKER_PX = int(BOOKMARK_MARKER.half_width * 2) + 1
BOOKMARK_ROW_MARKER_GAP_PX = 4

# how many more there are is said fainter than the names
BOOKMARK_MORE_OPACITY = 0.7


def chapter_notch_half_width(bar_width: int) -> int:
    """How far a chapter notch reaches either side of its middle, 0 for a tick."""

    for from_width, half_width in CHAPTER_NOTCH_WIDTHS:
        if bar_width >= from_width:
            return half_width

    return 0


def marker_shape(middle_x: float, top: float, size: MarkerSize) -> QPolygonF:
    """A bookmark's marker hanging from top, pointed at its foot."""

    bottom = top + size.height
    sides = bottom - size.point

    return QPolygonF(
        [
            QPointF(middle_x - size.half_width, top),
            QPointF(middle_x + size.half_width, top),
            QPointF(middle_x + size.half_width, sides),
            QPointF(middle_x, bottom),
            QPointF(middle_x - size.half_width, sides),
        ]
    )


def marker_colors(colors) -> list[QColor]:
    """What a marker is drawn in, given the colours of the bookmarks it
    stands for: each once, first to last; the bookmarks' own for one given
    none."""

    shown = []

    for color in colors:
        color = color or BOOKMARK_COLOR

        if color not in shown:
            shown.append(color)

    if not shown:
        shown.append(BOOKMARK_COLOR)

    return [QColor(color) for color in shown[:BOOKMARK_STRIPES_MAX]]


def bookmark_colors(bookmarks) -> list[QColor]:
    """What the marker of these bookmarks is drawn in."""

    return marker_colors(bookmark.color for bookmark in bookmarks)


def _stripe_edges(left: float, right: float, count: int) -> list[float]:
    """Where stripes side by side across left to right part, on whole pixels;
    of three, the outer two as wide as each other."""

    inner = [
        math.floor(left + (right - left) * i / count + 0.5) for i in range(1, count)
    ]

    if count == 3:
        inner[1] = left + right - inner[0]

    return [left - 1, *inner, right + 1]


def _draw_shape(painter, shape: QPolygonF | QPainterPath):
    if isinstance(shape, QPainterPath):
        painter.drawPath(shape)
    else:
        painter.drawPolygon(shape)


def fill_bookmark_marker(painter, shape: QPolygonF | QPainterPath, colors):
    """A marker's inside in its colours, striped where it has several.

    The stripes part on whole pixels, which keeps them sharp: a part across
    a pixel's middle would blend the two colours into a third.
    """

    painter.save()
    painter.setPen(Qt.NoPen)

    if len(colors) == 1:
        painter.setBrush(colors[0])
        _draw_shape(painter, shape)
        painter.restore()
        return

    bounds = shape.boundingRect()
    edges = _stripe_edges(bounds.left(), bounds.right(), len(colors))

    for color, left, right in zip(colors, edges, edges[1:]):
        painter.save()
        painter.setClipRect(
            QRectF(left, bounds.top() - 1, right - left, bounds.height() + 2),
            Qt.IntersectClip,
        )
        painter.setBrush(color)
        _draw_shape(painter, shape)
        painter.restore()

    painter.restore()


def draw_bookmark_marker(painter, shape: QPolygonF, colors, rim: QColor):
    """A marker in its colours, rimmed all round in a hairline, so that it
    reads over whatever is behind it."""

    fill_bookmark_marker(painter, shape, colors)

    pen = QPen(rim)
    pen.setCosmetic(True)

    painter.save()
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPolygon(shape)
    painter.restore()


def bookmark_markers(marks, length: int, bar_width: int) -> list[tuple[int, list]]:
    """Where along the bar each marker stands, and the bookmarks it stands for.

    Bookmarks nearer together than a marker is wide share one: stood over one
    another they would read as a smudge, with the one on top hiding the rest.
    Those at the ends are kept whole above the bar, grown under the mouse as
    well.
    """

    if not length:
        return []

    bookmarks = sorted(
        (mark for mark in marks if mark.kind == SeekMarkKind.BOOKMARK),
        key=lambda mark: mark.time_ms,
    )

    edge = BOOKMARK_TAIL.half_width
    min_gap = BOOKMARK_MARKER.half_width * 2

    markers = []

    # Shared or not by how far apart they are exactly, which only grows as
    # the bar does: by whole pixels, two at the edge of sharing one would
    # part and join again pixel after pixel as the window is resized, the
    # pixels each is rounded to coming nearer and farther in turn. Each
    # stands at a whole pixel; one past where the one before it stands by
    # the gap or more lands as far from it or farther.
    group_x = None

    for mark in bookmarks:
        exact_x = bar_width * mark.time_ms / length
        exact_x = min(max(exact_x, edge), bar_width - edge - 1)

        if group_x is not None and exact_x - group_x < min_gap:
            markers[-1][1].append(mark)
            continue

        group_x = exact_x
        markers.append((math.ceil(exact_x), [mark]))

    return markers


def marker_under(markers, mouse_x: float) -> int | None:
    """Which of the markers the mouse is over, the nearest, None for none."""

    near = [
        (abs(x - mouse_x), index)
        for index, (x, _) in enumerate(markers)
        if abs(x - mouse_x) <= BOOKMARK_HOVER_PX
    ]

    return min(near)[1] if near else None


class _UnderLine(NamedTuple):
    """A line below the time in the hover label."""

    text: str
    # the colour of the square in front of it, None for none
    color: QColor | None
    is_bold: bool = False
    # the colour of a bookmark's marker in front of it, None for none
    marker: QColor | None = None
    # said after it, fainter: how many more there are than are named
    after: str = ""
    # one of a list, lined up on the left with the rest of it, its text as
    # far in as theirs whether it has a marker or not
    is_listed: bool = False


def _bold_font(font: QFont) -> QFont:
    bold = QFont(font)
    bold.setBold(True)

    return bold


def _after_txt(line: _UnderLine) -> str:
    """What is said after a line's text, a space between them."""

    if not line.after or not line.text:
        return line.after

    return f" {line.after}"


def _line_advance(line: _UnderLine, font: QFont) -> int:
    """How wide a line's text is, in bold where it is, and what is said
    after it."""

    text_metrics = QFontMetrics(_bold_font(font) if line.is_bold else font)
    after_metrics = QFontMetrics(font)

    return text_metrics.horizontalAdvance(line.text) + after_metrics.horizontalAdvance(
        _after_txt(line)
    )


def _swatch_width(line: _UnderLine) -> int:
    """How far in a line's text starts, past the square or the marker in
    front of it."""

    if line.color is not None:
        return SEGMENT_SWATCH_PX + SEGMENT_SWATCH_GAP_PX

    if line.is_listed:
        return BOOKMARK_ROW_MARKER_PX + BOOKMARK_ROW_MARKER_GAP_PX

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
    # cut to a new shape on the opaque overlay, which cuts its window to it
    shape_changed = pyqtSignal()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.length = None
        self.marks = ()

        # the bookmarks of the marker under the mouse, named below the time a
        # row each; none for none
        self.bookmark_rows: tuple[_UnderLine, ...] = ()

        # where the video is, for the one of a marker's it is on
        self.position = 0

        # the marker under the mouse: where, its bookmarks, and how wide the
        # bar is; None while it is over none
        self._marker = None

        # which of its bookmarks the video is on, where it stands for several
        self._bookmark_on = None

        # the segments under the mouse, named on a line of their own below
        # that: their names and the colour of the first; None for none
        self.segment_line: tuple[str, QColor] | None = None

        self.is_opaque = False

        # where the pointer sits along the label, None for the middle
        self._pointer_x = None

        # over a bookmark's marker, whose place the pointer takes
        self._is_on_marker = False

    def on_mouse_over(self, pos, progress_pos, bar_width):
        """The mouse over the bar: the time there, and what it is in.

        Bookmarks are named over their markers only, where a click goes to
        them; over the bar, one goes exactly where the mouse is.
        """

        if self.length is None:
            return

        self._is_on_marker = False
        self._marker = None
        self._bookmark_on = None

        self._show_at(pos, int(self.length * progress_pos), bar_width, ())

    def on_marker_over(self, pos, bookmarks, bar_width):
        """The mouse over a bookmark's marker: where it is, and every bookmark
        it stands for, with the marker for the label's pointer.

        Each bookmark is a row, after its marker in its colour, as the
        segments' names are after their squares; of a marker standing for
        several, that tells the stripes of the pointer apart, the one the
        video is on is in bold, and its time is the one told; a click goes
        to the one after it.
        """

        if self.length is None:
            return

        self._is_on_marker = True
        self._marker = (pos, bookmarks, bar_width)

        self._show_marker()

    def on_position(self, position):
        """The video somewhere else: over a marker standing for several,
        the one it is on may be another."""

        self.position = position

        if self._marker is None or not self.isVisible():
            return

        if self._on_marker_bookmark() != self._bookmark_on:
            self._show_marker()

    def _on_marker_bookmark(self) -> int | None:
        _, bookmarks, _ = self._marker

        if len(bookmarks) < 2:
            return None

        return bookmark_on(bookmarks, self.position)

    def _show_marker(self):
        pos, bookmarks, bar_width = self._marker

        self._bookmark_on = self._on_marker_bookmark()
        told = bookmarks[0 if self._bookmark_on is None else self._bookmark_on]

        self._show_at(pos, told.time_ms, bar_width, bookmarks)

    def _show_at(self, pos, time_ms, bar_width, bookmarks):
        self.text = self._hover_text(time_ms)

        rows = BOOKMARK_ROWS_MAX
        self.bookmark_rows = self._bookmark_rows(bookmarks, rows)

        near_ms = self.length * HIGHLIGHT_HOVER_PX / bar_width
        self.segment_line = self._hover_segment_line(time_ms, near_ms)

        # sized now rather than at the next paint, since where it goes
        # depends on how wide it is
        self.update_visuals()

        # a cell too short for the lines below the time above the bar goes
        # without them: SponsorBlock's first, then the bookmarks' a row at a
        # time, down to one
        if self.segment_line is not None and pos.y() < self.height():
            self.segment_line = None
            self.update_visuals()

        while self.bookmark_rows and pos.y() < self.height():
            rows = min(rows, len(self.bookmark_rows)) - 1
            self.bookmark_rows = self._bookmark_rows(bookmarks, rows)
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
        self._update_shape()
        self.update()

    def _bookmark_rows(self, bookmarks, most: int) -> tuple[_UnderLine, ...]:
        """The bookmarks of the marker under the mouse, in at most this many
        rows; none where even one has no room.

        Each is a row, its name after its marker. Past the rows there is room
        for, those around the one the video is on are named, one before it
        where there is one, and the last row says how many more there are; on
        a single row, the one the video is on says it after its name.
        """

        if most < 1 or not bookmarks:
            return ()

        on = self._bookmark_on
        count = len(bookmarks)

        if count <= most:
            named = range(count)
        elif most == 1:
            named = [0 if on is None else on]
        else:
            first = 0 if on is None else min(max(on - 1, 0), count - (most - 1))
            named = range(first, first + most - 1)

        more = count - len(named)
        more_txt = (
            translate("Bookmarks", "+{COUNT} more").format(COUNT=more) if more else ""
        )
        # one row has no room for another to say how many more
        after = more_txt if most == 1 else ""

        rows = []

        for index in named:
            bookmark = bookmarks[index]
            is_bold = index == on

            name = self._bookmark_row_text(bookmark.label, is_bold, after)

            if name is None:
                return ()

            rows.append(
                _UnderLine(
                    name,
                    None,
                    is_bold,
                    marker=bookmark_colors((bookmark,))[0],
                    after=after,
                    is_listed=True,
                )
            )

        if more and not after:
            rows.append(_UnderLine("", None, after=more_txt, is_listed=True))

        return tuple(rows)

    def _bookmark_row_text(self, name: str, is_bold: bool, after: str) -> str | None:
        """A bookmark's name cut down to what fits on its row, past its
        marker and before what is said after it; None where none does."""

        font = _bold_font(self.font()) if is_bold else self.font()

        room = (
            self.parentWidget().width()
            - OverlayWidget.padding * 2
            - BOOKMARK_ROW_MARKER_PX
            - BOOKMARK_ROW_MARKER_GAP_PX
        )

        if after:
            room -= QFontMetrics(self.font()).horizontalAdvance(f" {after}")

        if room < HOVER_LABEL_MIN_NAME_PX:
            return None

        return QFontMetrics(font).elidedText(name, Qt.ElideRight, room)

    def _update_shape(self):
        """Cut the label to its box and its pointer, on the opaque overlay.

        Once it is in place and before it paints, never while it paints: the
        overlay cuts its window to what is on it, and whatever is outside
        that is not painted at all. A shape changed while painting comes too
        late for the paint it is changed in.
        """

        if not self.is_opaque:
            return

        shape = QRegion(self._text_box()) + self._pointer_region()

        if shape != self.mask():
            self.setMask(shape)

        self.shape_changed.emit()

    def _pointer_region(self) -> QRegion:
        if not self._is_on_marker:
            return QRegion(self._pointer().toPolygon())

        # the marker as painted, its rim and all
        painted = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
        painted.fill(Qt.transparent)

        painter = QPainter(painted)
        self.draw_pointer(painter)
        painter.end()

        return QRegion(QBitmap.fromImage(painted.createAlphaMask()))

    def _hover_text(self, time_ms: int) -> str:
        """The time under the mouse, to the millisecond, and the chapter it is
        in where there is one."""

        time_txt = ms_time_txt(time_ms, strip=True)

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

        # pieces of one kind that overlap are one kind to name
        names = ", ".join(dict.fromkeys(mark.label for mark in segments))

        text = self._segment_line_text(names)

        if text is None:
            return None

        return text, QColor(segments[0].color)

    def _segment_line_text(self, names: str) -> str | None:
        """Names cut down to what fits past their square, None where none
        do."""

        room = (
            self.parentWidget().width()
            - OverlayWidget.padding * 2
            - SEGMENT_SWATCH_PX
            - SEGMENT_SWATCH_GAP_PX
        )

        if room < HOVER_LABEL_MIN_NAME_PX:
            return None

        return QFontMetrics(self.font()).elidedText(names, Qt.ElideRight, room)

    def _under_lines(self) -> list[_UnderLine]:
        """The lines below the time: the bookmarks, then the segments."""

        lines = list(self.bookmark_rows)

        if self.segment_line is not None:
            name, color = self.segment_line
            lines.append(_UnderLine(name, color))

        return lines

    def on_mouse_left(self):
        self._marker = None
        self._bookmark_on = None

        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)

        if not self._is_visuals_updated:
            self.update_visuals()

        text_box = self._text_box()

        painter.fillRect(text_box, self.color)
        painter.setPen(self.color_contrast)

        under_lines = self._under_lines()

        if under_lines:
            self.draw_lines(painter, text_box, under_lines)
        else:
            painter.drawText(text_box, Qt.AlignCenter, self.text)

        self.draw_pointer(painter)

    def _pointer_height(self) -> int:
        if self._is_on_marker:
            return BOOKMARK_STRIP_HEIGHT

        return HOVER_POINTER_HEIGHT

    def _text_box(self) -> QRect:
        """Where the text goes, above the pointer."""

        text_box = self.rect()
        text_box.setHeight(text_box.height() - self._pointer_height())

        return text_box

    def _pointer(self) -> QPolygonF:
        """The pointer below the text, over where the mouse is: over a
        bookmark's marker, the marker, standing where it stands on the strip."""

        middle_x = self._pointer_x
        if middle_x is None:
            middle_x = round(self.width() / 2)

        bottom = self.height()
        top = bottom - self._pointer_height()

        if self._is_on_marker:
            return marker_shape(middle_x + 0.5, top, BOOKMARK_TAIL)

        half_width = HOVER_POINTER_HALF_WIDTH

        return QPolygonF(
            [
                QPointF(middle_x - half_width, top),
                QPointF(middle_x + half_width, top),
                QPointF(middle_x, bottom),
            ]
        )

    def draw_lines(self, painter, text_box, under_lines: list[_UnderLine]):
        """The time, over what is under the mouse, each by its colour."""

        metrics = QFontMetrics(self.font())
        line_height = metrics.height()

        top = (
            text_box.top()
            + (text_box.height() - line_height * (1 + len(under_lines))) // 2
        )

        painter.drawText(
            QRect(text_box.left(), top, text_box.width(), line_height),
            Qt.AlignCenter,
            self.text,
        )

        bold_font = _bold_font(self.font())

        # the rows of a list lined up on the left, the list in the middle
        listed_width = max(
            (
                _swatch_width(line) + _line_advance(line, self.font())
                for line in under_lines
                if line.is_listed
            ),
            default=0,
        )

        for line in under_lines:
            name_left = _swatch_width(line)

            if line.is_listed:
                line_width = listed_width
            else:
                line_width = name_left + _line_advance(line, self.font())

            left = text_box.left() + (text_box.width() - line_width) // 2
            top += line_height

            if line.color is not None:
                self._draw_square_swatch(painter, left, top, line_height, line.color)

            if line.marker is not None:
                self._draw_row_marker(painter, left, top, line_height, line.marker)

            text_left = left + name_left

            if line.text:
                painter.setFont(bold_font if line.is_bold else self.font())
                text_width = painter.fontMetrics().horizontalAdvance(line.text)

                painter.drawText(
                    QRect(text_left, top, text_width, line_height),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    line.text,
                )

                text_left += text_width
                painter.setFont(self.font())

            after = _after_txt(line)

            if after:
                painter.save()
                painter.setOpacity(BOOKMARK_MORE_OPACITY)
                painter.drawText(
                    QRect(
                        text_left,
                        top,
                        painter.fontMetrics().horizontalAdvance(after),
                        line_height,
                    ),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    after,
                )
                painter.restore()

    def _draw_row_marker(self, painter, left, top, line_height, color: QColor):
        """A bookmark's marker in front of its name, as the bar draws it,
        its rim on the pixel grid."""

        size = BOOKMARK_MARKER

        shape = marker_shape(
            left + size.half_width + 0.5,
            top + (line_height - size.height) // 2 + 0.5,
            size,
        )

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        draw_bookmark_marker(painter, shape, [color], self.color_contrast)
        painter.restore()

    @staticmethod
    def _draw_square_swatch(painter, left, top, line_height, color):
        swatch = QRect(
            left,
            top + (line_height - SEGMENT_SWATCH_PX) // 2,
            SEGMENT_SWATCH_PX,
            SEGMENT_SWATCH_PX,
        )

        painter.fillRect(swatch, color)

        # rimmed in the colour of the text, or yellow on white is nowhere
        painter.drawRect(swatch.adjusted(0, 0, -1, -1))

    def draw_pointer(self, painter):
        painter.setRenderHint(QPainter.Antialiasing, True)

        pointer = self._pointer()

        if self._is_on_marker:
            bookmarks = self._marker[1] if self._marker is not None else ()
            fill_bookmark_marker(painter, pointer, bookmark_colors(bookmarks))

            # rimmed as the markers are, down its sides and round its point;
            # along its top it runs into the label
            rim = QPen(self.color_contrast)
            rim.setCosmetic(True)

            painter.setPen(rim)
            painter.drawPolyline(QPolygonF([*list(pointer)[1:], pointer[0]]))
            return

        path = QPainterPath()
        path.addPolygon(pointer)
        path.closeSubpath()

        painter.setPen(Qt.NoPen)
        painter.fillPath(path, self.color)

    def update_visuals(self):
        padding = 10

        metrics = QFontMetrics(self.font())
        size = metrics.size(0, self._text)

        width = size.width()
        height = size.height()

        for line in self._under_lines():
            width = max(width, _swatch_width(line) + _line_advance(line, self.font()))
            height += metrics.height()

        self.setFixedSize(width + padding, height + padding + self._pointer_height())

        self._is_visuals_updated = True


class OverlayBar(OverlayWidget):
    @property
    def color_progress(self):
        is_color_reddish = 0 <= self.color.hue() <= 50 or 310 <= self.color.hue() <= 360

        if is_color_reddish:
            return QColor(Qt.green)

        return QColor(Qt.red)

    @property
    def color_select(self):
        """What has been played, while the mouse is over the bar."""

        return QColor(Qt.blue)

    @property
    def color_ahead(self):
        """What is ahead, up to the mouse, while it is over the bar."""

        return self.color_contrast_mid


class OverlayProgressBar(OverlayBar):
    position_changed = pyqtSignal(float)

    # where the mouse is over the top edge of the bar, how far along it, and
    # how wide the bar is, which says how much of the video a pixel covers
    mouse_over = pyqtSignal(QPoint, float, int)
    mouse_left = pyqtSignal()

    # moved, resized, shown or hidden, whether the overlay is on screen or
    # not: the bookmarks' markers above it follow it
    placed = pyqtSignal()

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

    def moveEvent(self, event):
        super().moveEvent(event)

        self.placed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.placed.emit()

    def setVisible(self, visible):
        # shown again at every tick of the position, which is no news
        was_hidden = self.isHidden()

        super().setVisible(visible)

        if self.isHidden() != was_hidden:
            self.placed.emit()

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
            painter.fillRect(progress_rect_sel, self.color_select)
        else:
            painter.fillRect(progress_rect_sel, self.color_ahead)
            painter.fillRect(progress_rect, self.color_select)

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


class OverlayBookmarkMarkers(OverlayWidget):
    """The bookmarks' markers, on a strip of their own right above the bar.

    It follows the bar about, and is up while the bar is and there are
    bookmarks to mark. Only the markers are its own: the mouse anywhere else
    on it is left to the video behind, and the opaque overlay cuts its window
    to the markers alone. The one under the mouse is left to the hover label,
    which takes it for its pointer.
    """

    # the mouse over a marker: the bar's top edge below its middle, in the
    # parent's coordinates, the bookmarks it stands for, and how wide the bar
    # is, which says how much of the video a pixel covers
    marker_over = pyqtSignal(QPoint, tuple, int)
    marker_left = pyqtSignal()

    # a marker clicked, by the times of the bookmarks it stands for
    marker_clicked = pyqtSignal(tuple)

    # a marker's menu asked for: where, and the times of its bookmarks
    marker_menu_requested = pyqtSignal(QPoint, tuple)

    # cut to a new shape on the opaque overlay, which cuts its window to it
    shape_changed = pyqtSignal()

    def __init__(self, bar: OverlayProgressBar, **kwargs):
        super().__init__(**kwargs)

        self._bar = bar

        self._bookmarks = ()
        self._length = 0

        # (where along the bar, the bookmarks it stands for)
        self._markers = []
        self._hovered = None

        # a click taken on a marker, whose release is taken with it
        self._is_pressed = False

        self.is_opaque = False

        self.setMouseTracking(True)
        self.setFixedHeight(BOOKMARK_STRIP_HEIGHT)
        self.hide()

        bar.placed.connect(self._follow_bar)

    @property
    def markers(self) -> list[tuple[int, list]]:
        return self._markers

    def set_marks(self, marks):
        self._bookmarks = tuple(
            mark for mark in marks if mark.kind == SeekMarkKind.BOOKMARK
        )

        self._follow_bar()

    def set_length(self, length):
        if length == self._length:
            return

        self._length = length

        self._follow_bar()

    def _follow_bar(self):
        bar = self._bar

        self.setGeometry(bar.x(), bar.y() - self.height(), bar.width(), self.height())

        self._update_markers()

        self.setVisible(not bar.isHidden() and bool(self._markers))

    def _update_markers(self):
        markers = bookmark_markers(self._bookmarks, self._length, self.width())

        if markers == self._markers:
            return

        # the one the label names may be gone, or somewhere else
        self._set_hovered(None)

        self._markers = markers

        self.update_shape()
        self.update()

        # the mouse still over the strip: over whichever is under it now,
        # without waiting for it to move
        if self.isVisible():
            mouse = self.mapFromGlobal(QCursor.pos())

            if self.rect().contains(mouse):
                self._set_hovered(marker_under(self._markers, mouse.x()))

    def update_shape(self):
        """Cut the strip to its markers as they are painted, on the opaque
        overlay, all but the one the hover label has taken.

        Its window is painted in the overlay's colour wherever it is not cut
        away, so a marker cut out any bigger stands on a box of it. Only
        there, too: a widget faded by a graphics effect paints nothing
        through a cut at all.
        """

        if not self.is_opaque:
            return

        if not self._markers:
            self.clearMask()
            self.shape_changed.emit()
            return

        painted = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
        painted.fill(Qt.transparent)

        painter = QPainter(painted)
        self._paint_markers(painter)
        painter.end()

        self.setMask(QRegion(QBitmap.fromImage(painted.createAlphaMask())))
        self.shape_changed.emit()

    def _marker_at(self, x: int) -> tuple[int, list] | None:
        index = marker_under(self._markers, x)

        if index is None:
            return None

        return self._markers[index]

    def mouseMoveEvent(self, event):
        self._set_hovered(marker_under(self._markers, event.pos().x()))

        # the cell sees it all the same, which keeps the overlay up
        event.ignore()

    def leaveEvent(self, event):
        self._set_hovered(None)

    def hideEvent(self, event):
        self._set_hovered(None)

    def _set_hovered(self, index):
        if index == self._hovered:
            return

        self._hovered = index
        self.update()

        # The label takes it before the strip lets it go, and gives it back
        # after, or the opaque overlay's window would be cut to neither for a
        # moment, and show the video where it is.
        if index is None:
            self.update_shape()
            self.marker_left.emit()
            return

        x, bookmarks = self._markers[index]

        self.marker_over.emit(
            self.mapToParent(QPoint(x, self.height())), tuple(bookmarks), self.width()
        )

        self.update_shape()

    # A click on a marker is taken, the whole of it, or the video behind
    # would take it for its own; one beside the markers is left to the video.

    def mousePressEvent(self, event):
        marker = self._marker_at(event.pos().x())

        self._is_pressed = marker is not None

        if marker is None:
            event.ignore()
            return

        if event.button() == Qt.LeftButton:
            _, bookmarks = marker
            self.marker_clicked.emit(tuple(mark.time_ms for mark in bookmarks))

        event.accept()

    def mouseReleaseEvent(self, event):
        event.setAccepted(self._is_pressed)

        self._is_pressed = False

    def mouseDoubleClickEvent(self, event):
        event.setAccepted(self._marker_at(event.pos().x()) is not None)

    def contextMenuEvent(self, event):
        marker = self._marker_at(event.pos().x())

        if marker is None:
            event.ignore()
            return

        _, bookmarks = marker

        self.marker_menu_requested.emit(
            event.globalPos(), tuple(mark.time_ms for mark in bookmarks)
        )

        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)

        self._paint_markers(painter)

    def _paint_markers(self, painter):
        painter.setRenderHint(QPainter.Antialiasing, True)

        for index, (x, bookmarks) in enumerate(self._markers):
            # the hover label's pointer for now, drawn by the label
            if index != self._hovered:
                self._draw_marker(painter, x, BOOKMARK_MARKER, bookmarks)

    def _draw_marker(self, painter, x, size: MarkerSize, bookmarks):
        # its point on the strip's last row, just above the bar, and its rim
        # a hairline on the pixel grid whatever the screen's scale
        top = self.height() - size.height - 0.5

        draw_bookmark_marker(
            painter,
            marker_shape(x + 0.5, top, size),
            bookmark_colors(bookmarks),
            self.color_contrast,
        )


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
            painter.fillRect(progress_rect_sel, self.color_select)
        else:
            painter.fillRect(progress_rect_sel, self.color_ahead)
            painter.fillRect(progress_rect, self.color_select)

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
