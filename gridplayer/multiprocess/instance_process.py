import logging
import secrets
import traceback
from multiprocessing import Value
from multiprocessing.context import Process

from gridplayer.multiprocess.command_loop import CommandLoop
from gridplayer.params_static import PLAYER_ID_LENGTH
from gridplayer.utils.log_config import child_process_config


class InstanceProcess(CommandLoop):
    def __init__(self, players_per_instance, pm_callback_pipe, **kwargs):
        super().__init__(**kwargs)

        self.id = secrets.token_hex(PLAYER_ID_LENGTH)

        self.process = Process(
            target=self.run,
            daemon=True,
            name="{0}_{1}".format(self.__class__.__name__, self.id),
        )

        self.players_per_instance = players_per_instance
        self.pm_callback_pipe = pm_callback_pipe

        # shared data outside
        self._players_shared_data = {}

        # shared data multiprocess
        self.player_count = Value("i", 0)
        self.is_dead = Value("i", 0)

        self._log_queue = None
        self._log_level = None

        # process variables
        self._players = {}

    # outside
    def request_new_player(self, init_data, pipe):
        with self.player_count.get_lock():
            self.player_count.value += 1

        player_id = secrets.token_hex(PLAYER_ID_LENGTH)

        self.init_player_shared_data(player_id)

        self.cmd_send_self("new_player", player_id, init_data, pipe)

        return player_id

    # outside
    def get_player_shared_data(self, player_id):
        return self._players_shared_data[player_id]

    # outside
    def cleanup_player_shared_data(self, player_id):
        self._players_shared_data.pop(player_id, None)

    # outside
    def setup_log_queue(self, log_queue, log_level):
        self._log_queue = log_queue
        self._log_level = log_level

    # process
    def run(self):
        if self._log_queue is not None:
            child_process_config(self._log_queue, self._log_level)

        try:
            self.process_body()
        except Exception:
            traceback_txt = traceback.format_exc()

            logger = logging.getLogger("InstanceProcess")
            logger.critical(traceback_txt)

            self.crash(traceback_txt)
        finally:
            if self._log_queue is not None:
                self._log_queue.close()

    # process
    def process_body(self):
        logger = logging.getLogger("InstanceProcess")

        logger.debug("Starting process...")

        self.init_instance()
        self.cmd_loop_run()

        logger.debug("Terminating process...")

    # process
    def crash(self, traceback_txt):
        self.pm_callback_pipe.send(("crash_all", (traceback_txt,)))

    # outside
    def request_set_log_level(self, log_level):
        self.cmd_send_self("set_log_level", log_level)

    # process
    def set_log_level(self, log_level):  # noqa: WPS615
        logging.root.setLevel(log_level)

    # process
    def cleanup(self):
        self.cleanup_instance()
        self.cmd_loop_terminate()

        self.pm_callback_pipe.send(("cleanup_instance", (self.id,)))

    # process
    def release_player(self, player_id):
        self._players[player_id].cleanup_final()

        with self.player_count.get_lock():
            self.player_count.value -= 1

            self.release_player_shared_data(player_id)

            if self.player_count.value == 0:
                with self.is_dead.get_lock():
                    self.is_dead.value = 1
                self.cleanup()

    # process
    def init_instance(self):
        """Instance initialization"""

    # process
    def cleanup_instance(self):
        """Instance cleanup"""

    # process
    def new_player(self, player_id, init_data, pipe):
        """Request new player"""

    # process
    def init_player_shared_data(self, player_id):
        """Initialize shared data for player instance"""

    # process
    def release_player_shared_data(self, player_id):
        """Release shared data for player instance"""
