import argparse
import os
import sys

from gridplayer.params import env
from gridplayer.utils.app_dir import ENV_USER_DATA_DIR
from gridplayer.version import __app_name__, __version__

QT_PLATFORMS = ("auto", "xcb", "wayland")


def init_cli_args(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description="Play videos side-by-side",
        epilog="FILE and URL arguments open media files, .gpls playlists,"
        " or streaming URLs on startup.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE|URL",
        help="media files, .gpls playlists, or streaming URLs to open on startup",
    )
    parser.add_argument(
        "--user-data-dir",
        metavar="PATH",
        default="",
        help="store settings and log files in PATH instead of the default"
        f" location (also settable via {ENV_USER_DATA_DIR} environment variable)",
    )
    if env.IS_LINUX:
        parser.add_argument(
            "--platform",
            choices=QT_PLATFORMS,
            default="auto",
            help="display server to run on: auto picks xcb (X11 or Xwayland)"
            " when there is one, wayland otherwise; hardware video needs xcb",
        )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {__version__}",
    )

    args = parser.parse_intermixed_args(argv)

    sys.argv[:] = [sys.argv[0], *args.files]

    if args.user_data_dir.strip():
        os.environ[ENV_USER_DATA_DIR] = args.user_data_dir.strip()

    if getattr(args, "platform", "auto") != "auto":
        env.QT_PLATFORM = args.platform
