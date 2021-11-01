import logging
import os
import platform
import stat
from multiprocessing import connection
from threading import Thread

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer import params_env

if platform.system() == "Windows":
    S_NAME, S_TYPE = r"\\.\pipe\gridplayer-fileopen", "AF_PIPE"
elif params_env.IS_FLATPAK:
    S_NAME, S_TYPE = (
        f"{os.environ['XDG_RUNTIME_DIR']}/app/{os.environ['FLATPAK_ID']}"
        f"/gridplayer/gridplayer-fileopen.socket",
        "AF_UNIX",
    )
elif os.getenv("XDG_RUNTIME_DIR"):
    S_NAME, S_TYPE = (
        f"{os.environ['XDG_RUNTIME_DIR']}/gridplayer/gridplayer-fileopen.socket",
        "AF_UNIX",
    )

if platform.system() == "Darwin":
    from Foundation import NSWorkspace

    from gridplayer.version import __app_id__

    def is_the_only_instance():
        instances_count = sum(
            app.bundleIdentifier() == __app_id__
            for app in NSWorkspace.sharedWorkspace().runningApplications()
        )

        return instances_count == 1


else:

    def is_the_only_instance():
        """Dummy"""


logger = logging.getLogger(__name__)


def _init_listener():
    try:
        return connection.Listener(S_NAME, S_TYPE)
    except OSError:
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

    def cleanup(self):
        if not self._thread.is_alive():
            return

        logger.debug("Terminating instance socket")

        _send_data(None)
        self._thread.join()

    def _listen(self):
        if platform.system() != "Windows" and _is_socket_working():
            return

        listener = _init_listener()

        logger.debug(f"Instance socket listening at {S_NAME}")

        self._listening_loop(listener)

        listener.close()

    def _listening_loop(self, listener):
        while True:
            client = listener.accept()

            with client:
                try:
                    input_data = client.recv()
                except EOFError:
                    continue

            if input_data is None:
                break

            self._handle_input_data(input_data)

    def _handle_input_data(self, input_data):
        if input_data == "ping":
            logger.debug("Received ping from another instance")

        if isinstance(input_data, list):
            self.open_files.emit(input_data)


def _send_data(output_data):
    client = connection.Client(S_NAME, S_TYPE)

    client.send(output_data)


def _is_socket_working():
    os.makedirs(os.path.dirname(S_NAME), exist_ok=True)

    if os.path.exists(S_NAME):
        if not stat.S_ISSOCK(os.stat(S_NAME).st_mode):
            os.unlink(S_NAME)
            return False

        try:
            _send_data("ping")
        except ConnectionRefusedError:
            os.unlink(S_NAME)
            return False

        logger.info("Socket already exists and responding")
        return True

    return False


def is_delegated_to_primary(argv):
    input_files = filter(os.path.isfile, argv[1:])

    file_paths = [os.path.abspath(f) for f in input_files]

    try:
        _send_data(file_paths)
    except (FileNotFoundError, ConnectionRefusedError):
        return False

    return True
