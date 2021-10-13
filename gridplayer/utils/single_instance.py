import logging
import multiprocessing.connection
import os
import platform
import stat
from threading import Thread

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer import params_env

if platform.system() == "Windows":
    S_NAME, S_TYPE = r"\\.\pipe\gridplayer-fileopen", "AF_PIPE"
elif platform.system() == "Darwin":
    # Not used actually
    S_NAME, S_TYPE = ("/tmp/gridplayer/gridplayer-fileopen.socket", "AF_UNIX")
elif params_env.IS_FLATPAK:
    S_NAME, S_TYPE = (
        f"{os.environ['XDG_RUNTIME_DIR']}/app/{os.environ['FLATPAK_ID']}"
        f"/gridplayer/gridplayer-fileopen.socket",
        "AF_UNIX",
    )
else:
    S_NAME, S_TYPE = (
        f"{os.environ['XDG_RUNTIME_DIR']}/gridplayer/gridplayer-fileopen.socket",
        "AF_UNIX",
    )

logger = logging.getLogger(__name__)


def _init_listener():
    if platform.system() != "Windows" and _is_socket_working():
        return

    try:
        return multiprocessing.connection.Listener(S_NAME, S_TYPE)
    except (PermissionError, OSError):
        logger.warning(
            "Couldn't start single instance listener,"
            " probably other process is using it"
        )


class Listener(QObject):
    open_files = pyqtSignal(list)

    def __init__(self):
        super().__init__()

        self._thread = None

    def start(self):
        self._thread = Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        listener = _init_listener()

        if listener is None:
            return

        logger.debug(f"Instance socket listening at {S_NAME}")

        while True:
            client = listener.accept()

            with client:
                try:
                    data = client.recv()
                except EOFError:
                    continue

            if data == "ping":
                logger.debug("Received ping from another instance")

            if data is None:
                break

            if isinstance(data, list):
                self.open_files.emit(data)

        listener.close()

    def cleanup(self):
        if not self._thread.is_alive():
            return

        logger.debug(f"Terminating instance socket")

        _send_data(None)
        self._thread.join()


def _send_data(data):
    client = multiprocessing.connection.Client(S_NAME, S_TYPE)

    client.send(data)


def _is_socket_working():
    os.makedirs(os.path.dirname(S_NAME), exist_ok=True)

    if os.path.exists(S_NAME):
        if not stat.S_ISSOCK(os.stat(S_NAME).st_mode):
            os.unlink(S_NAME)
            return False

        try:
            _send_data("ping")
            logger.info("Socket already exists and responding")
            return True
        except ConnectionRefusedError:
            os.unlink(S_NAME)

    return False


def delegate_if_not_primary(argv):
    files = [os.path.abspath(f) for f in argv[1:] if os.path.isfile(f)]

    try:
        _send_data(files)
    except (FileNotFoundError, ConnectionRefusedError):
        return False

    return True
