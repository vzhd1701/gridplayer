from PyQt5.QtCore import QEvent, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params.static import VideoAnchor, VideoShift
from gridplayer.utils.qt import translate

# where each alignment's button is, row and column, as it is in the pane
_ANCHOR_CELLS = {
    VideoAnchor.TOP_LEFT: (0, 0),
    VideoAnchor.TOP: (0, 1),
    VideoAnchor.TOP_RIGHT: (0, 2),
    VideoAnchor.LEFT: (1, 0),
    VideoAnchor.CENTER: (1, 1),
    VideoAnchor.RIGHT: (1, 2),
    VideoAnchor.BOTTOM_LEFT: (2, 0),
    VideoAnchor.BOTTOM: (2, 1),
    VideoAnchor.BOTTOM_RIGHT: (2, 2),
}

_ANCHOR_ICON_SIZE = 20


def _anchor_names() -> dict:
    """What the menu and the settings call each alignment."""

    return {
        VideoAnchor.CENTER: translate("Alignment", "Center"),
        VideoAnchor.TOP: translate("Alignment", "Top"),
        VideoAnchor.BOTTOM: translate("Alignment", "Bottom"),
        VideoAnchor.LEFT: translate("Alignment", "Left"),
        VideoAnchor.RIGHT: translate("Alignment", "Right"),
        VideoAnchor.TOP_LEFT: translate("Alignment", "Top Left"),
        VideoAnchor.TOP_RIGHT: translate("Alignment", "Top Right"),
        VideoAnchor.BOTTOM_LEFT: translate("Alignment", "Bottom Left"),
        VideoAnchor.BOTTOM_RIGHT: translate("Alignment", "Bottom Right"),
    }


