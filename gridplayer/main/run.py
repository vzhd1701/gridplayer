import sys

from gridplayer import params_env
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.main.init_app import init_app
from gridplayer.utils.libvlc import init_vlc
from gridplayer.utils.misc import tr


def run_app():
    app = init_app()

    try:
        vlc_version, vlc_python_version = init_vlc()
    except FileNotFoundError:
        QCustomMessageBox.critical(
            None,
            tr("Error"),
            tr(
                "<p>VLC player is required!</p><p>Please visit"
                ' <a href="https://www.videolan.org/vlc/">VLC official site</a>'
                " for instructions on how to install it.</p>",
            ),
        )
        return 1

    params_env.VLC_VERSION = vlc_version
    params_env.VLC_PYTHON_VERSION = vlc_python_version

    # Need to postpone import parts that depend on vlc
    # because python-vlc loads VLC DLL on import
    # and we need to set environment vars before that
    from gridplayer.player import Player  # noqa: WPS433

    player = Player()
    player.show()

    app.installEventFilter(player)

    if sys.argv[1:]:
        player.process_arguments(sys.argv[1:])

    return app.exec_()
