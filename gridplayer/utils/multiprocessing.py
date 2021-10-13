import contextlib
import ctypes
import gc
import logging
import logging.handlers
import multiprocessing
import os
import secrets
import threading
import time
import traceback
from multiprocessing import Pipe, Value, connection
from multiprocessing.context import Process
from multiprocessing.shared_memory import SharedMemory
from threading import Thread, get_ident

from PyQt5 import QtCore
from PyQt5.QtCore import QObject

from gridplayer.utils import log_config
from gridplayer.settings import settings
from gridplayer.utils.log import log_environment
from gridplayer.utils.log_config import child_process_config


class CommandLoop:
    def __init__(self, pipe=None):
        self._pipe, self._self_pipe = Pipe() if pipe is None else pipe

    def cmd_loop_run(self):
        while connection.wait([self._pipe]):
            if not self._pipe.poll():
                continue

            command_name, command_args = self._pipe.recv()

            if command_name == "loop_stop":
                break

            func = getattr(self, command_name, None)

            if func is None or not callable(func):
                continue

            func(*command_args)

    def cmd_loop_terminate(self):
        self.cmd_send_self("loop_stop")

    def cmd_send(self, cmd_name, *cmd_args):
        self._pipe.send((cmd_name, cmd_args))

    def cmd_send_self(self, cmd_name, *cmd_args):
        self._self_pipe.send((cmd_name, cmd_args))

    def cmd_child_pipe(self):
        return self._self_pipe, self._pipe


class CommandLoopThreaded(CommandLoop):
    def __init__(self, crash_func, pipe=None):
        super().__init__(pipe)

        self._thread = None
        self._thread_init_func = None

        self.crash_func = crash_func

    def cmd_loop_start_thread(self, init_func=None):
        self._thread_init_func = init_func

        self._thread = Thread(target=self.cmd_loop_thread_func)
        self._thread.start()

    def cmd_loop_thread_func(self):
        try:
            if self._thread_init_func:
                self._thread_init_func()

            self.cmd_loop_run()
        except Exception:
            traceback_txt = traceback.format_exc()
            exception_txt = f"Exception in thread\n{self._thread.name}\n{traceback_txt}"

            logger = logging.getLogger(self.__class__.__name__)
            logger.critical(exception_txt)

            if self.crash_func is not None:
                self.crash_func(exception_txt)

    def cmd_loop_terminate(self):
        super().cmd_loop_terminate()

        if self._thread is not None and get_ident() != self._thread.ident:
            self._thread.join()


class PlayerInstance:
    def __init__(self, instance, player_id):
        self._instance = instance
        self._player_id = player_id

    def get_player_shared_data(self):
        return self._instance.get_player_shared_data(self._player_id)

    def cleanup(self):
        self._instance.cleanup_player_shared_data(self._player_id)


class ProcessManager(CommandLoopThreaded, QObject):
    crash = QtCore.pyqtSignal(str)

    def __init__(self, instance_class):
        QObject.__init__(self)
        CommandLoopThreaded.__init__(self, crash_func=self.crash_all)

        self.instances = {}

        self.instances_killed = threading.Condition()

        self.limit = settings.get("player/video_driver_players")
        self.instance_class = instance_class

        if os.name != "nt":
            from multiprocessing import resource_tracker

            resource_tracker.ensure_running()

        self.cmd_loop_start_thread()

        # When forking log config is inherited by children
        # When spawning log must be handled manually
        if multiprocessing.get_start_method() != "fork":
            self.log_queue = multiprocessing.Queue(-1)
            self.log_listener = log_config.QueueListenerRoot(self.log_queue)
            self.log_listener.start()
        else:
            self.log_queue = None
            self.log_listener = None

        self.logger = logging.getLogger("ProcessManager")

    def get_available_instance(self):
        available_instances = (
            i for i in self.instances.values() if i.player_count.value < self.limit
        )

        return next(available_instances, None)

    def get_instance(self):
        instance = self.get_available_instance()

        if instance is None:
            instance = self.create_instance()
            self.instances[instance.id] = instance

            self.logger.debug(f"Launching process {instance.id}")
            instance.start()

        return instance

    def create_instance(self):
        log_level = settings.get("logging/log_level")

        return self.instance_class(
            self.limit, self._self_pipe, self.log_queue, log_level
        )

    def init_player(self, init_data, pipe):
        instance = self.get_instance()
        player_id = instance.request_new_player(init_data, pipe)

        return PlayerInstance(instance, player_id)

    def cleanup_instance(self, inst_id):
        self.instances[inst_id].join()
        self.instances[inst_id].close()

        del self.instances[inst_id]

        with self.instances_killed:
            if len(self.instances) == 0:
                self.instances_killed.notify()

    def crash_all(self, traceback_txt):
        self._force_terminate_children()

        self.crash.emit(traceback_txt)

    def cleanup(self):
        self.logger.debug("Waiting for processes to shut down...")

        with self.instances_killed:
            self.instances_killed.wait_for(lambda: len(self.instances) == 0, timeout=3)

        self._force_terminate_children()

        self.logger.debug("Terminating command loop...")
        self.cmd_loop_terminate()

        if self.log_listener is not None and self.log_listener._thread is not None:
            self.logger.debug("Terminating log listener...")
            self.log_listener.stop()

        # # Kill resource manager
        # if os.name != "nt":
        #     self.logger.debug("Stopping resource tracker...")
        #
        #     import gc
        #     gc.collect()
        #
        #     from multiprocessing import resource_tracker
        #
        #     resource_tracker._resource_tracker._stop()

    def _force_terminate_children(self):
        if multiprocessing.active_children():
            self.logger.warning("Force terminating child processes...")
            for p in multiprocessing.active_children():
                p.terminate()

    def set_log_level(self, log_level):
        active_instances = (i for i in self.instances.values() if not i.is_dead.value)

        for a in active_instances:
            a.request_set_log_level(log_level)


