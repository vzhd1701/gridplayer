from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QLabel, QSizePolicy, QStyleOption


class ElidedLabel(QLabel):
    """One line of text cut short in the middle where it does not fit: a
    path keeps both its drive and its file in sight. The whole of it is in
    the tooltip."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        # (QLabel's own would leave the tooltip out)
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)

        option = QStyleOption()
        option.initFrom(self)

        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideMiddle, rect.width())

        self.style().drawItemText(
            painter,
            rect,
            int(self.alignment() | Qt.AlignVCenter),
            option.palette,
            self.isEnabled(),
            text,
            self.foregroundRole(),
        )

        painter.end()
