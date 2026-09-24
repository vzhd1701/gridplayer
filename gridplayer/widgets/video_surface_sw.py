from PyQt5.QtCore import QRect, QRectF, Qt
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QWidget

from gridplayer.params.static import VideoAspect, VideoCrop
from gridplayer.utils.aspect_calc import calc_crop_region

_ZERO_CROP = VideoCrop(0, 0, 0, 0)
# Same extra zoom as the old QGraphicsView path, to hide decoder edge pixels.
_BLACK_BORDER_CUT = 0.05


class SoftwareVideoSurface(QWidget):
    """Paints the latest RGB32 frame. Avoids QGraphicsView.setPixmap."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._image: QImage | None = None
        self._rgb = None
        # the placeholder shown before the first frame, not one worth saving
        self._is_black = False
        self._aspect = VideoAspect.FIT
        self._scale = 1.0
        self._crop = _ZERO_CROP

        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setAutoFillBackground(False)

    def has_frame(self) -> bool:
        return self._image is not None and not self._image.isNull()

    def frame_size(self) -> tuple[int, int]:
        if not self.has_frame():
            return 0, 0
        return self._image.width(), self._image.height()

    def frame_image(self, visible_size: tuple[int, int] | None = None) -> QImage | None:
        """A copy of the frame on show, as it came from the decoder.

        The decoder pads its buffer out to a size it likes, 788x576 coming
        as 800x578, so the part of it that is picture can be asked for.
        """

        if not self.has_frame() or self._is_black:
            return None

        width, height = visible_size or (0, 0)

        if 0 < width <= self._image.width() and 0 < height <= self._image.height():
            return self._image.copy(0, 0, width, height)

        return self._image.copy()

    def present_rgb32(self, buf, width, height) -> None:
        if not buf or not width or not height:
            return

        # Dimensions arrive via a queued signal, the buffer via shared memory
        # that the decoder reallocates on the VLC thread. A mid-stream switch to
        # a smaller frame lands the new buffer here while width/height are still
        # the old, larger ones, and QImage would read past the end of it.
        # Skip such a frame; the matching dimensions are already on their way.
        if len(buf) < height * width * 4:
            return

        # Keep buf alive for this QImage; skip .copy() (second full-frame memcpy).
        self._rgb = buf
        self._image = QImage(buf, width, height, width * 4, QImage.Format_RGB32)
        self._is_black = False
        self.update()

    def present_black(self, width, height) -> None:
        if not width or not height:
            return
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(Qt.black)
        self._image = image
        self._is_black = True
        self.update()

    def set_view(self, aspect: VideoAspect, scale: float, crop: VideoCrop) -> None:
        self._aspect = aspect
        self._scale = scale
        self._crop = crop
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        painter.fillRect(self.rect(), Qt.black)
        if not self.has_frame():
            return

        src = self._source_rect()
        dest = self._dest_rect(src)
        if dest.isEmpty() or src.isEmpty():
            return
        painter.drawImage(dest, self._image, QRectF(src))

    def _source_rect(self) -> QRect:
        width, height = self.frame_size()
        x, y, crop_w, crop_h = calc_crop_region((width, height), self._crop)
        return QRect(x, y, crop_w, crop_h)

    def _dest_rect(self, src: QRect) -> QRectF:
        widget_w = self.width()
        widget_h = self.height()
        if widget_w <= 0 or widget_h <= 0 or src.isEmpty():
            return QRectF()

        src_w = src.width()
        src_h = src.height()
        scale = self._scale + _BLACK_BORDER_CUT

        if self._aspect == VideoAspect.STRETCH:
            dest_w = widget_w * scale
            dest_h = widget_h * scale
        elif self._aspect == VideoAspect.FIT:
            fit = max(widget_w / src_w, widget_h / src_h) * scale
            dest_w = src_w * fit
            dest_h = src_h * fit
        else:
            fit = min(widget_w / src_w, widget_h / src_h) * scale
            dest_w = src_w * fit
            dest_h = src_h * fit

        return QRectF(
            (widget_w - dest_w) / 2,
            (widget_h - dest_h) / 2,
            dest_w,
            dest_h,
        )