class InstanceProcess(Process, CommandLoop):
    def __init__(self, players_per_instance, pm_callback_pipe, pm_log_queue, log_level):
        Process.__init__(self)
        CommandLoop.__init__(self)

        self.id = secrets.token_hex(8)

        self.players_per_instance = players_per_instance
        self.pm_callback_pipe = pm_callback_pipe

        # shared data outside
        self._players_shared_data = {}

        # shared data multiprocess
        self.player_count = Value("i", 0)
        self.is_dead = Value("i", 0)
        self.log_queue = pm_log_queue
        self.log_level = log_level

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
        if player_id in self._players_shared_data:
            del self._players_shared_data[player_id]

    # process
    def run(self):
        if self.log_queue is not None:
            child_process_config(self.log_queue, self.log_level)

        logger = logging.getLogger("InstanceProcess")

        try:
            logger.debug("Starting process...")

            log_environment()

            self.init_instance()
            self.cmd_loop_run()

            logger.debug("Terminating process...")
        except Exception:
            traceback_txt = traceback.format_exc()
            logger.critical(traceback_txt)

            self.crash(traceback_txt)
        finally:
            if self.log_queue is not None:
                self.log_queue.close()

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

        # self.cmd_send("cleanup_instance", self.id)

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
        pass

    # process
    def cleanup_instance(self):
        pass

    # process
    def new_player(self, player_id, init_data, pipe):
        pass

    # process
    def init_player_shared_data(self, player_id):
        pass

    # process
    def release_player_shared_data(self, player_id):
        pass


class releasing:
    def __init__(self, thing):
        self.thing = thing

    def __enter__(self):
        return self.thing

    def __exit__(self, *exc_info):
        with contextlib.suppress(ValueError):
            self.thing.release()


class SafeSharedMemory:
    def __init__(self, name, lock):
        self._name = name
        self._lock = lock

        self._memory = self._get_memory(True)

        self._buf_size = None
        self._ptr = None

        self._is_allocator = False
        self._is_cleaned = False

        self.is_closing = False

        self.logger = logging.getLogger("SafeSharedMemory")

    def _get_memory(self, is_init=False):
        try:
            return SharedMemory(name=self._name)
        except FileNotFoundError:
            if not is_init:
                raise RuntimeError("Memory not allocated")
            return None

    def allocate(self, size):
        self._is_allocator = True

        self._buf_size = size
        self._memory = SharedMemory(name=self._name, create=True, size=size)

    def get_memory(self):
        if self._memory is None:
            self._memory = self._get_memory()

        return self._memory

    def get_memory_buf(self):
        if self._memory is None:
            self._memory = self._get_memory()

        return self._memory.buf

    def get_ptr(self):
        if self._ptr is None:
            if self.is_closing:
                self.logger.warning(f"Getting ptr")
            if self._memory is None:
                self._memory = self._get_memory()

            # https://stackoverflow.com/questions/32364876/how-to-get-the-address-of-mmap-ed-memory-in-python
            # ptr = ctypes.POINTER(ctypes.c_char)(ctypes.c_char.from_buffer(memory._mmap))
            ptr = (ctypes.c_char * self._buf_size).from_buffer(self._memory._mmap)
            self._ptr = ctypes.cast(ptr, ctypes.c_void_p)

        return self._ptr

    def __enter__(self):
        return self._lock.__enter__()

    def __exit__(self, *args):
        return self._lock.__exit__(*args)

    def acquire(self):
        self._lock.acquire()

    def release(self):
        self._lock.release()

    def unlink(self):
        if self._memory is None:
            return

        if not self._is_allocator:
            raise RuntimeError("Only allocator can unlink memory")

        self._memory.unlink()
        self._memory = None

    def close(self):
        self.is_closing = True
        if self._memory is None:
            return

        # https://stackoverflow.com/questions/53339931/properly-discarding-ctypes-pointers-to-mmap-memory-in-python
        self._ptr = None
        gc.collect()

        for _ in range(10):
            try:
                self._memory.close()
                break
            except BufferError as e:
                # Rare race condition
                # probably happens because VLC hold pointer to the buffer??
                # or gc is slow
                # https://github.com/python/cpython/blob/main/Modules/mmapmodule.c
                # cannot close exported pointers exist
                self.logger.warning(f"{e}, retrying...")
                time.sleep(0.1)

        # https://bugs.python.org/issue39959
        # if not self._is_allocator and os.name != "nt":
        #     from multiprocessing import resource_tracker
        #
        #     resource_tracker.unregister(self._memory._name, "shared_memory")
