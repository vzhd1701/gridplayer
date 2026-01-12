import logging
import os
import stat
from multiprocessing import connection
from pathlib import Path
from threading import Thread

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.params import env

if env.IS_WINDOWS:
    S_NAME, S_TYPE = r"\\.\pipe\gridplayer-fileopen", "AF_PIPE"
elif env.IS_FLATPAK:
    S_NAME, S_TYPE = (
        str(env.FLATPAK_RUNTIME_DIR / "gridplayer-fileopen.socket"),
        "AF_UNIX",
    )
elif os.getenv("XDG_RUNTIME_DIR"):
    S_NAME, S_TYPE = (
        f"{os.environ['XDG_RUNTIME_DIR']}/gridplayer/gridplayer-fileopen.socket",
        "AF_UNIX",
    )

if env.IS_MACOS:
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


LISTENER: connection.Listener | None = None


def _init_listener() -> connection.Listener | None:
    try:
        return connection.Listener(S_NAME, S_TYPE)
    except OSError:
        logging.getLogger(__name__).debug(
            "Couldn't start single instance listener,"
            " probably other process is using it"
        )

    return None


class Listener(QObject):
    open_files = pyqtSignal(list)

    def __init__(self):
        super().__init__()

        self._log = logging.getLogger(self.__class__.__name__)

        self._thread = None

    def start(self):
        if LISTENER is None:
            self._log.warning("Couldn't start single instance listener")
            return

        self._thread = Thread(target=self._listen, args=(LISTENER,), daemon=True)
        self._thread.start()

    def cleanup(self):
        if self._thread is None or not self._thread.is_alive():
            return

        self._log.debug("Terminating instance socket")

        _send_data(None)
        self._thread.join()

    def _listen(self, listener):
        self._log.debug(f"Instance socket listening at {S_NAME}")

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
            self._log.debug("Received ping from another instance")

        if isinstance(input_data, list) and input_data:
            self.open_files.emit(input_data)


def _send_data(output_data):
    logging.getLogger(__name__).debug(
        f"Sending data to running instance: {output_data}"
    )

    client = connection.Client(S_NAME, S_TYPE)

    client.send(output_data)


def _is_socket_working():
    s_path = Path(S_NAME)
    s_path.parent.mkdir(parents=True, exist_ok=True)

    if s_path.exists():
        if not stat.S_ISSOCK(s_path.stat().st_mode):
            s_path.unlink()
            return False

        try:
            _send_data("ping")
        except ConnectionRefusedError:
            s_path.unlink()
            return False

        logging.getLogger(__name__).debug("Socket already exists and responding")
        return True

    return False


def is_other_instance_running():
    global LISTENER

    if env.IS_LINUX and _is_socket_working():
        return True

    LISTENER = _init_listener()

    return LISTENER is None


def is_delegated_to_primary(argv):
    if not is_other_instance_running():
        return False

    try:
        _send_data(argv[1:])
    except (FileNotFoundError, ConnectionRefusedError):
        return False

    return True
