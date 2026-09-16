import logging
import os
import secrets
import traceback
from abc import ABC, abstractmethod
from multiprocessing import Value, parent_process
from multiprocessing.context import Process
from threading import Thread

from gridplayer.main.init_app_env import init_app_env_id
from gridplayer.multiprocess.command_loop import CommandLoop
from gridplayer.multiprocess.parent_death_signal import arm_parent_death_signal
from gridplayer.params.static import PLAYER_ID_LENGTH
from gridplayer.utils.log_config import child_process_config

ORPHANED_EXIT_CODE = 1


class InstanceProcess(CommandLoop, ABC):
    def __init__(self, players_per_instance, pm_callback_pipe, options, **kwargs):
        super().__init__(**kwargs)

        self.id = secrets.token_hex(PLAYER_ID_LENGTH)
        self.options = options

        self.process = Process(
            target=self.run,
            daemon=True,
            name=f"{self.__class__.__name__}_{self.id}",
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
        # init app id to make settings available from subprocess
        init_app_env_id()

        if self._log_queue is not None:
            child_process_config(self._log_queue, self._log_level)

        self._guard_against_orphaning()

        try:
            self.process_body()
        except KeyboardInterrupt:
            logging.getLogger("InstanceProcess").debug("KeyboardInterrupt in process")
        except Exception:
            traceback_txt = traceback.format_exc()

            logging.getLogger("InstanceProcess").critical(traceback_txt)

            self.crash(traceback_txt)
        finally:
            if self._log_queue is not None:
                self._log_queue.close()

    # process
    def _guard_against_orphaning(self):
        """Make sure this process cannot outlive the player that started it.

        Nothing runs in the player when it dies of an access violation, so
        both of these have to hold without it. The kernel kills us outright
        where it can; the watchdog covers the rest, including the moment
        before the kernel was asked.

        macOS has no kernel side to ask -- no job objects, no PDEATHSIG -- so
        there the watchdog is all there is. It misses only a child that holds
        the GIL for good, which libvlc cannot cause: python-vlc calls it
        through ctypes.CDLL, which releases the GIL for the call.
        """
        arm_parent_death_signal()

        Thread(target=self._watch_parent, daemon=True, name="parent_watch").start()

    # process
    def _watch_parent(self):
        parent = parent_process()

        if parent is None:
            return

        # Returns straight away if the parent is already gone.
        parent.join()

        logging.getLogger("InstanceProcess").critical(
            "Parent process is gone, terminating"
        )

        # No clean shutdown to be had: the window VLC draws into belongs to the
        # process that just died, and releasing the player would block on it.
        os._exit(ORPHANED_EXIT_CODE)

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
    def set_log_level(self, log_level):
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
    @abstractmethod
    def init_instance(self):
        """Instance initialization"""

    # process
    @abstractmethod
    def cleanup_instance(self):
        """Instance cleanup"""

    # process
    @abstractmethod
    def new_player(self, player_id, init_data, pipe):
        """Request new player"""

    # process
    @abstractmethod
    def init_player_shared_data(self, player_id):
        """Initialize shared data for player instance"""

    # process
    @abstractmethod
    def release_player_shared_data(self, player_id):
        """Release shared data for player instance"""
