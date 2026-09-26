from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QWidget

from gridplayer.params.static import VideoTransform, ViewParams
from gridplayer.utils.aspect_calc import ViewPlacement, calc_view_placement

# How much bigger than the picture VLC can make the frame it hands over. It
# asks for a size its decoder likes, 640x360 coming as 640x386 or 788x576 as
# 800x578, and scales the picture up to fill all of it. A track size further
# off than this is one the stream has since moved away from.
_MAX_FRAME_OVERSIZE = 64


class SoftwareVideoSurface(QWidget):
    """Paints the latest RGB32 frame. Avoids QGraphicsView.setPixmap."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._image: QImage | None = None
        self._rgb = None
        # the placeholder shown before the first frame, not one worth saving
        self._is_black = False
        self._view = ViewParams()
        self._transform = VideoTransform.NONE
        self._track_size: tuple[int, int] | None = None

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

    def picture_size(self) -> tuple[int, int]:
        """The frame's size in video pixels, the ones the view is in.

        The frame comes scaled up to a size the decoder likes, so its own
        pixels are not square: the track's size says what shape it is.
        The frame's own size where the track has none, or one the frames
        no longer come at.
        """

        frame_w, frame_h = self.frame_size()

        if self._track_size is None:
            return frame_w, frame_h

        width, height = self._track_size

        is_track_size = (
            0 < width <= frame_w
            and 0 < height <= frame_h
            and frame_w - width <= _MAX_FRAME_OVERSIZE
            and frame_h - height <= _MAX_FRAME_OVERSIZE
        )

        return (width, height) if is_track_size else (frame_w, frame_h)

    def frame_image(self) -> QImage | None:
        """A copy of the frame on show, as it came from the decoder.

        At the size it came at, see picture_size for the size it is.
        """

        if not self.has_frame() or self._is_black:
            return None

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

    def set_view(
        self,
        view: ViewParams,
        transform: VideoTransform | None = VideoTransform.NONE,
        track_size: tuple[int, int] | None = None,
    ) -> None:
        self._view = view
        self._transform = transform
        self._track_size = track_size
        self.update()

    def placement(self) -> ViewPlacement | None:
        """Where the frame goes, the source in the frame's own pixels."""

        picture_w, picture_h = self.picture_size()

        placement = calc_view_placement(
            (picture_w, picture_h),
            (self.width(), self.height()),
            self._view,
            self._transform,
        )

        if placement is None:
            return None

        frame_w, frame_h = self.frame_size()
        scale_x, scale_y = frame_w / picture_w, frame_h / picture_h
        x, y, width, height = placement.source

        return ViewPlacement(
            source=(x * scale_x, y * scale_y, width * scale_x, height * scale_y),
            target=placement.target,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        painter.fillRect(self.rect(), Qt.black)
        if not self.has_frame():
            return

        placement = self.placement()
        if placement is None:
            return

        painter.drawImage(
            QRectF(*placement.target), self._image, QRectF(*placement.source)
        )
