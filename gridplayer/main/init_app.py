import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from gridplayer.main.init_app_env import gl_line_fix, pick_qt_platform, set_gl_alpha
from gridplayer.main.init_icons import init_icon
from gridplayer.main.init_resources import init_resources
from gridplayer.main.init_translator import init_translator
from gridplayer.params import env
from gridplayer.params.static import FONT_SIZE_MAIN, GLLineFix
from gridplayer.params.theme import (
    apply_theme,
    create_fusion_style,
    on_system_theme_changed,
)
from gridplayer.utils.darkmode import watch_system_theme
from gridplayer.utils.mouse_windows import keep_held_buttons
from gridplayer.utils.wayland import follow_desktop_cursor


def settle_gl_line_fix() -> None:
    """On Auto, the black line fix stays for NVIDIA only: the windows made
    from here on have no alpha channel otherwise. See init_app_env.gl_line_fix.

    Asked only now: a GL context made before the app is, NVIDIA's driver shows
    the app's windows another way, black line and all.
    """

    if not (env.MPV_GL_OUTPUT and env.IS_WINDOWS):
        return

    if gl_line_fix() != GLLineFix.AUTO:
        return

    from gridplayer.mpv_player.gl_context import wgl_vendor

    vendor = wgl_vendor()
    is_nvidia = vendor is not None and "NVIDIA" in vendor.upper()
    logging.getLogger(__name__).info(
        "OpenGL by %s, black line fix %s", vendor, "on" if is_nvidia else "off"
    )

    if not is_nvidia:
        set_gl_alpha(0)


def init_app():
    pick_qt_platform()

    if env.QT_PLATFORM:
        app = QApplication([*sys.argv, "-platform", env.QT_PLATFORM])
    else:
        app = QApplication(sys.argv)

    settle_gl_line_fix()

    follow_desktop_cursor()
    keep_held_buttons(app)

    init_resources()

    app.setStyle(create_fusion_style())

    app.setAttribute(Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton)
    app.styleHints().setShowShortcutsInContextMenus(True)

    apply_theme(app)
    app.paletteChanged.connect(lambda: on_system_theme_changed(app))
    watch_system_theme(lambda: on_system_theme_changed(app), app)

    init_icon(app)

    app.setFont(QFont("Hack", FONT_SIZE_MAIN))

    init_translator(app)

    return app
