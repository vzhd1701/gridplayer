import logging
import os
from multiprocessing import Queue, active_children, get_start_method
from threading import Condition

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.settings import Settings
from gridplayer.utils.log_config import QueueListenerRoot
from gridplayer.utils.misc import force_terminate_children


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

        instance = self._instance_class(
            players_per_instance=self._limit, pm_callback_pipe=self._self_pipe
        )

        if self._log_queue:
            log_level = Settings().get("logging/log_level")
            instance.setup_log_queue(self._log_queue, log_level)

        return instance

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
        force_terminate_children()

        self.crash.emit(traceback_txt)

    def cleanup(self):
        self._logger.debug("Waiting for processes to shut down...")

        with self._instances_killed:
            self._instances_killed.wait_for(lambda: not self.instances, timeout=3)

        if active_children():
            self._logger.warning("Force terminating child processes...")
            force_terminate_children()

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
