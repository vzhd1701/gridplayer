"""Tooltips of our own, in place of Qt's, for the whole app.

Qt's tooltip is a single line as long as its text, put where the mouse is
and swapped for the next one the moment the mouse gets there, so going
down a form it hops from row to row, changing size, and blinks out as the
mouse crosses from one part of a row to another.

Ours wraps at TIP_MAX_CHARS characters, takes the theme's colours, sits
under the thing it is about rather than at the mouse, and changes to
another one only once the mouse has come to rest there, fading out and in
again. It reads the same texts Qt's would: a widget's toolTip(), and the
ToolTipRole of a list or tree row. Anything else (a tab, a menu item, a
header) is left to Qt's own, which the theme's stylesheet at least colours
the same way.
"""

import math
from dataclasses import dataclass
from time import monotonic

from PyQt5 import sip
from PyQt5.QtCore import (
    QEvent,
    QMargins,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PyQt5.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QCursor,
    QFontMetrics,
    QFontMetricsF,
    QPainter,
    QPalette,
    QPen,
    QTextDocument,
    QTextOption,
)
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QWidget

from gridplayer.params.theme import current_colors
from gridplayer.utils.compositor_linux import is_compositor_running
from gridplayer.utils.darkmode import is_dark_mode

# how wide a tip gets before it wraps, in characters of its font
TIP_MAX_CHARS = 72

TIP_PADDING_X = 10

# over the text; under it is worked out from the font (see bottom_padding)
TIP_PADDING_Y = 6

# how far the padding under the text may differ from TIP_PADDING_Y
TIP_PADDING_Y_SLACK = 2

TIP_RADIUS = 4

# room around the box for its shadow, which falls a little down
TIP_SHADOW = 8
TIP_SHADOW_DROP = 2
TIP_SHADOW_ALPHA_LIGHT = 0.16
TIP_SHADOW_ALPHA_DARK = 0.45

# between the thing a tip is about and the tip
TIP_GAP = 4

# a tip starts this far left of the mouse
TIP_CURSOR_INDENT = 14

# below the mouse, clear of the pointer
TIP_CURSOR_HEIGHT = 20

# a thing taller than this many lines gets its tip under the mouse instead
TIP_TALL_LINES = 3

FADE_IN_MS = 120
FADE_OUT_MS = 150
SWAP_OUT_MS = 80

# the mouse at rest this long before a tip changes to another one
SETTLE_MS = 150

# the mouse at rest this long before a first tip, as Qt waits for its own
COLD_SETTLE_MS = 700

# off everything with a tip this long before the tip goes
GRACE_MS = 250

# after a tip goes, the next one comes after SETTLE_MS for this long
WARM_MS = 1000

POLL_MS = 30

# how long Qt keeps sending tooltip events at once after one was taken
QT_FALL_ASLEEP_MS = 2000

_DISMISS_EVENTS = frozenset(
    (
        QEvent.MouseButtonPress,
        QEvent.MouseButtonDblClick,
        QEvent.Wheel,
        QEvent.KeyPress,
    )
)


def fit_text_width(doc: QTextDocument, max_width: int) -> int:
    """The width to lay the document out at: its own if no wider than
    max_width, else as narrow as it goes on the lines it takes at
    max_width, so the last line is not a word or two on its own.

    Lines that may not wrap (white-space: pre) keep their whole width."""

    doc.setTextWidth(-1)
    natural = math.ceil(doc.idealWidth())
    if natural <= max_width:
        return max(natural, 1)

    doc.setTextWidth(max_width)
    height = doc.size().height()

    low, high = max_width // 3, max_width
    while high - low > 1:
        mid = (low + high) // 2
        doc.setTextWidth(mid)
        if doc.size().height() > height:
            low = mid
        else:
            high = mid

    doc.setTextWidth(high)

    return max(high, math.ceil(doc.idealWidth()))


