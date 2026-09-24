import logging
import traceback
from multiprocessing import Pipe, connection
from threading import Lock, Thread, get_ident


class CommandLoop:
    def __init__(self, pipe=None, **kwargs):
        super().__init__(**kwargs)

        cmd_pipe, self_pipe = Pipe() if pipe is None else pipe
        self._pipe = cmd_pipe
        self._self_pipe = self_pipe

        # a connection takes one message at a time, and a player sends from
        # the thread running its commands and from VLC's event thread at once
        self._pipe_lock = Lock()
        self._self_pipe_lock = Lock()

    def __getstate__(self):
        # a player process is handed to its child whole, and a lock cannot
        # be; the child gets locks of its own
        state = self.__dict__.copy()

        del state["_pipe_lock"]
        del state["_self_pipe_lock"]

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._pipe_lock = Lock()
        self._self_pipe_lock = Lock()

    def cmd_loop_run(self):
        while connection.wait([self._pipe]):
            if not self._pipe.poll():
                continue

            command_name, command_args = self._pipe.recv()

            if command_name == "loop_stop":
                break

            self.cmd_process_command(command_args, command_name)

    def cmd_process_command(self, command_args, command_name):
        func = getattr(self, command_name, None)

        if func is None or not callable(func):
            return

        func(*command_args)

    def cmd_loop_terminate(self):
        self.cmd_send_self("loop_stop")

    def cmd_send(self, cmd_name, *cmd_args):
        with self._pipe_lock:
            self._pipe.send((cmd_name, cmd_args))

    def cmd_send_self(self, cmd_name, *cmd_args):
        with self._self_pipe_lock:
            self._self_pipe.send((cmd_name, cmd_args))

    def cmd_child_pipe(self):
        return self._self_pipe, self._pipe


class CommandLoopThreaded(CommandLoop):
    def __init__(self, crash_func=None, **kwargs):
        super().__init__(**kwargs)

        self._thread = None
        self._thread_init_func = None

        self.crash_func = crash_func

    def cmd_loop_start_thread(self, init_func=None):
        self._thread_init_func = init_func

        self._thread = Thread(target=self.cmd_loop_thread_func)
        self._thread.start()

    def cmd_loop_thread_func(self):
        try:
            self.cmd_loop_thread_body()
        except Exception:
            traceback_txt = traceback.format_exc()
            exception_txt = f"Exception in thread\n{self._thread.name}\n{traceback_txt}"

            logging.getLogger(self.__class__.__name__).critical(exception_txt)

            if self.crash_func is not None:
                self.crash_func(exception_txt)

    def cmd_loop_thread_body(self):
        if self._thread_init_func:
            self._thread_init_func()

        self.cmd_loop_run()

    def cmd_loop_terminate(self):
        super().cmd_loop_terminate()

        if self._thread is not None and get_ident() != self._thread.ident:
            self._thread.join()
