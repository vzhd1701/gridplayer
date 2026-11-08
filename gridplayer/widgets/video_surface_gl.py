"""A surface that draws the frame's texture with GL, nothing read back.

The texture is the render thread's, made in a context that shares with every
QOpenGLWidget's: see QtShareGroup. Qt draws the widget into a texture of its
own and puts the window together from those, so there is still a copy, but it
never leaves the GPU.

Qt makes each QOpenGLWidget a context of its own as it's first shown, about
40 ms on NVIDIA. A cell's frame is shown once it has loaded, so a grid's were
all made at once as the cells came up, holding the window up for a second. So
each surface starts as soon as it's in the window, shown or not, one at a time,
a turn of the event loop apart, while the cells are loading; a cell says it has
loaded once its picture can be drawn.
"""

import functools

from PyQt5 import sip
from PyQt5.QtCore import (
    QCoreApplication,
    QEvent,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QImage,
    QOpenGLFramebufferObject,
    QOpenGLTextureBlitter,
    QOpenGLVersionProfile,
    QPainter,
    QResizeEvent,
)
from PyQt5.QtWidgets import QOpenGLWidget, QWidget

from gridplayer.utils.aspect_calc import ViewPlacement
from gridplayer.utils.gl_window_size import draw_at_window_size
from gridplayer.widgets.video_frame_vlc_base import native_px
from gridplayer.widgets.video_surface_sw import VideoSurfaceView, unflipped_source

GL_COLOR_BUFFER_BIT = 0x00004000

# between one surface starting and the next: the window is drawn in between
START_INTERVAL_MS = 10

# moved to another window, which QOpenGLWidget starts on as well, as on a show
_WINDOW_CHANGE_INTERNAL = 215


class _StartQueue:
    """Surfaces waiting to start, in the order they asked. One that can't yet
    is passed over: it asks again once moved or sized."""

    def __init__(self):
        self._waiting: list[GLVideoSurface] = []
        self._timer: QTimer | None = None

    def ask(self, surface: "GLVideoSurface") -> None:
        if surface not in self._waiting:
            self._waiting.append(surface)

        if self._timer is None:
            self._timer = QTimer(QCoreApplication.instance())
            self._timer.setSingleShot(True)
            self._timer.setInterval(START_INTERVAL_MS)
            self._timer.timeout.connect(self._start_next)

        if not self._timer.isActive():
            self._timer.start()

    def _start_next(self) -> None:
        while self._waiting:
            surface = self._waiting.pop(0)
            if not sip.isdeleted(surface) and surface.can_start():
                surface.start()
                break

        if self._waiting:
            self._timer.start()


_start_queue = _StartQueue()


class _KeptTexture:
    """The texture on show once its video has gone, the surface's to delete
    as another comes or as the surface goes, painted or not: through the
    share group, which needs no context of the surface's."""

    def __init__(self, delete_textures):
        self.texture = 0
        self._delete_textures = delete_textures

    def let_go(self, *_args) -> None:
        texture, self.texture = self.texture, 0

        # with nothing to delete it, or the app going, it goes with the app
        if (
            texture
            and self._delete_textures is not None
            and not QCoreApplication.closingDown()
        ):
            self._delete_textures([texture])


class _HeldTillContextGone:
    """A blitter its context holds on to, for as long as it's there.

    As a context goes with no context current, as when its widget goes, Qt
    frees the blitter's vertex array on a hidden window made for it. Python
    can run while it's made, and the garbage collector with it, and a blitter
    only Python's, its widget going, could be freed then, under Qt's feet: a
    crash closing a cell.
    """

    def __init__(self, blitter: QOpenGLTextureBlitter):
        self.blitter = blitter

    def let_go(self, *_args) -> None:
        self.blitter = None