def bottom_padding(metrics: QFontMetrics) -> int:
    """The padding under the text that leaves as much room from the last
    baseline down as there is from the top down to the first capitals.

    Some fonts have more room over their capitals (for accents) than under
    their baseline, some less: Hack has 2 px over and 3 under on Windows.
    The same padding over and under looks low in one and high in another."""

    over_capitals = metrics.ascent() - metrics.capHeight()
    padding = TIP_PADDING_Y + over_capitals - metrics.descent()

    return max(
        TIP_PADDING_Y - TIP_PADDING_Y_SLACK,
        min(padding, TIP_PADDING_Y + TIP_PADDING_Y_SLACK),
    )


def tip_position(
    anchor: QRect | None,
    cursor: QPoint,
    box: QSize,
    area: QRect,
    line_height: int,
) -> QPoint:
    """Where the tip's box goes, on the screen's own coordinates.

    Under the anchor (the row, button or list item the tip is about),
    starting a little left of the mouse; over it where the screen ends
    below. An anchor taller than a few lines would put the tip far from
    the mouse, so there it goes under the mouse instead."""

    if anchor is None or anchor.height() > TIP_TALL_LINES * line_height:
        below = cursor.y() + TIP_CURSOR_HEIGHT
        above = cursor.y() - TIP_GAP - box.height()
    else:
        below = anchor.bottom() + 1 + TIP_GAP
        above = anchor.top() - TIP_GAP - box.height()

    y = below if below + box.height() <= area.bottom() + 1 else above
    y = max(area.top(), y)

    x = cursor.x() - TIP_CURSOR_INDENT
    x = max(area.left(), min(x, area.right() + 1 - box.width()))

    return QPoint(x, y)


