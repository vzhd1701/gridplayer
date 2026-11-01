from collections.abc import Callable, Sequence

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from PyQt5.QtGui import (
    QBitmap,
    QBrush,
    QColor,
    QGuiApplication,
    QPainter,
    QPainterPath,
)
from PyQt5.QtWidgets import QWidget

from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.layout.free_tiles import Gap, Guide, GuideKind
from gridplayer.utils.layout.lines import SnapKind, Target
from gridplayer.utils.qt import translate

# a light line with a dark edge either side, to show over any picture
LINE_COLOR = QColor("#eeeeee")
EDGE_COLOR = QColor("#111111")
# the pill a snap's words are on, as the editors' popups are
TAG_BACK_COLOR = QColor("#1e1e1e")
TAG_BORDER_COLOR = QColor("#474747")


def snap_word(target: Target, is_column: bool) -> str:
    """What a line that snapped says it stopped at: for a video that fits,
    on which side of it."""

    if target.kind is SnapKind.ALIGNED:
        return translate("Grid Lines", "Aligned")
    if target.kind is SnapKind.EVEN:
        return translate("Grid Lines", "Even")

    if target.side == 0:
        return translate("Grid Lines", "Both fit")
    if is_column:
        if target.side < 0:
            return translate("Grid Lines", "Left fits")
        return translate("Grid Lines", "Right fits")
    if target.side < 0:
        return translate("Grid Lines", "Top fits")
    return translate("Grid Lines", "Bottom fits")


def tile_snap_words(
    guides: list[Guide], fits: bool = False, has_gaps: bool = False
) -> str:
    """What a tile moved in Free Tiles is in line with, in words: its
    middle at the page's, an edge at the page's middle or at its edge,
    another tile beside it, another's edges or middle; sized, an edge back
    where it started; sized to any shape, its video's (see TileDrag.fits);
    and the room beside it as much as others have (see TileDrag.gaps)."""

    kinds = {guide.kind for guide in guides}
    words = []
    if fits:
        words.append(translate("Free Tiles", "Fits"))
    if GuideKind.START in kinds:
        words.append(translate("Free Tiles", "Old edge"))
    if GuideKind.CENTERED in kinds:
        words.append(translate("Free Tiles", "Centered"))
    if has_gaps:
        words.append(translate("Free Tiles", "Same gap"))
    if GuideKind.PAGE_MIDDLE in kinds:
        words.append(translate("Free Tiles", "Page middle"))
    if GuideKind.PAGE_EDGE in kinds:
        words.append(translate("Free Tiles", "Page edge"))
    if GuideKind.TOUCHING in kinds:
        words.append(translate("Free Tiles", "Touching"))
    if GuideKind.EDGES in kinds:
        words.append(translate("Free Tiles", "Edges lined up"))
    if GuideKind.MIDDLES in kinds:
        words.append(translate("Free Tiles", "Middles lined up"))
    return ", ".join(words)


class FloatingMark(QWidget):
    """Something shown over the player: a line, a word, a tile's frame.

    A window of its own, as a tip is: nothing painted in the player's own
    window shows over a hardware video, which is a native window. It never
    takes the mouse, nor is it ever made the active window.
    """

    # how many have been shown, one after another: the last on top of the
    # others
    shown_count = 0

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.ToolTip
            | Qt.FramelessWindowHint
            | Qt.WindowTransparentForInput
            | Qt.NoDropShadowWindowHint,
        )

        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def show_at(self, rect: QRect) -> None:
        """Shown at rect on the screen, painted anew if it is not the size
        it was."""

        if rect != self.geometry():
            if rect.size() != self.size():
                self.update()
            self.setGeometry(rect)
        self._placed()

        if self.isHidden():
            self.show()
            FloatingMark.shown_count += 1

            # made on its first show, the window can be put where the
            # geometry says in device pixels, on a screen that scales
            if self.geometry() != rect:
                self.setGeometry(rect)
                self._placed(is_again=True)

    def _placed(self, is_again: bool = False) -> None:
        """The window just put where it is shown, before it is: again, if
        put there once more."""


def show_pooled(pool: list, make: Callable, items: Sequence, show: Callable) -> None:
    """Each of items shown by a mark of the pool, show(mark, item), more
    made as they are needed, make(); the rest hidden."""

    while len(pool) < len(items):
        pool.append(make())

    for mark, item in zip(pool, items):
        show(mark, item)

    for mark in pool[len(items) :]:
        if mark.isVisible():
            mark.hide()


