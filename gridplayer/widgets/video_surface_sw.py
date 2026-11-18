import math

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QRegion
from PyQt6.QtWidgets import QWidget

from gridplayer.params.static import VideoTransform, ViewParams
from gridplayer.utils.aspect_calc import ViewPlacement, calc_view_placement
from gridplayer.utils.screenshots import ScreenshotView

# How much bigger than the picture VLC can make the frame it hands over. It
# asks for a size its decoder likes, 640x360 coming as 640x386 or 788x576 as
# 800x578, and scales the picture up to fill all of it. A track size further
# off than this is one the stream has since moved away from.
_MAX_FRAME_OVERSIZE = 64


def unflipped_source(
    source: tuple[float, float, float, float],
    frame_size: tuple[int, int],
    flip: tuple[bool, bool],
) -> tuple[float, float, float, float]:
    """The source, a part of the picture as shown flipped, in the frame as it
    comes, unflipped."""

    x, y, width, height = source
    frame_w, frame_h = frame_size
    is_across, is_up_down = flip

    if is_across:
        x = frame_w - x - width
    if is_up_down:
        y = frame_h - y - height

    return x, y, width, height


class VideoSurfaceView:
    """What a surface knows of its frame and the view, whatever draws it. Goes
    before the widget's class in its bases."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._view = ViewParams()
        self._transform = VideoTransform.NONE
        # how wide a pixel of the picture is for its height, see set_view
        self._pixel_aspect = 1.0
        self._track_size: tuple[int, int] | None = None

    def has_frame(self) -> bool:
        raise NotImplementedError

    def frame_size(self) -> tuple[int, int]:
        raise NotImplementedError

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

    def set_view(
        self,
        view: ViewParams,
        transform: VideoTransform | None = VideoTransform.NONE,
        track_size: tuple[int, int] | None = None,
        pixel_aspect: float = 1.0,
    ) -> None:
        self._view = view
        self._transform = transform
        self._track_size = track_size
        self._pixel_aspect = pixel_aspect
        self.update()

    def placement(self) -> ViewPlacement | None:
        """Where the frame goes, the source in the frame's own pixels."""

        picture_w, picture_h = self.picture_size()

        placement = calc_view_placement(
            (picture_w, picture_h),
            (self.width(), self.height()),
            self._view,
            self._transform,
            pixel_aspect=self._pixel_aspect,
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

    def _bars(self, target) -> list[QRect]:
        """Where the picture won't be, to fill black: all of it filled first costs
        nearly as much as drawing the picture.

        A pixel away from the picture's edge, as on a screen scaled by 1.5 a
        pixel here can be part of one that the picture only partly covers: the
        picture is drawn over the rest.
        """

        x, y, width, height = target
        left, top = math.ceil(x) + 1, math.ceil(y) + 1
        right, bottom = math.floor(x + width) - 1, math.floor(y + height) - 1

        if right <= left or bottom <= top:
            return [self.rect()]

        covered = QRect(left, top, right - left, bottom - top)

        return QRegion(self.rect()).subtracted(QRegion(covered)).rects()


class SoftwareVideoSurface(VideoSurfaceView, QWidget):
    """Paints the latest frame, 4 bytes a pixel. Avoids QGraphicsView.setPixmap."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._image: QImage | None = None
        self._rgb = None
        # the placeholder shown before the first frame, not one worth saving
        self._is_black = False

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowFlags(Qt.WindowType.WindowTransparentForInput)
        self.setAutoFillBackground(False)

    def has_frame(self) -> bool:
        return self._image is not None and not self._image.isNull()

    def frame_size(self) -> tuple[int, int]:
        if not self.has_frame():
            return 0, 0
        return self._image.width(), self._image.height()

    def frame_image(self) -> QImage | None:
        """A copy of the frame on show, as it came from the decoder.

        At the size it came at, see picture_size for the size it is.
        """

        if not self.has_frame() or self._is_black:
            return None

        return self._image.copy()

    def present_rgb32(
        self, buf, width, height, image_format=QImage.Format.Format_RGB32
    ) -> None:
        """A frame of 4 bytes a pixel, RGB32 as VLC's are and mostly MPV's, or
        RGBX8888 from OpenGL ES that only reads back RGBA: then so is the
        image frame_image gives."""

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
        self._image = QImage(buf, width, height, width * 4, image_format)
        self._is_black = False
        self.update()

    def present_black(self, width, height) -> None:
        if not width or not height:
            return
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.black)
        self._image = image
        self._is_black = True
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        placement = self.placement() if self.has_frame() else None

        if placement is None:
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
            return

        for bar in self._bars(placement.target):
            painter.fillRect(bar, Qt.GlobalColor.black)

        self._draw_frame(painter, placement)

    def _draw_frame(self, painter: QPainter, placement: ViewPlacement) -> None:
        painter.drawImage(
            QRectF(*placement.target), self._image, QRectF(*placement.source)
        )


class PaintedVideoFrame:
    """What a video frame painted on one of these has in common. Goes before the
    frame's class in its bases."""

    surface_class = SoftwareVideoSurface

    def ui_video_surface(self):
        return self.surface_class(self)

    def take_snapshot(self) -> None:
        # last frame stays painted on the surface
        self.video_driver.set_pause(True)

    def shown_frame_image(self):
        return self.video_surface.frame_image()

    def screenshot_view(self):
        return ScreenshotView(
            self._pane_size(),
            self._view,
            self._transform,
            self.video_surface.picture_size(),
            self._orientation(),
            self._pixel_aspect(),
        )

    def adjust_view(self) -> bool:
        """True if there's nothing to place, as the frame's own says."""

        if super().adjust_view():
            return True

        self.video_surface.set_view(
            self._view, self._transform, self._frame_size(), self._pixel_aspect()
        )

        return False

    def _view_frame_size(self):
        return self.video_surface.picture_size()