class TipWindow(QWidget):
    """The tip itself: a rounded box in the theme's colours with a soft
    shadow, the text wrapped in it, fading in and out.

    Where windows cannot be see-through (X11 with no compositor) it is a
    plain square box that shows and goes at once.
    """

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

        self._is_translucent = is_compositor_running()
        if self._is_translucent:
            self.setAttribute(Qt.WA_TranslucentBackground)

        self._text = ""
        self._box = QSize(0, 0)

        self._doc = QTextDocument(self)
        self._doc.setDocumentMargin(0)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self._doc.setDefaultTextOption(option)

        self._opacity = 1.0
        self._then = None
        self._fade = QVariantAnimation(self)
        self._fade.valueChanged.connect(self._set_opacity)
        self._fade.finished.connect(self._on_fade_finished)

    def text(self) -> str:
        return self._text

    def set_text(self, text: str, max_width: int | None = None) -> QSize:
        """Lay the text out and size the window to it; the box's size.

        max_width, the screen's, keeps lines that may not wrap on it."""

        self._text = text

        doc = self._doc
        doc.setDefaultFont(self.font())
        if Qt.mightBeRichText(text):
            doc.setHtml(text)
        else:
            doc.setPlainText(text)

        frame = 2 * TIP_PADDING_X + 2
        cap = round(QFontMetricsF(self.font()).averageCharWidth() * TIP_MAX_CHARS)
        if max_width is not None:
            cap = min(cap, max_width - frame)

        text_width = fit_text_width(doc, cap)
        if max_width is not None:
            text_width = min(text_width, max_width - frame)
        doc.setTextWidth(text_width)

        padding_y = TIP_PADDING_Y + bottom_padding(QFontMetrics(self.font()))
        self._box = QSize(
            text_width + frame,
            math.ceil(doc.size().height()) + padding_y + 2,
        )

        margins = self._margins()
        self.resize(
            self._box.width() + margins.left() + margins.right(),
            self._box.height() + margins.top() + margins.bottom(),
        )
        self.update()

        return QSize(self._box)

    def box_size(self) -> QSize:
        return QSize(self._box)

    def box_geometry(self) -> QRect:
        """The box, without its shadow, on the screen's coordinates."""

        margins = self._margins()
        return QRect(self.pos() + QPoint(margins.left(), margins.top()), self._box)

    def move_box(self, pos: QPoint) -> None:
        margins = self._margins()
        self.move(pos - QPoint(margins.left(), margins.top()))

    def show_now(self) -> None:
        self._stop_fade()
        self._set_opacity(1.0)
        self.show()

    def hide_now(self) -> None:
        self._stop_fade()
        self.hide()
        self._set_opacity(1.0)

    def fade_in(self, duration_ms: int = FADE_IN_MS) -> None:
        if not self.isVisible():
            self._stop_fade()
            self._set_opacity(0.0)
            self.show()

        self._fade_to(1.0, duration_ms)

    def fade_out(self, duration_ms: int = FADE_OUT_MS, then=None) -> None:
        """Fade out and hide, then call then, if given."""

        if not self.isVisible():
            self._stop_fade()
            if then is not None:
                then()
            return

        self._fade_to(0.0, duration_ms, then)

    def paintEvent(self, event):
        colors = current_colors()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self._opacity)

        margins = self._margins()
        box = QRectF(
            margins.left(), margins.top(), self._box.width(), self._box.height()
        )

        if self._is_translucent:
            self._paint_shadow(painter, box)

            painter.setPen(QPen(QColor(colors["border"]), 1))
            painter.setBrush(QColor(colors["tooltip_base"]))
            painter.drawRoundedRect(
                box.adjusted(0.5, 0.5, -0.5, -0.5), TIP_RADIUS, TIP_RADIUS
            )
        else:
            painter.fillRect(self.rect(), QColor(colors["tooltip_base"]))
            painter.setPen(QPen(QColor(colors["border"]), 1))
            painter.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))

        painter.translate(box.left() + 1 + TIP_PADDING_X, box.top() + 1 + TIP_PADDING_Y)

        context = QAbstractTextDocumentLayout.PaintContext()
        palette = QPalette(self.palette())
        palette.setColor(QPalette.Text, QColor(colors["tooltip_text"]))
        context.palette = palette
        self._doc.documentLayout().draw(painter, context)

        painter.end()

    def _paint_shadow(self, painter, box: QRectF) -> None:
        """Rings around the box, fainter outwards, adding up to a soft
        shadow that is darkest at its edge."""

        peak = TIP_SHADOW_ALPHA_DARK if is_dark_mode() else TIP_SHADOW_ALPHA_LIGHT
        steps = TIP_SHADOW
        step_alpha = peak / (steps / 2)

        painter.save()
        painter.setPen(Qt.NoPen)
        shadow = box.translated(0, TIP_SHADOW_DROP)
        for ring in range(steps, 0, -1):
            color = QColor(0, 0, 0)
            color.setAlphaF(step_alpha * (1 - ring / (steps + 1)))
            painter.setBrush(color)
            radius = TIP_RADIUS + ring
            painter.drawRoundedRect(
                shadow.adjusted(-ring, -ring, ring, ring), radius, radius
            )
        painter.restore()

    def _margins(self) -> QMargins:
        if not self._is_translucent:
            return QMargins(0, 0, 0, 0)

        return QMargins(
            TIP_SHADOW,
            TIP_SHADOW - TIP_SHADOW_DROP,
            TIP_SHADOW,
            TIP_SHADOW + TIP_SHADOW_DROP,
        )

    def _fade_to(self, opacity: float, duration_ms: int, then=None) -> None:
        self._stop_fade()
        self._then = then

        distance = abs(opacity - self._opacity)
        if not self._is_translucent or duration_ms <= 0 or distance == 0:
            self._set_opacity(opacity)
            self._on_fade_finished()
            return

        self._fade.setStartValue(self._opacity)
        self._fade.setEndValue(opacity)
        self._fade.setDuration(max(1, round(duration_ms * distance)))
        self._fade.start()

    def _stop_fade(self) -> None:
        self._fade.stop()
        self._then = None

    def _set_opacity(self, opacity) -> None:
        self._opacity = float(opacity)
        self.update()

    def _on_fade_finished(self) -> None:
        then, self._then = self._then, None

        if self._opacity == 0:
            self.hide()

        if then is not None:
            then()


