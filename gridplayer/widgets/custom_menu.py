from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QIconEngine,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import QMenu, QProxyStyle, QStyle

from gridplayer.params.theme import current_colors

ICON_SIZE = 24

# A checked item says so on its icon rather than across its whole row: a
# disc at the icon's corner, ticked for a setting that is on, holed for the
# one picked out of several. A row with no icon of its own gets the tick or
# a dot alone, where the icon would be. In the icon's pixels, ICON_SIZE across.
MARK_DISC = 11
MARK_GAP = 2
MARK_HOLE = 5
MARK_DOT = 8
MARK_TICK_ON_DISC = 8
MARK_TICK_ALONE = 18

# a tick in a box 16 across, and how thick, in the box's units
_TICK = ((2.5, 8.5), (6.5, 12.5), (13.5, 4))
_TICK_STROKE_ON_DISC = 3
_TICK_STROKE_ALONE = 2

MENU_STYLE = """
QMenu {
    background-color: {background};
    color: {text};
    border: 1px solid {border};
    margin: 0;
    menu-scrollable: 1;
}
QMenu::icon { margin-left: 5px;}
QMenu::item {
    height:{icon_size}px;
    margin: 0;
    padding: 1px 15px 1px 5px;
    background: transparent;
    border: 0 solid transparent;
}
QMenu::separator { height: 1px; margin: 2px 3px; background: {border}; }
QMenu::item:selected { background-color: {background_selected}; }
QMenu::item:disabled { color: {text_disabled}; }
QMenu::item:disabled:selected { background-color: transparent; }
"""


class CustomMenu(QMenu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Do not pass qApp.style() into QProxyStyle — that transfers ownership of the
        # *application* style to the proxy. When the menu is destroyed, Qt deletes the
        # app style and the process later dies with ACCESS_VIOLATION (0xC0000005).
        # Default-constructed QProxyStyle uses the app style without taking ownership.
        style = BigMenuIcons()
        style.setParent(self)
        self.setStyle(style)
        self.setStyleSheet(_get_theme_style())

        self.setWindowFlags(
            self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )

    def setActiveAction(self, act):
        # QMenu stylesheets make SH_Menu_AllowActiveAndDisabled unreliable, so
        # disabled items stay highlightable/clickable unless we block them here.
        if act is not None and not act.isEnabled():
            act = None
        super().setActiveAction(act)

    def mouseReleaseEvent(self, event):
        action = self.actionAt(event.pos())
        if action is not None and not action.isEnabled():
            event.accept()
            return
        super().mouseReleaseEvent(event)


class BigMenuIcons(QProxyStyle):
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_SmallIconSize:
            return ICON_SIZE
        return super().pixelMetric(metric, option, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_Menu_AllowActiveAndDisabled:
            return 0
        return super().styleHint(hint, option, widget, returnData)


def checked_icon(icon: QIcon, is_choice: bool) -> QIcon:
    """This icon for a checkable item, marked while the item is checked.

    A menu asks a checked item's icon for its On state and draws no tick of
    its own beside an icon, so the mark is all there is to tell it by. An
    icon that is nothing, or the theme's "empty" that only keeps the rows
    lined up, gets the mark alone.
    """

    is_blank = icon.isNull() or icon.name() == "empty"

    return QIcon(_CheckedIconEngine(icon, is_choice=is_choice, is_blank=is_blank))


class _CheckedIconEngine(QIconEngine):
    """An icon with the mark of being checked in its corner, in the On state.

    The gap round the disc, the hole in a choice's disc and the tick on a
    setting's are holes in the picture rather than paint: what shows through
    them is the row, as it is, hovered or not.
    """

    def __init__(self, icon: QIcon, is_choice: bool, is_blank: bool):
        super().__init__()

        self._icon = QIcon(icon)
        self._is_choice = is_choice
        self._is_blank = is_blank

    def paint(self, painter, rect, mode, state):
        # drawn apart first, or the holes would go through whatever the
        # painter already holds
        ratio = painter.device().devicePixelRatioF()

        pixmap = self.pixmap(rect.size() * ratio, mode, state)
        pixmap.setDevicePixelRatio(ratio)

        painter.drawPixmap(rect, pixmap)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)

        rect = QRect(QPoint(0, 0), size)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if not self._is_blank:
            self._icon.paint(painter, rect, Qt.AlignCenter, mode, QIcon.Off)

        if state == QIcon.On:
            colors = current_colors()
            color = QColor(
                colors["text_disabled" if mode == QIcon.Disabled else "text"]
            )

            scale = size.height() / ICON_SIZE

            if self._is_blank:
                _draw_mark_alone(painter, rect, scale, color, self._is_choice)
            else:
                _draw_mark_on_icon(painter, rect, scale, color, self._is_choice)

        painter.end()

        return pixmap

    def clone(self):
        return _CheckedIconEngine(self._icon, self._is_choice, self._is_blank)


def _draw_mark_on_icon(painter, rect, scale, color, is_choice):
    radius = MARK_DISC / 2 * scale
    center = QPointF(
        rect.x() + rect.width() - radius, rect.y() + rect.height() - radius
    )

    _cut_circle(painter, center, radius + MARK_GAP * scale)

    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(center, radius, radius)

    if is_choice:
        _cut_circle(painter, center, MARK_HOLE / 2 * scale)
        return

    painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    _draw_tick(
        painter, center, MARK_TICK_ON_DISC * scale, _TICK_STROKE_ON_DISC, Qt.black
    )
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


def _draw_mark_alone(painter, rect, scale, color, is_choice):
    center = QRectF(rect).center()

    if is_choice:
        radius = MARK_DOT / 2 * scale

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(center, radius, radius)
        return

    _draw_tick(painter, center, MARK_TICK_ALONE * scale, _TICK_STROKE_ALONE, color)


def _cut_circle(painter, center, radius):
    painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    painter.setPen(Qt.NoPen)
    painter.setBrush(Qt.black)
    painter.drawEllipse(center, radius, radius)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)


def _draw_tick(painter, center, box, stroke, color):
    unit = box / 16
    left = center.x() - box / 2
    top = center.y() - box / 2

    path = QPainterPath()
    for index, (x, y) in enumerate(_TICK):
        point = QPointF(left + x * unit, top + y * unit)
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)

    pen = QPen(color, stroke * unit, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)


def _get_theme_style():
    colors = current_colors()
    style = MENU_STYLE

    for c_key, c_value in colors.items():
        style = style.replace(f"{{{c_key}}}", c_value)

    return style.replace("{icon_size}", str(ICON_SIZE))
