"""The colours a bookmark can be given, and where they are picked.

A bookmark has no colour until it is given one, and is drawn in the
bookmarks' own amber till then. Those offered are bright, which keeps them
told apart through the overlay's half opacity over most of what a video
shows; any other can be picked by hand.

Wherever a colour is picked from a menu or shown in a list, it is shown on a
bookmark's marker, the shape the bar marks bookmarks with. Only the Rename
box picks from circles, as the video's own Rename box does.
"""

import base64
import functools
import math

from PyQt5.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QIconEngine,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPixmap,
)
from PyQt5.QtWidgets import QColorDialog, QHBoxLayout, QWidget

from gridplayer.params.theme import current_colors
from gridplayer.utils.qt import translate
from gridplayer.widgets.color_palette import QColorCircle
from gridplayer.widgets.custom_menu import CustomMenu
from gridplayer.widgets.video_overlay_elements import (
    BOOKMARK_COLOR,
    BOOKMARK_MARKER,
    MarkerSize,
    draw_bookmark_marker,
    fill_bookmark_marker,
    marker_colors,
    marker_shape,
)

# How much of an icon's height its marker takes: in a menu, as much as the
# outline of the bookmark icons beside it takes of theirs (512 of 532); in a
# list, nearly all of its small box.
MENU_ICON_SHARE = 512 / 532
LIST_ICON_SHARE = 0.8

# The bookmark icons' outline (resources/icons/custom/bookmark*.svg), as a
# share of its height: its top corners rounded 48 of 512, and drawn 26 of 512
# thick, all of it inside.
ICON_CORNER_SHARE = 48 / 512
ICON_RIM_SHARE = 26 / 512

# Default stands a little apart from the colours in the Rename box: it is no
# colour, but the bookmarks' own.
DEFAULT_CIRCLE_GAP_PX = 8

# what the bookmarks of a menu have where they differ
_MIXED = object()

# the room after a marker drawn in a line of text, before the name it is of
TEXT_MARKER_GAP_PX = 3


def bookmark_color_presets() -> list[tuple[str, str]]:
    """The colours offered, with their names."""

    return [
        ("#ff3d3d", translate("Actions", "Red")),
        ("#ff4fb8", translate("Actions", "Pink")),
        ("#b36bff", translate("Actions", "Purple")),
        ("#3d8bff", translate("Actions", "Blue")),
        ("#1fd6e8", translate("Actions", "Cyan")),
        ("#3ddc5a", translate("Actions", "Green")),
        ("#ffffff", translate("Actions", "White")),
    ]


def _icon_outline(middle_x: float, top: float, size: MarkerSize) -> QPainterPath:
    """A marker as the bookmark icons outline it: the bar's, its top
    corners rounded."""

    radius = size.height * ICON_CORNER_SHARE

    left = middle_x - size.half_width
    right = middle_x + size.half_width
    sides = top + size.height - size.point

    path = QPainterPath()
    path.moveTo(left, top + radius)
    path.arcTo(QRectF(left, top, radius * 2, radius * 2), 180, -90)
    path.lineTo(right - radius, top)
    path.arcTo(QRectF(right - radius * 2, top, radius * 2, radius * 2), 90, -90)
    path.lineTo(right, sides)
    path.lineTo(middle_x, top + size.height)
    path.lineTo(left, sides)
    path.closeSubpath()

    return path


def _rim_inside(shape: QPainterPath, width: float) -> QPainterPath:
    """A rim this wide round the inside of a shape, as the icons' outlines
    are drawn: inside it, none of it past its edge."""

    stroker = QPainterPathStroker()
    stroker.setWidth(width * 2)
    stroker.setJoinStyle(Qt.MiterJoin)

    return shape.intersected(stroker.createStroke(shape))


class _MarkerIconEngine(QIconEngine):
    """A bookmark's marker in its colours, standing in the middle of the
    icon, as big a share of its height as it is told, at whatever size and
    scale the icon is drawn. Without colours, in all of them: any colour."""

    def __init__(self, colors, rim: QColor, share: float):
        super().__init__()

        self._colors = colors
        self._rim = QColor(rim)
        self._share = share

    def paint(self, painter, rect, mode, state):
        scale = rect.height() * self._share / BOOKMARK_MARKER.height
        size = MarkerSize(*(dimension * scale for dimension in BOOKMARK_MARKER))

        middle_x = rect.x() + rect.width() / 2
        top = rect.y() + (rect.height() - size.height) / 2
        shape = _icon_outline(middle_x, top, size)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        if mode == QIcon.Disabled:
            painter.setOpacity(0.4)

        fill_bookmark_marker(painter, shape, self._fills(shape))
        painter.fillPath(_rim_inside(shape, size.height * ICON_RIM_SHARE), self._rim)

        painter.restore()

    def _fills(self, shape):
        if self._colors:
            return self._colors

        bounds = shape.boundingRect()
        hues = QLinearGradient(QPointF(bounds.left(), 0), QPointF(bounds.right(), 0))

        for step in range(7):
            hues.setColorAt(step / 6, QColor.fromHsvF(step / 6 % 1, 0.75, 1))

        return [QBrush(hues)]

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        self.paint(painter, QRect(QPoint(0, 0), size), mode, state)
        painter.end()

        return pixmap

    def clone(self):
        return _MarkerIconEngine(self._colors, self._rim, self._share)


