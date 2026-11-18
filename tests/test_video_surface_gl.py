"""MPV's frames drawn by GL: the texture on show stays while its video goes, and
is let go of once another takes its place or the surface goes, drawn or not; a
surface draws once its window's grid surface is up, which draws the surfaces
lowest first, each cut to its cell. Nothing here draws: no GL needed."""

import ctypes
import gc
import weakref
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from gridplayer.mpv_player import gl_context
from gridplayer.mpv_player.renderer import RenderedVideo
from gridplayer.params import env
from gridplayer.params.static import VideoTransform, ViewParams
from gridplayer.widgets import video_surface_gl
from gridplayer.widgets.video_frame_mpv import MpvGLVideoSurface


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _grid_never_shown(monkeypatch):
    # nothing drawn: a grid surface made with no context started
    monkeypatch.setattr(video_surface_gl.GLGridSurface, "show", lambda _self: None)


def _surface(texture=5, size=(160, 90), deleted=None):
    surface = MpvGLVideoSurface(
        delete_textures=None if deleted is None else deleted.extend
    )
    surface.resize(320, 180)
    surface.set_view(ViewParams(), VideoTransform.NONE, size)
    surface.present_texture(texture, *size)
    return surface


def _shown_by(texture) -> RenderedVideo:
    video = RenderedVideo(MagicMock())
    video.latest().texture = texture
    return video


def test_a_frame_on_show_is_placed_as_painted_ones_are():
    surface = _surface()

    assert surface.has_frame()
    assert surface.frame_size() == (160, 90)
    assert surface.placement().target == (0, 0, 320, 180)


def test_the_frame_on_show_is_kept_as_its_video_goes():
    surface = _surface(texture=5)
    video = _shown_by(5)

    surface.keep_frame(video)

    assert video.latest().texture == 0
    assert surface.has_frame()


def test_a_texture_not_on_show_is_left_for_the_renderer():
    surface = _surface(texture=5)
    video = _shown_by(6)

    surface.keep_frame(video)

    assert video.latest().texture == 6


def test_a_kept_texture_goes_once_another_is_on_show():
    deleted = []
    surface = _surface(texture=5, deleted=deleted)
    surface.keep_frame(_shown_by(5))

    surface.present_texture(5, 160, 90)
    assert deleted == []

    surface.present_texture(7, 160, 90)
    assert deleted == [5]

    surface.present_texture(8, 160, 90)
    assert deleted == [5]


def test_a_kept_texture_goes_with_the_surface_never_shown():
    deleted = []
    surface = _surface(texture=5, deleted=deleted)
    surface.keep_frame(_shown_by(5))

    sip.delete(surface)

    assert deleted == [5]


def test_a_failed_video_s_frame_is_not_shown_on():
    surface = _surface(texture=5)

    surface.drop_frame()

    assert not surface.has_frame()


def test_a_kept_frame_stays_as_a_later_video_fails():
    surface = _surface(texture=5)
    surface.keep_frame(_shown_by(5))

    surface.drop_frame()

    assert surface.has_frame()


def test_a_surface_out_of_any_window_doesn_t_draw():
    surface = _surface()

    assert not surface.is_drawing()


def test_a_surface_draws_once_its_window_s_grid_surface_is_up():
    window, surface = _in_window()
    started = []
    surface.drawing_started.connect(lambda: started.append(True))

    surface.present_texture(6, 160, 90)
    grid = video_surface_gl.GLGridSurface.of(window)

    assert not surface.is_drawing()

    grid.ready.emit()

    assert surface.is_drawing()
    assert started == [True]
    assert video_surface_gl.GLGridSurface.of(window) is grid


def test_surfaces_are_drawn_lowest_first_and_cut_to_their_cell():
    window = QWidget()
    window.resize(400, 300)
    low, high = QWidget(window), QWidget(window)
    low.setGeometry(0, 0, 200, 150)
    high.setGeometry(100, 50, 200, 150)
    in_low = QWidget(low)
    # past the cell's right edge
    in_low.setGeometry(150, 10, 100, 50)
    in_high = QWidget(high)
    in_high.setGeometry(0, 0, 200, 150)
    window.show()

    placed = video_surface_gl.placed_surfaces([in_high, in_low], window)

    assert [surface for surface, _, _ in placed] == [in_low, in_high]
    assert placed[0][1] == QPoint(150, 10)
    assert placed[0][2] == QRect(150, 10, 50, 50)
    assert placed[1][2] == QRect(100, 50, 200, 150)

    low.raise_()
    placed = video_surface_gl.placed_surfaces([in_high, in_low], window)

    assert [surface for surface, _, _ in placed] == [in_high, in_low]

    high.hide()
    placed = video_surface_gl.placed_surfaces([in_high, in_low], window)

    assert [surface for surface, _, _ in placed] == [in_low]
    window.close()


def _in_window():
    window = QWidget()
    window.resize(320, 180)
    window.winId()
    surface = _surface()
    surface.setParent(window)
    return window, surface


class _Context(QObject):
    aboutToBeDestroyed = pyqtSignal()

    def versionFunctions(self, _profile=None):
        return None

    def getProcAddress(self, _name):
        return 0


