from PyQt5.QtCore import QEvent, QSize, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QStyle,
    QWidget,
)

_WHEEL_FIELDS = (QComboBox, QAbstractSpinBox)


def _scrollbar_extent(widget: QWidget) -> int:
    style = widget.style()
    extent = style.pixelMetric(QStyle.PM_ScrollBarExtent, None, widget)
    return max(extent, 16)


class _BoxedScrollBar(QScrollBar):
    """Fusion only strokes the inner edge; draw the other three with the same pen."""

    def paintEvent(self, event):
        super().paintEvent(event)
        # Same as QFusionStylePrivate::outline + scrollbar alpha.
        outline = self.palette().window().color().darker(140)
        outline.setAlpha(180)
        painter = QPainter(self)
        painter.setPen(outline)
        rect = self.rect()
        if self.orientation() == Qt.Horizontal:
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.drawLine(rect.topLeft(), rect.bottomLeft())
            painter.drawLine(rect.topRight(), rect.bottomRight())
        else:
            painter.drawLine(rect.topLeft(), rect.topRight())
            painter.drawLine(rect.topRight(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())


class PageScrollArea(QScrollArea):
    """Scroll area that reserves width for the vertical bar and does not
    force the dialog to the inner page's full height."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBar(_BoxedScrollBar(Qt.Vertical, self))
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setContentsMargins(0, 1, 1, 1)

    def setWidget(self, widget):
        super().setWidget(widget)

        # A field the pointer passes over while the page scrolls would take
        # the wheel and change its value. It only gets it once clicked.
        for field in widget.findChildren(_WHEEL_FIELDS):
            field.setFocusPolicy(Qt.StrongFocus)
            field.installEventFilter(self)

    def eventFilter(self, obj, event):
        # The scroll bars are filtered here too, and handing them their own
        # wheel back would go round forever.
        if (
            event.type() == QEvent.Wheel
            and isinstance(obj, _WHEEL_FIELDS)
            and not obj.hasFocus()
        ):
            self.wheelEvent(event)
            return True

        return super().eventFilter(obj, event)

    def sizeHint(self):
        inner = self.widget()
        extra = _scrollbar_extent(self.verticalScrollBar())
        if inner is None:
            return QSize(extra, 0)
        hint = inner.sizeHint()
        return QSize(hint.width() + extra, hint.height())

    def minimumSizeHint(self):
        inner = self.widget()
        extra = _scrollbar_extent(self.verticalScrollBar())
        min_h = super().minimumSizeHint().height()
        if inner is None:
            return QSize(extra, min_h)
        hint = inner.minimumSizeHint()
        return QSize(hint.width() + extra, min_h)
