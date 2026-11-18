"""MPV's frames drawn with GL, nothing read back: one surface for all of a
window's videos.

The textures are the render thread's, made in a context that shares with Qt's:
see QtShareGroup. A window gets one GLGridSurface, a QOpenGLWidget its size
under all of its other widgets, made as the first video in it has a frame.
Each cell has a GLVideoSurface: a plain widget that leaves its part of the
window see-through, as Qt does under a QOpenGLWidget, so what the grid
surface draws there shows. The grid surface draws each cell's picture where
its surface is, in the order they are stacked, cut to what of it is in view.

What is over a cell's surface is drawn over its picture, and a surface over
another cell clears that cell's controls under it: tiles over one another
look as they would with a surface each.

A QOpenGLWidget a cell cost a context made as each came up, about 40 ms on
NVIDIA, and each frame a context switch and a framebuffer of its own: at 36
cells the GUI thread was busy half the time and frames were lost. See 13.5
in docs/plans/MPV_PLAN.md.
"""

import contextlib
import functools
import logging

from PyQt6 import sip
from PyQt6.QtCore import (
    QCoreApplication,
    QEvent,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLTextureBlitter
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget

from gridplayer.mpv_player.gl_context import qt_gl_functions
from gridplayer.utils.aspect_calc import ViewPlacement
from gridplayer.utils.gl_window_size import set_up_gl_window
from gridplayer.widgets.video_frame_vlc_base import native_px, native_rect
from gridplayer.widgets.video_surface_sw import VideoSurfaceView, unflipped_source

GL_COLOR_BUFFER_BIT = 0x00004000
GL_SCISSOR_TEST = 0x0C11

# how long a surface with a frame and no window yet waits to look again
JOIN_RETRY_MS = 50

# what has the grid surface work out again where the cells' surfaces are, on
# one of them or anything it's in
_PLACE_EVENTS = frozenset(
    {
        QEvent.Type.Move,
        QEvent.Type.Resize,
        QEvent.Type.Show,
        QEvent.Type.Hide,
        QEvent.Type.ZOrderChange,
        QEvent.Type.ParentChange,
    }
)

# what has a cell's surface look for its window's grid surface
_JOIN_EVENTS = frozenset({QEvent.Type.Show, QEvent.Type.ParentChange})

logger = logging.getLogger(__name__)


class _KeptTexture:
    """The texture on show once its video has gone, the surface's to delete
    as another comes or as the surface goes: through the share group, which
    needs no context of the surface's."""

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


def placed_surfaces(
    surfaces: list["GLVideoSurface"], window: QWidget
) -> list[tuple["GLVideoSurface", QPoint, QRect]]:
    """The surfaces on show, the lowest first, each with where it is in the
    window and the part of it its parents leave in view, in the window."""

    # where each widget is among its parent's children, the last in front,
    # which raise_() puts last; by Qt's object, as a wrapper PyQt makes for
    # one of Qt's own can go and another come
    stacked_at: dict[int, dict[int, int]] = {}
    placed = []

    for surface in surfaces:
        if not surface.isVisible():
            continue

        stacking = []
        origin = QPoint(0, 0)
        shown = surface.rect()
        widget = surface

        while widget is not window:
            parent = widget.parentWidget()
            if parent is None:
                break

            key = sip.unwrapinstance(parent)
            order = stacked_at.get(key)
            if order is None:
                order = {
                    sip.unwrapinstance(c): at for at, c in enumerate(parent.children())
                }
                stacked_at[key] = order

            stacking.append(order[sip.unwrapinstance(widget)])
            origin += widget.pos()
            shown = shown.translated(widget.pos()).intersected(parent.rect())
            widget = parent

        if widget is window and not shown.isEmpty():
            placed.append((stacking[::-1], surface, origin, shown))

    placed.sort(key=lambda item: item[0])

    return [(surface, origin, shown) for _, surface, origin, shown in placed]


class GLGridSurface(QOpenGLWidget):
    """Draws the pictures of all the cells' surfaces in a window, under them."""

    # it can draw from now on
    ready = pyqtSignal()

    @staticmethod
    def of(window: QWidget) -> "GLGridSurface":
        grid = window.findChild(
            GLGridSurface, "", Qt.FindChildOption.FindDirectChildrenOnly
        )

        return grid if grid is not None else GLGridSurface(window)

    def __init__(self, window: QWidget):
        super().__init__(window)

        self._surfaces: list[GLVideoSurface] = []
        # where they were, the last time it was worked out: see placed_surfaces
        self._placed: list[tuple[GLVideoSurface, QPoint, QRect]] | None = None

        self._blitter: QOpenGLTextureBlitter | None = None
        self._gl = None

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        window.installEventFilter(self)
        self.setGeometry(window.rect())
        self.lower()
        self.show()

    def is_ready(self) -> bool:
        return self._blitter is not None

    def add(self, surface: "GLVideoSurface") -> None:
        """A cell's surface, drawn from now on, followed as anything it's in
        moves: it tells of its own moves itself."""

        if surface not in self._surfaces:
            self._surfaces.append(surface)

        self._follow(surface)
        self.surfaces_moved()

    def remove(self, surface: "GLVideoSurface") -> None:
        if surface in self._surfaces:
            self._surfaces.remove(surface)
        self.surfaces_moved()

    def _follow(self, surface: "GLVideoSurface") -> None:
        # Qt filters each event once, however often it's asked to
        widget = surface.parentWidget()
        while widget is not None and widget is not self.parentWidget():
            widget.installEventFilter(self)
            widget = widget.parentWidget()

    def surfaces_moved(self) -> None:
        self._placed = None
        self.update()

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()

        if watched is self.parentWidget():
            if kind == QEvent.Type.Resize:
                self.setGeometry(watched.rect())
        elif kind in _PLACE_EVENTS:
            self.surfaces_moved()

        return False

    def initializeGL(self) -> None:
        context = self.context()

        # before the blitter's own, so it needs no hidden window
        context.aboutToBeDestroyed.connect(self._on_context_going)

        self._blitter = QOpenGLTextureBlitter()
        self._blitter.create()

        held = _HeldTillContextGone(self._blitter)
        context.destroyed.connect(functools.partial(_HeldTillContextGone.let_go, held))

        self._gl = qt_gl_functions(context)
        if self._gl is None:
            logger.error("No OpenGL functions to draw the videos with")

        # the window is put together with GL from now on
        set_up_gl_window(self.window())

        # once Qt is done starting it
        QTimer.singleShot(0, self.ready.emit)

    def _on_context_going(self) -> None:
        # Not as the surface itself goes: PyQt has cut it off by then.
        self.makeCurrent()
        self._blitter.destroy()
        self.doneCurrent()

    def paintGL(self) -> None:
        gl = self._gl
        if gl is None:
            # no pictures, the window as it would be with none
            painter = QPainter(self)
            painter.fillRect(self.rect(), self._background())
            return

        # All of the framebuffer, the size of which Qt rounds, where the
        # viewport it sets is cut down: a pixel short at some scales.
        ratio = self.devicePixelRatioF()
        viewport = QRect(
            0, 0, native_px(self.width(), ratio), native_px(self.height(), ratio)
        )
        gl.glViewport(0, 0, viewport.width(), viewport.height())

        color = self._background()
        gl.glClearColor(color.redF(), color.greenF(), color.blueF(), 1)
        gl.glClear(GL_COLOR_BUFFER_BIT)

        if self._placed is None:
            self._placed = self._place_surfaces()

        if not self._placed:
            return

        # A black clear costs the GPU next to nothing: all of a cell first,
        # then the picture over it.
        gl.glClearColor(0, 0, 0, 1)
        gl.glEnable(GL_SCISSOR_TEST)
        self._blitter.bind()

        for surface, origin, shown in self._placed:
            # gone since they were placed
            if sip.isdeleted(surface):
                continue

            self._scissor(shown, ratio, viewport.height())
            gl.glClear(GL_COLOR_BUFFER_BIT)

            placement = surface.placement() if surface.has_frame() else None
            if placement is not None:
                surface.blit(self._blitter, placement, origin, ratio, viewport)

        self._blitter.release()
        gl.glDisable(GL_SCISSOR_TEST)

    def _background(self):
        window = self.window()
        return window.palette().color(window.backgroundRole())

    def _place_surfaces(self) -> list[tuple["GLVideoSurface", QPoint, QRect]]:
        window = self.window()
        self._surfaces = [s for s in self._surfaces if not sip.isdeleted(s)]

        for surface in list(self._surfaces):
            # put in another window, to be drawn by its own
            if surface.window() is not window:
                surface.leave_grid()
            else:
                # put somewhere else in this one, maybe
                self._follow(surface)

        return placed_surfaces(self._surfaces, window)

    def _scissor(self, rect: QRect, ratio: float, framebuffer_h: int) -> None:
        x, y, width, height = native_rect(
            rect.x(), rect.y(), rect.width(), rect.height(), ratio
        )

        # GL counts rows from the bottom
        self._gl.glScissor(x, framebuffer_h - y - height, width, height)

    def frame_image(self, texture: int, width: int, height: int) -> QImage | None:
        """A texture read at the size it is."""

        if self._gl is None:
            return None

        self.makeCurrent()

        try:
            framebuffer = QOpenGLFramebufferObject(width, height)
            framebuffer.bind()

            whole = QRect(0, 0, width, height)
            self._gl.glViewport(0, 0, width, height)
            self._blitter.bind()
            self._blitter.blit(
                texture,
                QOpenGLTextureBlitter.targetTransform(QRectF(whole), whole),
                QOpenGLTextureBlitter.Origin.OriginTopLeft,
            )
            self._blitter.release()

            framebuffer.release()
            image = framebuffer.toImage()
        finally:
            self.doneCurrent()

        return image.convertToFormat(QImage.Format.Format_RGB32)


class GLVideoSurface(VideoSurfaceView, QWidget):
    """Where a cell's picture is, drawn by its window's grid surface."""

    # its picture can be drawn from now on
    drawing_started = pyqtSignal()

    # grabs going on, which want the picture where the window has a hole
    _grabs = 0

    @staticmethod
    @contextlib.contextmanager
    def grabbing():
        """For a grab() or render(), which paint as the window is painted,
        with no telling them apart from inside a paint in PyQt."""

        GLVideoSurface._grabs += 1
        try:
            yield
        finally:
            GLVideoSurface._grabs -= 1

    def __init__(self, parent=None, delete_textures=None):
        super().__init__(parent)

        self._texture = 0
        self._frame_w = 0
        self._frame_h = 0
        self._kept = _KeptTexture(delete_textures)
        self._grid: GLGridSurface | None = None
        self._is_drawing = False

        # held on to by the connection, as the surface is gone by then
        self.destroyed.connect(functools.partial(_KeptTexture.let_go, self._kept))

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        # a frame came before the cell was in a window
        self._join_retry = QTimer(self)
        self._join_retry.setSingleShot(True)
        self._join_retry.setInterval(JOIN_RETRY_MS)
        self._join_retry.timeout.connect(self._join)

    def has_frame(self) -> bool:
        return bool(self._texture)

    def is_drawing(self) -> bool:
        return self._is_drawing

    def _join(self) -> None:
        if self._grid is not None:
            return

        window = self.window()
        if window is self or window.windowHandle() is None:
            if self._texture:
                self._join_retry.start()
            return

        self._grid = GLGridSurface.of(window)
        self._grid.add(self)

        if self._grid.is_ready():
            self._start_drawing()
        else:
            self._grid.ready.connect(self._start_drawing)

    def leave_grid(self) -> None:
        """Put in another window: drawn by that one's grid surface."""

        if self._grid is not None and not sip.isdeleted(self._grid):
            self._grid.remove(self)
        self._grid = None
        self._join_retry.start()

    def _start_drawing(self) -> None:
        if not self._is_drawing:
            self._is_drawing = True
            self.drawing_started.emit()

    def event(self, event: QEvent) -> bool:
        kind = event.type()

        # with a frame: a window has a grid surface only for a picture
        if kind in _JOIN_EVENTS and self._texture:
            self._join()

        if kind in _PLACE_EVENTS and self._grid is not None:
            self._grid.surfaces_moved()

        return super().event(event)

    # Python's calls only: the surface itself is never painted anew for a
    # frame, only what the grid surface draws under it.
    def update(self, *_args) -> None:
        if self._grid is not None and not sip.isdeleted(self._grid):
            self._grid.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)

        if GLVideoSurface._grabs:
            self._paint_picture(painter)
            return

        # see-through, as under a QOpenGLWidget, whatever is under it
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(event.rect(), Qt.GlobalColor.transparent)

    def _paint_picture(self, painter: QPainter) -> None:
        placement = self.placement() if self.has_frame() else None
        image = self.frame_image() if placement is not None else None
        if image is None:
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
            return

        for bar in self._bars(placement.target):
            painter.fillRect(bar, Qt.GlobalColor.black)

        # the picture as shown, flips done
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(QRectF(*placement.target), image, QRectF(*placement.source))

    def frame_size(self) -> tuple[int, int]:
        if not self.has_frame():
            return 0, 0
        return self._frame_w, self._frame_h

    def present_texture(self, texture: int, width: int, height: int) -> None:
        if self._kept.texture != texture:
            self._kept.let_go()

        self._texture = texture
        self._frame_w, self._frame_h = width, height
        self._join()
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

        if not self.has_frame() or self._grid is None:
            return None

        return self._grid.frame_image(self._texture, self._frame_w, self._frame_h)

    def _painted_flip(self) -> tuple[bool, bool] | None:
        return None

    def blit(
        self,
        blitter: QOpenGLTextureBlitter,
        placement: ViewPlacement,
        origin: QPoint,
        ratio: float,
        viewport: QRect,
    ) -> None:
        """Its picture, by the grid surface, this surface at origin in it."""

        x, y, width, height = placement.target
        target = QOpenGLTextureBlitter.targetTransform(
            QRectF(*native_rect(origin.x() + x, origin.y() + y, width, height, ratio)),
            viewport,
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
            QOpenGLTextureBlitter.Origin.OriginTopLeft,
        )

        blitter.blit(self._texture, target, source)
