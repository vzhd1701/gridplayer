import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import sys
from multiprocessing import freeze_support

from gridplayer.main.init_app_env import init_app_env
from gridplayer.main.init_cli import init_cli_args
from gridplayer.main.init_log import init_log
from gridplayer.main.run import run_app
from gridplayer.params import env
from gridplayer.settings import Settings
from gridplayer.utils.excepthook import excepthook
from gridplayer.utils.log import log_environment
from gridplayer.utils.malloc_arenas import limit_malloc_arenas
from gridplayer.utils.single_instance import is_delegated_to_primary


def main():
    # before any thread
    if env.IS_LINUX:
        limit_malloc_arenas()

    freeze_support()

    init_cli_args()

    init_app_env()

    init_log()

    sys.excepthook = excepthook

    # MacOS has OpenFile events
    if not env.IS_MACOS:
        exit_if_delegated()

    log_environment()

    ret = run_app()

    sys.exit(ret)


def exit_if_delegated():
    if Settings().get("player/one_instance") and is_delegated_to_primary(sys.argv):
        sys.exit(0)


if __name__ == "__main__":
    main()
