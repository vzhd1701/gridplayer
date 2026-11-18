import ctypes
import multiprocessing
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QSurfaceFormat
from PyQt6.QtWidgets import QApplication

from gridplayer.mpv_player.gl_context import macos_gl_format
from gridplayer.params import env
from gridplayer.params.static import GLLineFix
from gridplayer.version import (
    __app_id__,
    __app_name__,
    __author_name__,
    __display_name__,
    __version__,
)


def is_mpv_gl_output_wanted() -> bool:
    """Whether Qt is to be set up for MPV's frames drawn by GL, which it can
    only be before it starts."""

    from gridplayer.settings import Settings
    from gridplayer.utils.video_driver import is_mpv_gl_output

    settings = Settings()

    return is_mpv_gl_output(
        settings.get("player/mpv_output"), settings.get("player/video_driver")
    )


def pick_qt_platform() -> None:
    """Linux: X11 or Wayland, by the settings, unless --platform has said.

    Not in init_app_env: asking the compositor takes a round trip, which a
    launch that only hands its files to the app already running can do
    without. Before the log says which, and before the QApplication is made.
    """

    if env.QT_PLATFORM is not None:
        return

    from gridplayer.settings import Settings
    from gridplayer.utils.video_driver import qt_platform_for

    settings = Settings()

    env.QT_PLATFORM = qt_platform_for(
        settings.get("player/display_server"),
        settings.get("player/video_driver"),
        settings.get("player/mpv_output"),
    )
    env.IS_QT_PLATFORM_PICKED = env.QT_PLATFORM is not None


def gl_line_fix():
    """Windows, GL output: whether windows get an alpha channel. Some drivers,
    NVIDIA's, pad a window's height to a multiple of 4 rows at some widths and
    squash the padding into it, black, unless it has one. It costs CPU.

    On Auto it's set up as for On, and settled once the app is up: see
    init_app.settle_gl_line_fix."""

    from gridplayer.settings import Settings

    return Settings().get("internal/gl_line_fix")


def set_gl_alpha(bits: int) -> None:
    surface_format = QSurfaceFormat.defaultFormat()
    surface_format.setAlphaBufferSize(bits)
    QSurfaceFormat.setDefaultFormat(surface_format)


def init_app_env_id():
    QApplication.setApplicationName(__app_name__)
    QApplication.setApplicationDisplayName(__display_name__)
    QApplication.setOrganizationName(__author_name__)
    QApplication.setApplicationVersion(__version__)


def start_resource_tracker() -> None:
    """macOS: multiprocessing's resource tracker, a process forked, started
    before the app is. Started later, with the process manager, the fork can
    hang for good: macOS 15 loads a framework on a thread of its own as the
    app comes up, holding dyld's lock while it waits for the Objective-C
    runtime's, and fork() takes the two the other way round."""

    from multiprocessing.resource_tracker import ensure_running

    ensure_running()


def set_app_user_model_id(app_id: str) -> None:
    """Windows: the taskbar groups the app's windows, and finds its icon and
    jump list, by this ID rather than by python.exe's."""

    shell32 = ctypes.WinDLL("shell32")
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def init_app_env():
    # first: where the settings are kept goes by these
    init_app_env_id()

    env.MPV_GL_OUTPUT = is_mpv_gl_output_wanted()

    if env.MPV_GL_OUTPUT:
        # MPV's frames drawn in the window: the render thread's textures go to
        # every QOpenGLWidget through Qt's one share group
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        if env.IS_WINDOWS:
            # not ANGLE, which has no NVDEC and can't share with WGL
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)
            # before Qt makes its first context, which every other shares with
            if gl_line_fix() != GLLineFix.OFF:
                set_gl_alpha(8)
        if env.IS_MACOS:
            # OpenGL 3.2 Core, as the render thread's context is: contexts of
            # two profiles can't share
            QSurfaceFormat.setDefaultFormat(macos_gl_format())
        if env.IS_LINUX:
            # EGL, as the render thread's context is
            os.environ.setdefault("QT_XCB_GL_INTEGRATION", "xcb_egl")
            # VLC's processes forked from a GL-drawing window break its GL:
            # they start from a clean process instead
            multiprocessing.set_start_method("forkserver", force=True)

    if env.IS_LINUX and not env.MPV_GL_OUTPUT:
        # Hardware video is drawn by VLC into an X11 window, not by Qt OpenGL.
        # If the xcb plugin loads libGL here, forked decoder processes inherit
        # a broken GLdispatch and abort on the second Hardware process:
        #   DispatchCurrentUnref: Assertion `dispatch->currentThreads >= 0'
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")

    if env.IS_WINDOWS:
        set_app_user_model_id(__app_id__)

    if env.IS_MACOS:
        start_resource_tracker()

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