class GLVideoSurface(VideoSurfaceView, QOpenGLWidget):
    # its picture can be drawn from now on
    drawing_started = pyqtSignal()

    def __init__(self, parent=None, delete_textures=None):
        super().__init__(parent)

        self._is_started = False
        self._texture = 0
        self._frame_w = 0
        self._frame_h = 0
        self._kept = _KeptTexture(delete_textures)
        self._blitter: QOpenGLTextureBlitter | None = None
        self._gl = None

        # held on to by the connection, as the surface is gone by then
        self.destroyed.connect(functools.partial(_KeptTexture.let_go, self._kept))

        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        _start_queue.ask(self)

    def has_frame(self) -> bool:
        return bool(self._texture)

    def is_drawing(self) -> bool:
        return self._is_started

    def can_start(self) -> bool:
        # what Qt needs to make a context and a framebuffer: not being shown
        return (
            not self._is_started
            and not self.size().isEmpty()
            and self.window().windowHandle() is not None
        )

    def start(self) -> None:
        """Its context made, as Qt would have once shown."""

        self._is_started = True

        QOpenGLWidget.resizeEvent(self, QResizeEvent(self.size(), self.size()))
        self.update()

        self.drawing_started.emit()

    def event(self, event: QEvent) -> bool:
        kind = event.type()

        if not self._is_started and kind in {QEvent.Show, _WINDOW_CHANGE_INTERNAL}:
            _start_queue.ask(self)
            # past QOpenGLWidget, which would start here
            return QWidget.event(self, event)

        return super().event(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        # QOpenGLWidget starts here too
        if self._is_started:
            super().resizeEvent(event)
        else:
            _start_queue.ask(self)

    def frame_size(self) -> tuple[int, int]:
        if not self.has_frame():
            return 0, 0
        return self._frame_w, self._frame_h

    def present_texture(self, texture: int, width: int, height: int) -> None:
        if self._kept.texture != texture:
            self._kept.let_go()

        self._texture = texture
        self._frame_w, self._frame_h = width, height
        self.update()

    def own_texture(self) -> None:
        """The texture on show is this surface's now, its video gone."""

        self._kept.texture = self._texture

    def drop_frame(self) -> None:
        """The frame on show gone with its video, which failed: not shown on,
        unless it's this surface's."""

        if self._texture != self._kept.texture:
            self._texture = 0
            self.update()

    def frame_image(self) -> QImage | None:
        """The frame on show, read from its texture at the size it is."""

        if not self.has_frame() or self._gl is None:
            return None

        self.makeCurrent()

        try:
            framebuffer = QOpenGLFramebufferObject(self._frame_w, self._frame_h)
            framebuffer.bind()

            whole = QRect(0, 0, self._frame_w, self._frame_h)
            self._gl.glViewport(0, 0, self._frame_w, self._frame_h)
            self._blitter.bind()
            self._blitter.blit(
                self._texture,
                QOpenGLTextureBlitter.targetTransform(QRectF(whole), whole),
                QOpenGLTextureBlitter.OriginTopLeft,
            )
            self._blitter.release()

            framebuffer.release()
            image = framebuffer.toImage()
        finally:
            self.doneCurrent()

        return image.convertToFormat(QImage.Format_RGB32)

    def _painted_flip(self) -> tuple[bool, bool] | None:
        return None

    def initializeGL(self) -> None:
        context = self.context()

        # before the blitter's own, so it needs no hidden window
        context.aboutToBeDestroyed.connect(self._on_context_going)

        self._blitter = QOpenGLTextureBlitter()
        self._blitter.create()

        held = _HeldTillContextGone(self._blitter)
        context.destroyed.connect(functools.partial(_HeldTillContextGone.let_go, held))

        # None on OpenGL ES, which then fills with a painter
        profile = QOpenGLVersionProfile()
        profile.setVersion(2, 0)
        self._gl = self.context().versionFunctions(profile)
        if self._gl is not None:
            self._gl.initializeOpenGLFunctions()

        # the window is put together with GL from now on
        draw_at_window_size(self.window())

    def _on_context_going(self) -> None:
        # Not as the surface itself goes: PyQt has cut it off by then.
        self.makeCurrent()
        self._blitter.destroy()
        self.doneCurrent()

    def paintGL(self) -> None:
        placement = self.placement() if self.has_frame() else None

        # A painter costs more to start each frame than drawing the picture,
        # and black all over costs the GPU next to nothing.
        if self._gl is not None:
            self._gl.glClearColor(0, 0, 0, 1)
            self._gl.glClear(GL_COLOR_BUFFER_BIT)
            if placement is not None:
                self._blit(placement)
            return

        painter = QPainter(self)

        if placement is None:
            painter.fillRect(self.rect(), Qt.black)
            return

        for bar in self._bars(placement.target):
            painter.fillRect(bar, Qt.black)

        painter.beginNativePainting()
        self._blit(placement)
        painter.endNativePainting()

    def _blit(self, placement: ViewPlacement) -> None:
        # All of the widget's framebuffer, the size of which Qt rounds, where
        # the viewport it sets is cut down: a pixel short at some scales.
        ratio = self.devicePixelRatioF()
        viewport = QRect(
            0, 0, native_px(self.width(), ratio), native_px(self.height(), ratio)
        )
        if self._gl is not None:
            self._gl.glViewport(0, 0, viewport.width(), viewport.height())

        x, y, width, height = placement.target
        target = QOpenGLTextureBlitter.targetTransform(
            QRectF(x * ratio, y * ratio, width * ratio, height * ratio), viewport
        )

        source_x, source_y, source_w, source_h = placement.source

        flip = self._painted_flip()
        if flip is not None:
            is_across, is_up_down = flip
            source_x, source_y, source_w, source_h = unflipped_source(
                placement.source, self.frame_size(), flip
            )
            target.scale(-1 if is_across else 1, -1 if is_up_down else 1)

        # Rows top first, as Qt's top-left origin has them, which counts the
        # part asked for from the bottom all the same.
        source_y = self._frame_h - source_y - source_h

        source = QOpenGLTextureBlitter.sourceTransform(
            QRectF(source_x, source_y, source_w, source_h),
            QSize(self._frame_w, self._frame_h),
            QOpenGLTextureBlitter.OriginTopLeft,
        )

        self._blitter.bind()
        self._blitter.blit(self._texture, target, source)
        self._blitter.release()
