import logging
import os
from multiprocessing import Queue, active_children, connection, get_start_method
from threading import Condition, Lock

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.multiprocess.command_loop import CommandLoopThreaded
from gridplayer.multiprocess.job_object import create_kill_on_close_job
from gridplayer.settings import Settings
from gridplayer.utils.log_config import QueueListenerRoot
from gridplayer.utils.misc import force_terminate_children, force_terminate_children_all


class PlayerInstance:
    def __init__(self, instance, player_id, manager):
        self._instance = instance
        self._player_id = player_id
        self._manager = manager

    def get_player_shared_data(self):
        return self._instance.get_player_shared_data(self._player_id)

    def cleanup(self):
        self._instance.cleanup_player_shared_data(self._player_id)

        self._manager.forget_player(self._instance.id, self._player_id)


def describe_exit_code(exit_code) -> str:
    if exit_code is None:
        return "unknown"

    # killed by a signal, as multiprocessing reports it
    if exit_code < 0:
        return f"signal {-exit_code}"

    # Windows exception codes, such as 0xC0000005 for an access violation
    if exit_code > 0xFFFF:
        return f"{exit_code:#010x}"

    return str(exit_code)


class ProcessManager(CommandLoopThreaded, QObject):
    crash = pyqtSignal(str)

    def __init__(self, instance_class, **kwargs):
        super().__init__(**kwargs)

        self.crash_func = self.crash_all

        self.instances_lock = Lock()
        self.instances = {}

        # instances that said they are done, until their process is gone
        self._exiting_instances = {}

        # who to tell when an instance dies under its players, by instance
        # and then by player; see init_player
        self._crash_listeners = {}

        # processes going down because we are taking them down
        self._is_shutting_down = False

        # Our half of making sure no decoder process outlives us when we die
        # without running any cleanup at all. The children look after
        # themselves too, see InstanceProcess._guard_against_orphaning.
        self._job = create_kill_on_close_job()

        self._instances_killed = Condition()

        self._limit = Settings().get("player/video_driver_players")
        self._instance_class = instance_class

        # Prevent opening multiple resource trackers
        if os.name != "nt":
            from multiprocessing.resource_tracker import ensure_running

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

        self._log = logging.getLogger(self.__class__.__name__)

    @property
    def active_instances(self):
        with self.instances_lock:
            return [
                instance
                for instance in self.instances.values()
                if self._is_instance_alive(instance)
            ]

    def get_instance(self, options):
        instance = self._get_available_instance(options)

        if instance is None:
            instance = self.create_instance(options=options)

            self._log.debug(f"Launching process {instance.id}")

            instance.process.start()

            # A crash in the sliver between the start and here would leave the
            # child out of the job, but the child's own watchdog covers that:
            # it reports a parent that is already gone.
            self._job.assign(instance.process.pid)

            # only once started: the loop waits on every process listed here
            with self.instances_lock:
                self.instances[instance.id] = instance

            # and is waiting on the ones it knew of before this one
            self.cmd_send_self("watch_processes")

        return instance

    def create_instance(self, options):
        instance = self._instance_class(
            players_per_instance=self._limit,
            pm_callback_pipe=self._self_pipe,
            options=options,
        )

        if self._log_queue:
            log_level = Settings().get("logging/log_level")
            instance.setup_log_queue(self._log_queue, log_level)

        return instance

    def init_player(self, init_data, pipe, options, on_crash=None):
        """Start a player in a process, and say if that process dies.

        on_crash is called with the exit code when the process dies before
        the player was released, from the thread the manager runs on.
        """

        instance = self.get_instance(options)
        player_id = instance.request_new_player(init_data, pipe)

        if on_crash is not None:
            with self.instances_lock:
                is_alive = instance.id in self.instances
                if is_alive:
                    listeners = self._crash_listeners.setdefault(instance.id, {})
                    listeners[player_id] = on_crash

            # gone before there was anyone to tell
            if not is_alive:
                on_crash(None)

        return PlayerInstance(instance, player_id, self)

    def forget_player(self, inst_id, player_id):
        with self.instances_lock:
            self._crash_listeners.get(inst_id, {}).pop(player_id, None)

    def cleanup_instance(self, inst_id):
        with self.instances_lock:
            instance = self.instances.pop(inst_id, None)

            if instance is None:
                return

            self._crash_listeners.pop(inst_id, None)

            # Its process goes on releasing VLC for a moment. Waiting for it
            # here would hold up the news from every other process, so it is
            # let go of once it exits; see cmd_loop_run.
            self._exiting_instances[inst_id] = instance

    def watch_processes(self):
        """Nothing to do: getting here has the loop wait on new processes."""

    def cmd_loop_run(self):
        """Wait for news from the processes, and for the processes to exit.

        A process that dies of an access violation says nothing on its way
        out, and its pipes do not break either: this process holds both of
        their ends. That it has exited is all there is to go by.
        """

        while True:
            with self.instances_lock:
                watched = {
                    instance.process.sentinel: instance
                    for instance in (
                        *self.instances.values(),
                        *self._exiting_instances.values(),
                    )
                }

            ready = connection.wait([self._pipe, *watched])

            # all of it before the exits: what an instance sent on its way
            # out says whether it was meant to go
            while self._pipe.poll():
                command_name, command_args = self._pipe.recv()

                if command_name == "loop_stop":
                    return

                self.cmd_process_command(command_args, command_name)

            for sentinel in ready:
                if sentinel in watched:
                    self._process_exited(watched[sentinel])

    def _process_exited(self, instance):
        with self.instances_lock:
            is_expected = self._exiting_instances.pop(instance.id, None) is not None
            if not is_expected:
                self.instances.pop(instance.id, None)

            listeners = self._crash_listeners.pop(instance.id, {})

        instance.process.join()
        exit_code = instance.process.exitcode
        instance.process.close()

        # its last player was released, and it was on its way out anyway
        with instance.is_dead.get_lock():
            is_expected = is_expected or bool(instance.is_dead.value)

        if not is_expected and not self._is_shutting_down:
            self._log.error(
                f"Decoder process {instance.id} died"
                f" with exit code {describe_exit_code(exit_code)},"
                f" taking {len(listeners)} player(s) with it"
            )

            for on_crash in listeners.values():
                self._report_crash(on_crash, exit_code)

        with self._instances_killed:
            if not self.instances and not self._exiting_instances:
                self._instances_killed.notify()

    def _report_crash(self, on_crash, exit_code):
        # one player failing to hear of it must not keep it from the others
        try:
            on_crash(exit_code)
        except Exception:
            self._log.warning("Failed to report a crash", exc_info=True)

    def crash_all(self, traceback_txt):
        self._is_shutting_down = True

        force_terminate_children_all()

        self.crash.emit(traceback_txt)

    def cleanup(self):
        self._log.debug("Waiting for processes to shut down...")

        # Until each has released VLC; what is left of them after that is
        # Python's own shutdown, and not worth holding the player up for.
        with self._instances_killed:
            self._instances_killed.wait_for(lambda: not self.instances, timeout=5)

        self._is_shutting_down = True

        if active_children():
            self._log.warning("Force terminating child processes...")
            force_terminate_children()

        # Nothing is left to protect, and dropping this takes out whatever
        # force_terminate_children could not.
        self._job.close()

        self._log.debug("Terminating command loop...")
        self.cmd_loop_terminate()

        if self._log_listener is not None:
            self._log.debug("Terminating log listener...")
            self._log_listener.stop()

    def set_log_level(self, log_level):
        for a in self.active_instances:
            a.request_set_log_level(log_level)

    def _get_available_instance(self, options):
        for instance in self.active_instances:
            with instance.player_count.get_lock():
                if (
                    instance.options == options
                    and instance.player_count.value < self._limit
                ):
                    return instance

        return None

    def _is_instance_alive(self, instance) -> bool:
        with instance.is_dead.get_lock():
            if instance.is_dead.value:
                return False

        return instance.process.is_alive()
