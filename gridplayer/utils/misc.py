import ctypes
import os
import re
import signal
from contextlib import suppress
from multiprocessing.process import active_children
from typing import NoReturn

from gridplayer.params import env


def force_terminate_resource_tracker():
    # windows doesn't have resource tracker
    if env.IS_WINDOWS:
        return

    # kill resource_tracker first so it won't complain about leaked resources
    from multiprocessing.resource_tracker import _resource_tracker

    if _resource_tracker._pid is not None:
        os.kill(_resource_tracker._pid, signal.SIGKILL)


def force_terminate_children():
    for p in active_children():
        # the process manager closes the ones that exit as they do
        with suppress(ValueError):
            p.terminate()


def force_terminate_children_all():
    force_terminate_resource_tracker()
    force_terminate_children()


def force_terminate(exit_code: int = 0):
    with suppress(ValueError):
        force_terminate_children_all()
    end_process(exit_code)


def end_process(exit_code: int) -> NoReturn:
    """End this process at once, its threads left where they are.

    On Windows by TerminateProcess. os._exit's ExitProcess kills the other
    threads mid-call and then unloads every DLL, and on arm64 one waited for
    good on a lock a killed VLC thread held (CI, 2026-11-20).
    """

    if env.IS_WINDOWS:
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), exit_code)

    os._exit(exit_code)


def is_url(s) -> bool:
    return bool(re.match("^[a-z]+://", s))