class _PositionPreview(QWidget):
    """Small live canvas: the pane, and all of the picture where it is."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._pane_w = 0
        self._pane_h = 0
        self._picture: QRectF | None = None

    def set_layout(self, pane_size, picture):
        """The pane's size, and the picture's rect in it, None if none."""

        self._pane_w, self._pane_h = pane_size
        self._picture = QRectF(*picture) if picture is not None else None
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._pane_w > 0 and self._pane_h > 0:
            self._paint_pane(painter)

        painter.end()

    def _paint_pane(self, painter):
        margin = 10
        avail_w = self.width() - margin * 2
        avail_h = self.height() - margin * 2
        if avail_w <= 0 or avail_h <= 0:
            return

        pane = QRectF(0, 0, self._pane_w, self._pane_h)
        picture = self._picture

        # all of both, the picture being bigger than the pane or out of it
        drawn = pane.united(picture) if picture is not None else pane

        scale = min(avail_w / drawn.width(), avail_h / drawn.height())
        x0 = (self.width() - drawn.width() * scale) / 2 - drawn.x() * scale
        y0 = (self.height() - drawn.height() * scale) / 2 - drawn.y() * scale

        def on_canvas(rect: QRectF) -> QRectF:
            return QRectF(
                x0 + rect.x() * scale,
                y0 + rect.y() * scale,
                rect.width() * scale,
                rect.height() * scale,
            )

        pane_rect = on_canvas(pane)

        # black where the picture leaves the pane, as it is on screen
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(Qt.black))
        painter.drawRect(pane_rect)

        if picture is not None:
            picture_rect = on_canvas(picture)

            # the picture, drawn like a regular sunken widget well
            painter.setPen(QPen(self.palette().mid(), 1))
            painter.setBrush(self.palette().base())
            painter.drawRect(picture_rect)

            # shaded where it is past the pane, not on show
            past_pane = QPainterPath()
            past_pane.addRect(picture_rect)
            in_pane = QPainterPath()
            in_pane.addRect(pane_rect)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 130))
            painter.drawPath(past_pane.subtracted(in_pane))

        # the pane's edges, what is on show being inside them
        painter.setPen(QPen(self.palette().highlight(), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(pane_rect)


class SetPositionDialog(QDialog):
    """Edits where a video block's picture is in its pane.

    The alignment, the offset from it and whether the picture may go past
    the pane's edges. Every change is applied to the playing video as it is
    made, so the video is the preview; cancel puts back what there was.

    The offset is in frame pixels, right and down, and its boxes range as
    far as the alignment and the edges let the picture go, so what they
    say is where the picture is.
    """

    def __init__(self, video_block, parent=None):
        super().__init__(parent)

        self._block = video_block

        params = video_block.video_params
        self._original = (params.anchor, params.shift, params.is_shift_past_edges)

        self.setWindowTitle(translate("Dialog - Set Position", "Set Position"))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._preview = _PositionPreview()

        alignment_box = QGroupBox(translate("Dialog - Set Position", "Alignment"))
        alignment_grid = QGridLayout(alignment_box)

        self._anchor_group = QButtonGroup(self)
        self._anchor_buttons = {}

        names = _anchor_names()
        for anchor, (row, col) in _ANCHOR_CELLS.items():
            button = QToolButton()
            button.setCheckable(True)
            button.setToolTip(names[anchor])
            button.setIconSize(QSize(_ANCHOR_ICON_SIZE, _ANCHOR_ICON_SIZE))
            button.clicked.connect(lambda _, anchor=anchor: self._on_anchor(anchor))

            self._anchor_group.addButton(button)
            alignment_grid.addWidget(button, row, col)

            self._anchor_buttons[anchor] = button

        offset_box = QGroupBox(translate("Dialog - Set Position", "Offset (px)"))
        offset_grid = QGridLayout(offset_box)

        self._spins = {}
        for row, name, name_title in (
            (0, "x", translate("Dialog - Set Position", "Horizontal")),
            (1, "y", translate("Dialog - Set Position", "Vertical")),
        ):
            spin = QSpinBox()
            spin.setAlignment(Qt.AlignRight)
            spin.valueChanged.connect(self._on_offset_changed)

            offset_grid.addWidget(QLabel(name_title), row, 0)
            offset_grid.addWidget(spin, row, 1)

            self._spins[name] = spin

        offset_grid.setColumnStretch(1, 1)

        self._past_edges = QCheckBox(
            translate("Dialog - Set Position", "Allow moving past the edges")
        )
        self._past_edges.toggled.connect(self._on_past_edges_toggled)
        offset_grid.addWidget(self._past_edges, 2, 0, 1, 2)

        reset = QPushButton(translate("Dialog - Set Position", "Reset"))
        reset.clicked.connect(self._on_reset)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        controls = QHBoxLayout()
        controls.addWidget(alignment_box)
        controls.addWidget(offset_box, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.addWidget(self._preview)
        root.addLayout(controls)
        root.addLayout(bottom)

        self._update_anchor_icons()
        self._show_position()

        self.setFixedSize(self.sizeHint())

    def accept(self):
        # says where the picture ended up, as a move from the menu does
        self._block.set_shift(self._block.video_params.shift, is_silent=False)

        super().accept()

    def reject(self):
        anchor, shift, is_shift_past_edges = self._original
        params = self._block.video_params

        if (params.anchor, params.shift, params.is_shift_past_edges) != (
            self._original
        ):
            # an alignment lets go of the offset, so it goes back first
            self._block.set_anchor(anchor)
            self._block.set_shift_past_edges(is_shift_past_edges)
            self._block.set_shift(shift, is_silent=True)

        super().reject()

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() == QEvent.PaletteChange:
            self._update_anchor_icons()

    def _on_anchor(self, anchor: VideoAnchor):
        self._block.set_anchor(anchor)
        self._show_position()

    def _on_offset_changed(self):
        shift = VideoShift(self._spins["x"].value(), self._spins["y"].value())

        self._block.set_shift(shift, is_silent=True)
        self._show_position()

    def _on_past_edges_toggled(self, is_checked: bool):
        self._block.set_shift_past_edges(is_checked)
        self._show_position()

    def _on_reset(self):
        self._block.set_shift(VideoShift(0, 0), is_silent=True)
        self._show_position()

    def _show_position(self):
        """Show where the picture is now, in every control."""

        params = self._block.video_params
        frame = self._block.video_driver

        self._anchor_buttons[params.anchor].setChecked(True)

        self._past_edges.blockSignals(True)
        self._past_edges.setChecked(params.is_shift_past_edges)
        self._past_edges.blockSignals(False)

        lowest, highest = frame.shift_range()

        for name, low, high, value in (
            ("x", lowest.X, highest.X, params.shift.X),
            ("y", lowest.Y, highest.Y, params.shift.Y),
        ):
            spin = self._spins[name]

            spin.blockSignals(True)
            spin.setRange(low, high)
            spin.setValue(value)
            spin.blockSignals(False)

            # nowhere for the picture to go that way
            spin.setEnabled(low != high)

        self._preview.set_layout((frame.width(), frame.height()), frame.picture_rect())

    def _update_anchor_icons(self):
        color = QColor(self.palette().color(self.foregroundRole()))

        for anchor, button in self._anchor_buttons.items():
            button.setIcon(QIcon(_anchor_pixmap(anchor, color)))


def _anchor_pixmap(anchor: VideoAnchor, color: QColor) -> QPixmap:
    """A pane with a picture against the side or corner it is aligned to."""

    size = _ANCHOR_ICON_SIZE

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setPen(QPen(color, 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(QRectF(0.5, 0.5, size - 1, size - 1))

    # small enough for its three places each way to be well apart
    row, col = _ANCHOR_CELLS[anchor]
    inset = 2.5
    picture_w, picture_h = size * 0.4, size * 0.3
    room_w = size - 2 * inset - picture_w
    room_h = size - 2 * inset - picture_h

    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRect(
        QRectF(
            inset + room_w * col / 2,
            inset + room_h * row / 2,
            picture_w,
            picture_h,
        )
    )

    painter.end()

    return pixmap
