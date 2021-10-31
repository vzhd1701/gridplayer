import logging
import os
import secrets
import traceback
from multiprocessing import Queue, Value, active_children, get_start_method
from multiprocessing.context import Process
from threading import Condition

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.multiprocess.command_loop import CommandLoop, CommandLoopThreaded
from gridplayer.settings import Settings
from gridplayer.utils.log_config import QueueListenerRoot, child_process_config


class PlayerInstance(object):
    def __init__(self, instance, player_id):
        self._instance = instance
        self._player_id = player_id

    def get_player_shared_data(self):
        return self._instance.get_player_shared_data(self._player_id)

    def cleanup(self):
        self._instance.cleanup_player_shared_data(self._player_id)


class ProcessManager(CommandLoopThreaded, QObject):
    crash = pyqtSignal(str)

    def __init__(self, instance_class, **kwargs):
        super().__init__(**kwargs)

        self.crash_func = self.crash_all

        self.instances = {}

        self._instances_killed = Condition()

        self._limit = Settings().get("player/video_driver_players")
        self._instance_class = instance_class

        # Prevent opening multiple resource trackers
        if os.name != "nt":
            from multiprocessing.resource_tracker import ensure_running  # noqa: WPS433

            ensure_running()

        self.cmd_loop_start_thread()

        # When forking log config is inherited by children
        # When spawning log must be handled manually
        if get_start_method() == "fork":
            self._log_queue = None
            self._log_listener = None
        else:
            self._log_queue = Queue(-1)
            self._log_listener = QueueListenerRoot(self._log_queue)
            self._log_listener.start()

        self._logger = logging.getLogger("ProcessManager")

    def get_instance(self):
        instance = self._get_available_instance()

        if instance is None:
            instance = self.create_instance()
            self.instances[instance.id] = instance

            self._logger.debug(f"Launching process {instance.id}")
            instance.process.start()

        return instance

    def create_instance(self):
        log_level = Settings().get("logging/log_level")

        return self._instance_class(
            self._limit, self._self_pipe, self._log_queue, log_level
        )

    def init_player(self, init_data, pipe):
        instance = self.get_instance()
        player_id = instance.request_new_player(init_data, pipe)

        return PlayerInstance(instance, player_id)

    def cleanup_instance(self, inst_id):
        self.instances[inst_id].process.join()
        self.instances[inst_id].process.close()

        self.instances.pop(inst_id)

        with self._instances_killed:
            if not self.instances:
                self._instances_killed.notify()

    def crash_all(self, traceback_txt):
        self._force_terminate_children()

        self.crash.emit(traceback_txt)

    def cleanup(self):
        self._logger.debug("Waiting for processes to shut down...")

        with self._instances_killed:
            self._instances_killed.wait_for(lambda: not self.instances, timeout=3)

        if active_children():
            self._logger.warning("Force terminating child processes...")
            self._force_terminate_children()

        self._logger.debug("Terminating command loop...")
        self.cmd_loop_terminate()

        if self._log_listener is not None:
            self._logger.debug("Terminating log listener...")
            self._log_listener.stop()

    def set_log_level(self, log_level):
        active_instances = (i for i in self.instances.values() if not i.is_dead.value)

        for a in active_instances:
            a.request_set_log_level(log_level)

    def _get_available_instance(self):
        available_instances = (
            i for i in self.instances.values() if i.player_count.value < self._limit
        )

        return next(available_instances, None)

    def _force_terminate_children(self):
        for p in active_children():
            p.terminate()


class InstanceProcess(CommandLoop):
    def __init__(
        self, players_per_instance, pm_callback_pipe, pm_log_queue, log_level, **kwargs
    ):
        super().__init__(**kwargs)

        self.id = secrets.token_hex(8)

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

        self._log_queue = pm_log_queue
        self._log_level = log_level

        # process variables
        self._players = {}

    # outside
    def request_new_player(self, init_data, pipe):
        with self.player_count.get_lock():
            self.player_count.value += 1

        player_id = secrets.token_hex(8)

        self.init_player_shared_data(player_id)

        self.cmd_send_self("new_player", player_id, init_data, pipe)

        return player_id

    # outside
    def get_player_shared_data(self, player_id):
        return self._players_shared_data[player_id]

    # outside
    def cleanup_player_shared_data(self, player_id):
        self._players_shared_data.pop(player_id, None)

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