def _menu_rim() -> QColor:
    return QColor(current_colors()["text"])


def bookmark_icon(colors, rim: QColor | None = None, share=MENU_ICON_SHARE) -> QIcon:
    """A marker in the colours of these bookmarks, as the bar would draw
    theirs: None for one in the bookmarks' own. Rimmed in the menus' text
    colour unless told otherwise."""

    rim = _menu_rim() if rim is None else rim

    return QIcon(_MarkerIconEngine(marker_colors(colors), rim, share))


def _text_marker_size() -> tuple[int, int]:
    """How big a marker drawn in a line of text is, its rim and the room
    after it all in."""

    size = BOOKMARK_MARKER

    width = math.ceil(size.half_width * 2) + 1 + TEXT_MARKER_GAP_PX
    height = math.ceil(size.height) + 1

    return width, height


@functools.lru_cache(maxsize=64)
def _text_marker_png(color: str | None, rim_rgba: int, scale: int) -> bytes:
    size = BOOKMARK_MARKER
    width, height = _text_marker_size()

    image = QImage(width * scale, height * scale, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(scale, scale)

    draw_bookmark_marker(
        painter,
        marker_shape(size.half_width + 0.5, 0.5, size),
        marker_colors([color]),
        QColor.fromRgba(rim_rgba),
    )

    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")

    return bytes(data)


def text_marker_html(color: str | None, rim: QColor, scale: int) -> str:
    """A bookmark's marker in its colour, as the bar draws it, to stand in
    a line of rich text, with room after it for the name; drawn at the
    screen's scale."""

    width, height = _text_marker_size()

    png = _text_marker_png(color, rim.rgba(), scale)
    src = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    return (
        f'<img src="{src}" width="{width}" height="{height}"'
        ' style="vertical-align: middle">'
    )


def _any_color_icon(rim: QColor) -> QIcon:
    return QIcon(_MarkerIconEngine([], rim, MENU_ICON_SHARE))


def bookmark_color_menu(parent, colors, slot_for, custom_slot) -> CustomMenu:
    """The Color menu of bookmarks with these colours: Default, the
    bookmarks' own, which is no colour; the bright ones; then any other,
    picked by hand.

    The one they all have is ticked, none where they differ. slot_for gives
    the slot a colour's item is to call, custom_slot is called for one to be
    picked by hand.
    """

    colors = list(colors)
    shared = colors[0] if colors and colors.count(colors[0]) == len(colors) else _MIXED
    presets = bookmark_color_presets()
    rim = _menu_rim()

    menu = CustomMenu(parent=parent)
    menu.setTitle(translate("Actions", "Color"))
    menu.setIcon(bookmark_icon(colors, rim))

    def add(color, title):
        action = menu.addAction(bookmark_icon([color], rim), title)
        action.setCheckable(True)
        action.setChecked(shared == color)
        action.triggered.connect(slot_for(color))

    add(None, translate("Actions", "Default"))

    menu.addSeparator()

    for color, title in presets:
        add(color, title)

    menu.addSeparator()

    # one picked by hand shows itself here, and is ticked
    is_custom = isinstance(shared, str) and shared not in dict(presets)

    custom = menu.addAction(
        bookmark_icon([shared], rim) if is_custom else _any_color_icon(rim),
        translate("Actions", "Custom…"),
    )
    custom.setCheckable(True)
    custom.setChecked(is_custom)
    custom.triggered.connect(custom_slot)

    return menu


def color_picked_by_hand(parent, color: str | None) -> str | None:
    """A colour picked by hand, starting from the one there is; None where
    the picking was given up."""

    picked = QColorDialog.getColor(
        QColor(color or BOOKMARK_COLOR),
        parent,
        translate("Dialog - Rename video - Select color", "Select color", "Header"),
    )

    if not picked.isValid():
        return None

    return picked.name()


class BookmarkColorPalette(QWidget):
    """The colours a bookmark can be given, as circles in a row, the way the
    video's own colour is picked: Default first, the bright ones, and one to
    pick by hand."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._default = QColorCircle(QColor(BOOKMARK_COLOR), parent=self)
        self._default.setToolTip(translate("Actions", "Default"))

        self._presets = {}

        for color, title in bookmark_color_presets():
            circle = QColorCircle(QColor(color), parent=self)
            circle.setToolTip(title)
            self._presets[color] = circle

        self._custom = QColorCircle(None, is_custom=True, parent=self)
        self._custom.setToolTip(translate("Actions", "Custom…"))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._default)
        layout.addSpacing(DEFAULT_CIRCLE_GAP_PX)

        for circle in self._presets.values():
            layout.addWidget(circle)

        layout.addWidget(self._custom)

        self._default.setChecked(True)

    @property
    def color(self) -> str | None:
        """The one picked, None for Default."""

        for color, circle in self._presets.items():
            if circle.isChecked():
                return color

        if self._custom.isChecked() and self._custom.color is not None:
            return self._custom.color.name()

        return None

    @color.setter
    def color(self, color: str | None):
        if color is None:
            self._default.setChecked(True)
        elif color in self._presets:
            self._presets[color].setChecked(True)
        else:
            self._custom.color = QColor(color)
            self._custom.setChecked(True)
