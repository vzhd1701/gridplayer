from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params.static import VideoCrop, VideoTransform
from gridplayer.utils.qt import translate

_DIMENSION_FALLBACK = 9999

_ROTATION_TRANSFORMS = {
    VideoTransform.ROTATE_90,
    VideoTransform.ROTATE_270,
    VideoTransform.TRANSPOSE,
    VideoTransform.ANTITRANSPOSE,
}


class _CropPreview(QWidget):
    """Small live canvas showing where the crop sits within the frame."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._frame_w = 0
        self._frame_h = 0
        self._left = self._top = self._right = self._bottom = 0.0

    def set_crop(self, frame_w, frame_h, left, top, right, bottom):
        self._frame_w = frame_w
        self._frame_h = frame_h
        self._left, self._top, self._right, self._bottom = left, top, right, bottom
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._frame_w and self._frame_h:
            self._paint_frame(painter)

        painter.end()

    def _paint_frame(self, painter):
        margin = 10
        avail_w = self.width() - margin * 2
        avail_h = self.height() - margin * 2
        if avail_w <= 0 or avail_h <= 0:
            return

        scale = min(avail_w / self._frame_w, avail_h / self._frame_h)
        frame_w = self._frame_w * scale
        frame_h = self._frame_h * scale
        x0 = (self.width() - frame_w) / 2
        y0 = (self.height() - frame_h) / 2
        frame_rect = QRectF(x0, y0, frame_w, frame_h)

        # Full source frame, drawn like a regular sunken widget well.
        painter.setPen(QPen(self.palette().mid(), 1))
        painter.setBrush(self.palette().base())
        painter.drawRect(frame_rect)

        # Shaded bands for the parts being cropped away.
        left_px = min(self._left * scale, frame_w)
        right_px = min(self._right * scale, frame_w)
        top_px = min(self._top * scale, frame_h)
        bottom_px = min(self._bottom * scale, frame_h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 130))
        if left_px > 0:
            painter.drawRect(QRectF(x0, y0, left_px, frame_h))
        if right_px > 0:
            painter.drawRect(QRectF(x0 + frame_w - right_px, y0, right_px, frame_h))
        if top_px > 0:
            painter.drawRect(QRectF(x0, y0, frame_w, top_px))
        if bottom_px > 0:
            painter.drawRect(QRectF(x0, y0 + frame_h - bottom_px, frame_w, bottom_px))

        # Outline of what remains after the crop.
        active_x = x0 + left_px
        active_y = y0 + top_px
        active_w = max(frame_w - left_px - right_px, 0)
        active_h = max(frame_h - top_px - bottom_px, 0)

        if active_w > 0 and active_h > 0:
            painter.setPen(QPen(self.palette().highlight(), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(active_x, active_y, active_w, active_h))


class SetCropDialog(QDialog):
    """Edits the active video crop; changes are applied live to the video."""

    def __init__(self, video_block, parent=None):
        super().__init__(parent)

        self._block = video_block
        self._original_crop = video_block.video_params.crop
        self._original_aspect = video_block.video_params.aspect_mode

        self.setWindowTitle(translate("Dialog - Set Crop", "Set Crop"))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._raw_width, self._raw_height = self._track_dimensions()
        self._is_rotated = self._block.video_params.transform in _ROTATION_TRANSFORMS
        width, height = self._display_dimensions()

        self._preview = _CropPreview()

        crop_box = QGroupBox(translate("Dialog - Set Crop", "Crop Margins (px)"))
        grid = QGridLayout(crop_box)

        self._spins = {}
        for row, col, name, name_title, dimension in (
            (0, 0, "left", translate("Dialog - Set Crop", "Left"), width),
            (0, 1, "right", translate("Dialog - Set Crop", "Right"), width),
            (1, 0, "top", translate("Dialog - Set Crop", "Top"), height),
            (1, 1, "bottom", translate("Dialog - Set Crop", "Bottom"), height),
        ):
            label = QLabel(name_title)
            spin = QSpinBox()
            spin.setRange(0, dimension or _DIMENSION_FALLBACK)
            spin.setValue(getattr(self._original_crop, name.capitalize()))
            spin.setAlignment(Qt.AlignRight)
            spin.valueChanged.connect(self._apply_live)

            grid.addWidget(label, row, col * 2)
            grid.addWidget(spin, row, col * 2 + 1)

            self._spins[name] = spin

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._size_label = QLabel()
        self._size_label.setAlignment(Qt.AlignCenter)
        size_font = self._size_label.font()
        size_font.setBold(True)
        self._size_label.setFont(size_font)

        self._area_label = QLabel()
        self._area_label.setAlignment(Qt.AlignCenter)

        reset = QPushButton(translate("Dialog - Set Crop", "Reset"))
        reset.clicked.connect(self._on_reset)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.addWidget(self._preview)
        root.addWidget(crop_box)
        root.addWidget(self._size_label)
        root.addWidget(self._area_label)
        root.addLayout(bottom)

        self._update_size_label()

        self.setFixedSize(self.sizeHint())

    def accept(self):
        self._set_block_crop(is_silent=False)
        super().accept()

    def reject(self):
        self._restore_original()
        super().reject()

    def _on_reset(self):
        for spin in self._spins.values():
            spin.setValue(0)

    def _apply_live(self):
        self._set_block_crop(is_silent=True)
        self._update_size_label()

    def _set_block_crop(self, is_silent):
        crop = self._spin_crop()

        self._block.set_crop(crop, is_silent=is_silent)

    def _restore_original(self):
        if self._block.video_params.crop != self._original_crop:
            self._block.set_crop(self._original_crop, is_silent=True)

        if self._block.video_params.aspect_mode != self._original_aspect:
            self._block.set_aspect(self._original_aspect)

    def _spin_crop(self):
        return VideoCrop(
            self._spins["left"].value(),
            self._spins["top"].value(),
            self._spins["right"].value(),
            self._spins["bottom"].value(),
        )

    def _track_dimensions(self):
        tracks = self._block.video_tracks or {}
        track = tracks.get(self._block.video_params.video_track_id)
        if track is None and tracks:
            track = next(iter(tracks.values()))
        if track is None:
            return 0, 0

        return track.video_dimensions

    def _display_dimensions(self):
        if self._is_rotated:
            return self._raw_height, self._raw_width

        return self._raw_width, self._raw_height

    def _update_size_label(self):
        if not self._raw_width or not self._raw_height:
            self._size_label.hide()
            self._area_label.hide()
            self._preview.hide()
            return

        left = self._spins["left"].value()
        top = self._spins["top"].value()
        right = self._spins["right"].value()
        bottom = self._spins["bottom"].value()

        cropped_w = max(self._raw_width - left - right, 0)
        cropped_h = max(self._raw_height - top - bottom, 0)
        video_w, video_h = self._display_dimensions()
        if self._is_rotated:
            cropped_w, cropped_h = cropped_h, cropped_w

        self._size_label.setText(
            "{}: {}x{} | {}: {}x{}".format(
                translate("Dialog - Set Crop", "Video"),
                video_w,
                video_h,
                translate("Dialog - Set Crop", "Cropped"),
                cropped_w,
                cropped_h,
            )
        )

        total_area = video_w * video_h
        if total_area:
            kept_pct = round(100 * (cropped_w * cropped_h) / total_area)
            self._area_label.setText(
                translate(
                    "Dialog - Set Crop", "{}% of the original frame retained"
                ).format(kept_pct)
            )
            self._area_label.show()
        else:
            self._area_label.hide()

        # The preview is drawn in display space. For unrotated video the
        # spin values map onto that space directly; for rotated video the
        # exact left/right/top/bottom split after rotation is ambiguous, so
        # the removed margin is shown centered on each axis instead.
        if not self._is_rotated:
            edges = (left, top, right, bottom)
        else:
            horiz_reduction = max(video_w - cropped_w, 0)
            vert_reduction = max(video_h - cropped_h, 0)
            edges = (
                horiz_reduction / 2,
                vert_reduction / 2,
                horiz_reduction / 2,
                vert_reduction / 2,
            )

        self._preview.set_crop(video_w, video_h, *edges)