class GridLineMark(FloatingMark):
    """The line between two cells that the pointer is on, to be moved, or
    that is being moved: thicker where it has snapped (see GridLines.snaps).
    """

    # the light middle of the line, of one snapped, and either dark edge
    core = 2
    snapped_core = 4
    edge = 1

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_column = True

    def show_line(
        self, is_column: bool, position: int, start: int, end: int, is_snapped: bool
    ) -> None:
        """Show the line: a column's at x = position from y = start to end,
        a row's at y = position from x = start to end, on the screen."""

        core = self.snapped_core if is_snapped else self.core
        thickness = core + 2 * self.edge
        low = position - thickness // 2

        if is_column:
            rect = QRect(low, start, thickness, end - start)
        else:
            rect = QRect(start, low, end - start, thickness)

        if is_column != self._is_column:
            self._is_column = is_column
            self.update()

        self.show_at(rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), EDGE_COLOR)

        if self._is_column:
            core = self.rect().adjusted(self.edge, 0, -self.edge, 0)
        else:
            core = self.rect().adjusted(0, self.edge, 0, -self.edge)

        painter.fillRect(core, LINE_COLOR)


# a guide: its light line, and the dark edge round it and its dots
GUIDE_CORE = 1
GUIDE_EDGE = 1
# a dot where tiles' corners, or their edges' middles, are in line
DOT_RADIUS = 2.5
# a gap's mark: the ticks at its ends, and the badge saying it is as much
# as another, where there is room for it with a little line either side
GAP_TICK = 7
CHIP = QSizeF(16, 11)
CHIP_RADIUS = 3
CHIP_ROOM = 4
# across a gap's mark, the most of it there is: the badge, its dark edge
GAP_THICKNESS = CHIP.height() + 2 * GUIDE_EDGE


def guide_paths(
    is_column: bool,
    position: float,
    start: float,
    end: float,
    points: Sequence[float] = (),
) -> tuple[QPainterPath, QPainterPath]:
    """A guide's shapes, the dark under the light: a column's line at x =
    position from y = start to end, a row's the other way, with a dot at
    each of points along it. In whole pixels, as sharp as can be."""

    middle = round(position) + GUIDE_CORE / 2
    start, end = round(start), round(end)

    dark, light = QPainterPath(), QPainterPath()
    dark.addRect(_bar(is_column, middle, start, end, GUIDE_CORE, GUIDE_EDGE))
    light.addRect(_bar(is_column, middle, start, end, GUIDE_CORE, 0))

    for point in points:
        at = _at(is_column, middle, round(point))
        dark.addEllipse(at, DOT_RADIUS + GUIDE_EDGE, DOT_RADIUS + GUIDE_EDGE)
        light.addEllipse(at, DOT_RADIUS, DOT_RADIUS)

    return _winding(dark), _winding(light)


def gap_paths(
    is_column: bool, start: float, end: float, position: float
) -> tuple[QPainterPath, QPainterPath]:
    """A gap's mark, the dark under the light: across a column's gap from
    x = start to end at y = position, a row's the other way. A line with a
    tick at each end, and a badge with = on it in the middle, where there
    is room."""

    middle = round(position) + GUIDE_CORE / 2
    start, end = round(start), round(end)
    length = max(end - start, 1)

    bars = [
        # a column's gap is crossed by a row's line, and the other way
        _bar(not is_column, middle, start, start + length, GUIDE_CORE, 0),
        # the ticks, on the first pixel of the gap and on its last
        _tick(is_column, middle, start),
        _tick(is_column, middle, start + length - 1),
    ]

    dark, light = QPainterPath(), QPainterPath()
    for bar in bars:
        dark.addRect(bar.adjusted(-GUIDE_EDGE, -GUIDE_EDGE, GUIDE_EDGE, GUIDE_EDGE))
        light.addRect(bar)
    dark, light = _winding(dark), _winding(light)

    if length >= CHIP.width() + 2 * CHIP_ROOM:
        chip = QRectF(QPointF(), CHIP)
        chip.moveCenter(_at(not is_column, middle, start + length / 2))
        chip = QRectF(
            round(chip.left()), round(chip.top()), chip.width(), chip.height()
        )
        dark, light = _with_chip(dark, light, chip)

    return dark, light