@dataclass(frozen=True, eq=False)
class _Target:
    """Something with a tip: the tip's text, the rect it goes under, on
    the screen's coordinates, and the window it is in. The key tells one
    from another; the same widget with another text is another."""

    key: tuple
    text: str
    anchor: QRect
    window: QWidget


def _view_of_viewport(widget):
    parent = widget.parentWidget()

    if isinstance(parent, QAbstractItemView) and parent.viewport() is widget:
        return parent

    return None


def _target_of(widget, pos: QPoint) -> _Target | None:
    """The tip of this widget itself at pos, on the screen's coordinates,
    none of its parents'; for a list or tree, of its item there."""

    view = _view_of_viewport(widget)
    if view is not None:
        index = view.indexAt(widget.mapFromGlobal(pos))
        if not index.isValid():
            return None

        text = index.data(Qt.ToolTipRole)
        if not isinstance(text, str) or not text:
            return None

        rect = view.visualRect(index)
        key = (view, index.row(), index.column(), index.internalId(), text)
        anchor = QRect(widget.mapToGlobal(rect.topLeft()), rect.size())

        return _Target(key, text, anchor, widget.window())

    text = widget.toolTip()
    if not text:
        return None

    anchor = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())

    return _Target((widget, text), text, anchor, widget.window())