def test_the_blitter_lasts_as_long_as_its_context(monkeypatch):
    """Qt frees its vertex array as the context goes, on a hidden window made
    for it, while Python can run and collect: the surface already going, only
    the context can hold on to it."""

    monkeypatch.setattr(video_surface_gl, "QOpenGLTextureBlitter", _Blitter)
    monkeypatch.setattr(video_surface_gl, "set_up_gl_window", lambda _w: None)
    context = _Context()
    window = QWidget()
    grid = video_surface_gl.GLGridSurface(window)
    monkeypatch.setattr(grid, "context", lambda: context)

    grid.initializeGL()
    blitter = weakref.ref(grid._blitter)

    grid._blitter = None
    gc.collect()
    assert blitter() is not None

    sip.delete(context)
    gc.collect()
    assert blitter() is None

    # its grid surface, set up on a context that is gone, isn't left for a
    # later test's events to reach
    sip.delete(window)


class _Blitter:
    def create(self):
        pass


def _started_grid(monkeypatch):
    monkeypatch.setattr(video_surface_gl, "QOpenGLTextureBlitter", _Blitter)
    monkeypatch.setattr(video_surface_gl, "set_up_gl_window", lambda _w: None)
    context = _Context()
    window = QWidget()
    grid = video_surface_gl.GLGridSurface(window)
    monkeypatch.setattr(grid, "context", lambda: context)
    grid.initializeGL()
    return window, grid, context


def test_a_started_grid_says_it_is_ready_once_qt_is_done(monkeypatch):
    window, grid, context = _started_grid(monkeypatch)
    said = []
    grid.ready.connect(lambda: said.append(True))

    assert said == []
    QApplication.processEvents()

    assert said == [True]
    sip.delete(window)
    sip.delete(context)


def test_a_grid_gone_before_it_is_ready_says_nothing(monkeypatch):
    window, _grid, context = _started_grid(monkeypatch)

    sip.delete(window)
    # its ready signal no longer there to be emitted: this crashed
    QApplication.processEvents()

    sip.delete(context)


def test_a_grab_through_any_surface_class_paints_the_picture():
    with MpvGLVideoSurface.grabbing():
        assert video_surface_gl.GLVideoSurface._grabs == 1

    assert video_surface_gl.GLVideoSurface._grabs == 0


def test_a_surface_put_in_another_window_leaves_the_old_one_s_grid():
    window, surface = _in_window()
    surface.present_texture(6, 160, 90)
    grid = video_surface_gl.GLGridSurface.of(window)
    other = QWidget()
    other.winId()

    surface.setParent(other)
    grid._place_surfaces()

    assert surface._grid is None
    assert surface not in grid._surfaces
    surface._join()
    assert surface._grid is video_surface_gl.GLGridSurface.of(other)

    sip.delete(window)
    sip.delete(other)


class _OpenGLESContext:
    """Qt's context on OpenGL ES, which PyQt5 has no functions for: its calls
    are Python ones here."""

    def __init__(self):
        self.calls = []
        self._kept = {}

    def versionFunctions(self, _profile=None):
        return None

    def getProcAddress(self, name):
        name = bytes(name).decode()
        argtypes = gl_context._QT_GL_CALLS[name]
        proto = ctypes.WINFUNCTYPE if env.IS_WINDOWS else ctypes.CFUNCTYPE

        def call(*args):
            if name == "glDeleteTextures":
                count, textures = args
                args = (count, [textures[i] for i in range(count)])
            self.calls.append((name, *args))

        function = self._kept[name] = proto(None, *argtypes)(call)

        return ctypes.cast(function, ctypes.c_void_p).value


def test_opengl_es_is_drawn_with_calls_of_its_own():
    context = _OpenGLESContext()

    gl = gl_context.qt_gl_functions(context)
    gl.glViewport(0, 0, 640, 360)
    gl.glClear(0x4000)
    gl.glDeleteTextures(2, [7, 9])

    assert context.calls == [
        ("glViewport", 0, 0, 640, 360),
        ("glClear", 0x4000),
        ("glDeleteTextures", 2, [7, 9]),
    ]


class _EGLWithOnlyES:
    """A driver that takes desktop OpenGL and has no config for it."""

    def __init__(self):
        self.apis = []

    def eglGetPlatformDisplay(self, *_args):
        return 1

    def eglInitialize(self, *_args):
        return 1

    def eglBindAPI(self, api):
        self.apis.append(api)
        return 1

    def eglQueryString(self, *_args):
        return b"EGL_KHR_surfaceless_context"

    def eglChooseConfig(self, _display, attrs, _config, _size, count):
        is_es = attrs[3] == gl_context.EGLContext._OPENGL_ES2_BIT
        count._obj.value = 1 if is_es else 0
        return 1

    def eglCreateContext(self, *_args):
        return 5

    def eglMakeCurrent(self, *_args):
        return 1

    def eglGetError(self):
        return 0x3000


def test_opengl_es_where_desktop_opengl_is_taken_but_has_no_config():
    egl = _EGLWithOnlyES()
    context = object.__new__(gl_context.EGLContext)
    context._platform = "offscreen"
    context._egl = egl
    context._display = context._surface = context._context = None
    context._share_context = context._native_display = None
    context.is_gles = False

    context._open(None)

    assert context.is_gles
    assert egl.apis == [
        gl_context.EGLContext._OPENGL_API,
        gl_context.EGLContext._OPENGL_ES_API,
    ]
    assert context._context == 5


def test_textures_with_no_gl_calls_to_be_had_are_given_up_on_once(monkeypatch):
    looked_up = []
    monkeypatch.setattr(
        gl_context, "qt_gl_functions", lambda context: looked_up.append(context)
    )
    group = object.__new__(gl_context.QtShareGroup)
    group._context = MagicMock()
    group._surface = None
    group._gl = None

    group.delete_textures([1])
    group.delete_textures([2])

    assert len(looked_up) == 1