def _with_chip(dark, light, chip: QRectF) -> tuple[QPainterPath, QPainterPath]:
    """The paths with the badge on top: dark inside, a light rim, = on it."""

    outer = QPainterPath()
    outer.addRoundedRect(
        chip.adjusted(-GUIDE_EDGE, -GUIDE_EDGE, GUIDE_EDGE, GUIDE_EDGE),
        CHIP_RADIUS + GUIDE_EDGE,
        CHIP_RADIUS + GUIDE_EDGE,
    )
    rim = QPainterPath()
    rim.addRoundedRect(chip, CHIP_RADIUS, CHIP_RADIUS)
    inside = QPainterPath()
    inside.addRoundedRect(chip.adjusted(1, 1, -1, -1), CHIP_RADIUS - 1, CHIP_RADIUS - 1)

    sign = QPainterPath()
    left = chip.center().x() - 3
    top = chip.center().y() - 2
    sign.addRect(QRectF(round(left), round(top), 6, 1))
    sign.addRect(QRectF(round(left), round(top) + 3, 6, 1))

    dark = dark.united(outer)
    light = light.subtracted(outer).united(rim.subtracted(inside)).united(sign)
    return dark, light


def _bar(is_column, middle, start, end, core, edge) -> QRectF:
    """A line along a column's x = middle, or a row's y, core thick, with
    edge round it."""

    low = middle - core / 2 - edge
    if is_column:
        return QRectF(low, start - edge, core + 2 * edge, end - start + 2 * edge)
    return QRectF(start - edge, low, end - start + 2 * edge, core + 2 * edge)


def _tick(is_column, middle, at) -> QRectF:
    """A tick across a gap's line, a column's at x = at."""

    low = middle - GAP_TICK / 2
    if is_column:
        return QRectF(at, round(low), 1, GAP_TICK)
    return QRectF(round(low), at, GAP_TICK, 1)


def _at(is_column, middle, along) -> QPointF:
    return QPointF(middle, along) if is_column else QPointF(along, middle)


def _winding(path: QPainterPath) -> QPainterPath:
    # filled where any of its shapes is, the dots over the line too
    path.setFillRule(Qt.WindingFill)
    return path


class ShapedMark(FloatingMark):
    """A mark of a shape that is not a box: see-through round it where the
    system can show that, smooth to the edge; else the window is cut to
    it, whole pixels in or out, and painted to the cut in its outer colour,
    or what the cut leaves of a pixel at the edge is the window's own."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)

        # the cut, and whether the window has yet to be
        self._cut: QBitmap | None = None
        self._is_cut_new = False

    def cut_to(self, size: QSize, path: QPainterPath) -> None:
        """Only the path shown, in a window of that size, once it is shown
        at that size (see show_at)."""

        if not self._is_translucent:
            self._cut = _mask(size, path)
            self._is_cut_new = True

    def _placed(self, is_again: bool = False) -> None:
        # X11 cuts the window's shape to its size as the shape is set: one
        # set before a window grows leaves the rest of it unseen
        if self._cut is not None and (self._is_cut_new or is_again):
            self.setMask(self._cut)
            self._is_cut_new = False

    def begin_paint(self, outer: QColor) -> QPainter:
        painter = QPainter(self)
        if not self._is_translucent:
            painter.fillRect(self.rect(), outer)
        painter.setRenderHint(QPainter.Antialiasing)
        return painter


class ShapeMark(ShapedMark):
    """A guide or a gap's mark (see guide_paths, gap_paths), light with a
    dark edge to show over any picture. Only the shapes are shown."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._dark = QPainterPath()
        self._light = QPainterPath()

    def show_guide(self, *args) -> None:
        """Show a guide on the screen, as guide_paths(*args) has it."""

        self.show_paths(*guide_paths(*args))

    def show_gap(self, *args) -> None:
        """Show a gap's mark on the screen, as gap_paths(*args) has it."""

        self.show_paths(*gap_paths(*args))

    def show_paths(self, dark: QPainterPath, light: QPainterPath) -> None:
        rect = dark.boundingRect().toAlignedRect()
        offset = QPointF(-rect.x(), -rect.y())
        dark, light = dark.translated(offset), light.translated(offset)

        if dark != self._dark or light != self._light:
            self._dark, self._light = dark, light
            self.cut_to(rect.size(), dark)
            self.update()

        self.show_at(rect)

    def paintEvent(self, event) -> None:
        painter = self.begin_paint(EDGE_COLOR)
        painter.fillPath(self._dark, EDGE_COLOR)
        painter.fillPath(self._light, LINE_COLOR)


