import platform
import sys
from multiprocessing import freeze_support

from gridplayer.main.init_app import setup_app_env
from gridplayer.main.init_utils import exit_if_delegated, init_log
from gridplayer.main.run import run_app
from gridplayer.utils.excepthook import excepthook
from gridplayer.utils.log import log_environment


def main():
    freeze_support()

    setup_app_env()

    init_log()

    sys.excepthook = excepthook

    # MacOS has OpenFile events
    if platform.system() != "Darwin":
        exit_if_delegated()

    log_environment()

    ret = run_app()

    sys.exit(ret)


if __name__ == "__main__":
    main()
