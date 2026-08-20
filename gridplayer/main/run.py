import sys

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.main.init_app import init_app
from gridplayer.main.init_icons import init_icon
from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.utils.libvlc import init_vlc
from gridplayer.utils.qt import translate


def run_app():
    app = init_app()

    try:
        vlc_version, vlc_python_version = init_vlc()
    except FileNotFoundError:
        QCustomMessageBox.critical(
            None,
            translate("Dialog", "Error"),
            translate(
                "Error",
                "<p>VLC player is required!</p><p>Please visit"
                ' <a href="https://www.videolan.org/vlc/">VLC official site</a>'
                " for instructions on how to install it.</p>",
            ),
        )
        return 1

    env.VLC_VERSION = vlc_version
    env.VLC_PYTHON_VERSION = vlc_python_version

    # Need to postpone import parts that depend on vlc
    # because python-vlc loads VLC DLL on import
    # and we need to set environment vars before that
    from gridplayer.player import Player

    player = Player()
    if Settings().get("player/start_fullscreen"):
        player.showFullScreen()
    elif Settings().get("player/start_maximized"):
        player.showMaximized()
    else:
        player.show()

    # force load main app icon for Windows 11
    if env.IS_WINDOWS:
        init_icon(app)

    app.installEventFilter(player)

    if sys.argv[1:]:
        player.process_arguments(sys.argv[1:])

    return app.exec_()