class TooltipManager(QObject):
    """Takes Qt's tooltip events for the whole app and shows TipWindow in
    place of Qt's tip.

    Qt sends a widget a tooltip event once the mouse has rested on it, at
    first after COLD_SETTLE_MS, and for a while after one was shown as soon
    as the mouse stops. The first starts a tip; from then on the mouse is
    watched every POLL_MS, while a tip is up and for a while after, and
    the tip changes rows only once the mouse is at rest for SETTLE_MS.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tip = None

        self._shown = None
        self._suppressed = None

        self._grace_since = None
        self._warm_until = 0.0
        self._pending_until = 0.0
        self._last_taken = -math.inf

        self._last_pos = QPoint()
        self._last_move = 0.0

        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._on_poll)

    @property
    def is_shown(self) -> bool:
        return self._shown is not None

    def eventFilter(self, event_object, event):
        event_type = event.type()

        if event_type == QEvent.ToolTip:
            if isinstance(event_object, QWidget):
                return self._on_tooltip_event(event_object, event)
            return False

        if event_type in _DISMISS_EVENTS and (
            self._shown is not None or self._poll.isActive()
        ):
            self._dismiss()

        return False

    def _on_tooltip_event(self, widget, event) -> bool:
        target = _target_of(widget, event.globalPos())
        if target is None:
            return False

        now = monotonic()
        is_qt_awake = (now - self._last_taken) * 1000 < QT_FALL_ASLEEP_MS
        self._last_taken = now

        if self._shown is None and not is_qt_awake and now >= self._warm_until:
            self._show(target)
        else:
            # Qt sends these as soon as the mouse stops, so whether it has
            # rested long enough is up to the watch
            self._pending_until = now + QT_FALL_ASLEEP_MS / 1000
            self._start_watch()

        return True

    def _start_watch(self) -> None:
        if self._poll.isActive():
            return

        self._last_pos = QCursor.pos()
        self._last_move = monotonic()
        self._poll.start()

    def _on_poll(self) -> None:
        now = monotonic()

        pos = QCursor.pos()
        if pos != self._last_pos:
            self._last_pos = pos
            self._last_move = now
        rested_ms = (now - self._last_move) * 1000

        target = self._target_at(pos)

        if target is None or (
            self._suppressed is not None and target.key != self._suppressed
        ):
            self._suppressed = None

        if self._shown is not None:
            if not self._is_window_active(self._shown.window):
                self._hide_now()
            elif target is not None and target.key == self._shown.key:
                self._grace_since = None
            elif target is not None:
                self._grace_since = None
                if rested_ms >= SETTLE_MS:
                    self._swap(target)
            elif self._grace_since is None:
                self._grace_since = now
            elif (now - self._grace_since) * 1000 >= GRACE_MS:
                self._hide()
            return

        if target is not None and target.key != self._suppressed:
            is_warm = now < self._warm_until
            if rested_ms >= (SETTLE_MS if is_warm else COLD_SETTLE_MS):
                self._show(target)
                return

        if now >= self._warm_until and now >= self._pending_until:
            self._poll.stop()

    def _target_at(self, pos: QPoint) -> _Target | None:
        """The tip at pos, on the screen's coordinates, as Qt would find it:
        of the widget under the mouse, or else of the nearest parent that
        has one."""

        widget = self._widget_at(pos)

        while widget is not None:
            target = _target_of(widget, pos)
            if target is not None:
                return target

            if widget.isWindow():
                return None

            widget = widget.parentWidget()

        return None

    def _widget_at(self, pos: QPoint):
        """The widget under the mouse, in the active window only, as Qt
        shows tips there only.

        The tip is no answer: where windows say nothing of where they are
        (Wayland) or the tip is in the way (X11), the active window is
        asked instead."""

        widget = QApplication.widgetAt(pos)
        if (
            widget is not None
            and not self._is_tip(widget)
            and self._is_window_active(widget.window())
        ):
            return widget

        window = QApplication.activePopupWidget() or QApplication.activeWindow()
        if window is None:
            return None

        local = window.mapFromGlobal(pos)
        if not window.rect().contains(local):
            return None

        return window.childAt(local) or window

    def _is_tip(self, widget) -> bool:
        tip = self._tip
        return tip is not None and not sip.isdeleted(tip) and widget.window() is tip

    @staticmethod
    def _is_window_active(window) -> bool:
        if sip.isdeleted(window):
            return False

        return window.isVisible() and window.isActiveWindow()

    def _tip_for(self, window) -> TipWindow:
        """The tip, in the window it is to show over, so that it stays over
        that window, and on Wayland can show at all."""

        tip = self._tip
        if tip is not None and not sip.isdeleted(tip):
            if tip.parentWidget() is window:
                return tip

            tip.hide_now()
            tip.deleteLater()

        self._tip = TipWindow(window)

        return self._tip

    def _lay_out(self, tip: TipWindow, target: _Target) -> None:
        cursor = QCursor.pos()

        screen = QApplication.screenAt(cursor) or target.window.screen()
        area = screen.availableGeometry()

        tip.set_text(target.text, area.width())

        line_height = QFontMetrics(tip.font()).lineSpacing()
        tip.move_box(
            tip_position(target.anchor, cursor, tip.box_size(), area, line_height)
        )

    def _show(self, target: _Target) -> None:
        tip = self._tip_for(target.window)

        self._lay_out(tip, target)
        tip.fade_in()

        self._shown = target
        self._grace_since = None
        self._start_watch()

    def _swap(self, target: _Target) -> None:
        tip = self._tip

        if tip is None or sip.isdeleted(tip) or tip.parentWidget() is not target.window:
            self._hide_now()
            self._show(target)
            return

        self._shown = target
        self._grace_since = None

        def _show_next():
            self._lay_out(tip, target)
            tip.fade_in()

        tip.fade_out(SWAP_OUT_MS, then=_show_next)

    def _hide(self) -> None:
        self._shown = None
        self._grace_since = None
        self._warm_until = monotonic() + WARM_MS / 1000

        tip = self._tip
        if tip is not None and not sip.isdeleted(tip):
            tip.fade_out()

    def _hide_now(self) -> None:
        self._shown = None
        self._grace_since = None

        tip = self._tip
        if tip is not None and not sip.isdeleted(tip):
            tip.hide_now()

    def _dismiss(self) -> None:
        """A click, the wheel or a key: the tip goes at once, and comes
        back only once the mouse has been elsewhere."""

        if self._shown is not None:
            self._suppressed = self._shown.key
        else:
            target = self._target_at(QCursor.pos())
            self._suppressed = target.key if target is not None else None

        self._hide_now()
        self._warm_until = 0.0
        self._pending_until = 0.0


def install_tooltips(app) -> TooltipManager:
    """Put our tooltips in place of Qt's for the whole app."""

    manager = TooltipManager(app)
    app.installEventFilter(manager)

    return manager