def _mask(size: QSize, path: QPainterPath) -> QBitmap:
    """The window cut to the path, whole pixels in or out."""

    bitmap = QBitmap(size)
    bitmap.fill(Qt.color0)
    painter = QPainter(bitmap)
    painter.fillPath(path, QBrush(Qt.color1))
    painter.end()
    return bitmap


def guides_clear_of(guides: list[Guide], gaps: list[Gap]) -> list[Guide]:
    """The guides to draw with the gaps marked: not one along a mark,
    across the gap where it is drawn, which would hide it; it is still said
    (see tile_snap_words)."""

    # half of each, the mark and the line
    reach = (GAP_THICKNESS + GUIDE_CORE + 2 * GUIDE_EDGE) / 2

    def is_under(guide: Guide, gap: Gap) -> bool:
        return (
            guide.is_column != gap.is_column
            and abs(guide.position - gap.position) < reach
            and guide.start < gap.end
            and guide.end > gap.start
        )

    return [g for g in guides if not any(is_under(g, gap) for gap in gaps)]


class GridLineTag(ShapedMark):
    """A word beside a line being moved that has snapped, saying why it
    stopped there: a video fits, or the cells are even."""

    # between the word and the pill's edge, and between the pill and the line
    padding = QSize(9, 3)
    gap = 8

    def __init__(self, parent=None):
        super().__init__(parent)

        self._text = ""
        # the size it was shown at, which the window may not quite be on a
        # screen that scales
        self._size_shown = QSize()
        # FloatingMark.shown_count when it was last put on top
        self._on_top_at = -1

    def show_snap(
        self,
        target: Target | None,
        is_column: bool,
        position: int,
        pointer: QPoint,
        area: QRect,
    ) -> None:
        """Say what a line moved to position in the area, on the screen,
        snapped to (see snap_word), beside it by the pointer; nothing where
        it has not."""

        if target is None:
            if self.isVisible():
                self.hide()
            return

        if is_column:
            at = QPoint(area.x() + position, pointer.y())
        else:
            at = QPoint(pointer.x(), area.y() + position)
        self.show_text(snap_word(target, is_column), is_column, at, area)

    def show_text(self, text: str, is_column: bool, at: QPoint, room: QRect) -> None:
        """Show the word beside a column's line at x = at.x(), or under a
        row's at y = at.y(), by the pointer, kept inside room."""

        metrics = self.fontMetrics()
        size = QSize(
            metrics.horizontalAdvance(text) + 2 * self.padding.width(),
            metrics.height() + 2 * self.padding.height(),
        )

        if is_column:
            x = at.x() + self.gap
            if x + size.width() > room.right():
                x = at.x() - self.gap - size.width()
            y = at.y() - size.height() // 2
        else:
            x = at.x() - size.width() // 2
            y = at.y() + self.gap
            if y + size.height() > room.bottom():
                y = at.y() - self.gap - size.height()

        x = min(max(x, room.left()), room.right() - size.width())
        y = min(max(y, room.top()), room.bottom() - size.height())
        rect = QRect(QPoint(x, y), size)

        if text != self._text or size != self._size_shown:
            self._text = text
            self._size_shown = size
            self.cut_to(size, self._outline())
            self.update()

        # over the lines it speaks of: one shown after it would cover it
        is_shown = self.isVisible()
        self.show_at(rect)
        if is_shown and self._on_top_at != FloatingMark.shown_count:
            self._put_on_top()
        self._on_top_at = FloatingMark.shown_count

    def _put_on_top(self) -> None:
        # raised, X11 leaves it under the windows shown after it (mutter, at
        # least); shown again, it is on top
        if QGuiApplication.platformName() == "xcb":
            self.hide()
            self.show()
        else:
            self.raise_()

    def paintEvent(self, event) -> None:
        painter = self.begin_paint(TAG_BORDER_COLOR)
        painter.fillPath(self._outline(), TAG_BORDER_COLOR)
        painter.fillPath(self._outline(inset=1), TAG_BACK_COLOR)
        painter.setPen(LINE_COLOR)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)

    def _outline(self, inset: float = 0) -> QPainterPath:
        """The pill the word is on, in the window."""

        size = self._size_shown
        rect = QRectF(0, 0, size.width(), size.height()).adjusted(
            inset, inset, -inset, -inset
        )
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path
