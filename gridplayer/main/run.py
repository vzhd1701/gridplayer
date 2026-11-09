import sys
from contextlib import suppress

from PyQt5.QtCore import QTimer

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.main.init_app import init_app
from gridplayer.main.init_icons import init_icon
from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.utils.libmpv import init_mpv
from gridplayer.utils.libvlc import init_vlc
from gridplayer.utils.qt import translate
from gridplayer.widgets.tooltip import install_tooltips


def run_app():
    app = init_app()

    # either will do: mpv is the driver being moved to, VLC still works
    with suppress(FileNotFoundError):
        env.MPV_VERSION = init_mpv()

    if env.IS_PYINSTALLER:
        # a package brings its own libmpv and has no use for a VLC it did
        # not ship, whichever one happens to be installed
        env.IS_VLC_MISSING = True
    else:
        try:
            env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
        except FileNotFoundError:
            env.IS_VLC_MISSING = True

    if env.MPV_VERSION is None and env.IS_VLC_MISSING:
        QCustomMessageBox.critical(
            None,
            "GridPlayer",
            translate("Error", "libmpv was not found"),
            info=translate(
                "Error",
                "GridPlayer plays videos with libmpv, and could not load it.",
            ),
        )
        return 1

    # Need to postpone import parts that depend on vlc
    # because python-vlc loads VLC DLL on import
    # and we need to set environment vars before that
    from gridplayer.player import Player

    player = Player()
    app.installEventFilter(player)

    # after the player's, so it sees the clicks and keys the player takes
    install_tooltips(app)

    if sys.argv[1:]:
        player.process_arguments(sys.argv[1:])

    if Settings().get("player/start_fullscreen"):
        player.showFullScreen()
    elif Settings().get("player/start_maximized"):
        player.showMaximized()
    else:
        player.show()

    # force load main app icon for Windows 11, sometimes it doesn't load if called before show
    if env.IS_WINDOWS:
        init_icon(app)

    # once the loop runs, and not over a file opened by then, such as one
    # macOS sends as an event rather than an argument
    if not sys.argv[1:]:
        QTimer.singleShot(0, player.restore_last_playlist)

    return app.exec_()
