"""Kernel-enforced cleanup of decoder processes.

A hard crash -- an access violation inside libvlc or Qt, a TerminateProcess, a
taskkill /F -- skips every atexit hook, so nothing in Python gets to reap the
decoder processes and they stay alive forever, each holding a VLC instance and
a few hundred megabytes.

A Windows job object with KILL_ON_JOB_CLOSE hands that problem to the kernel:
when the last handle to the job closes, which happens automatically when the
process holding it dies however it dies, every process still in the job is
terminated. No code of ours has to run, which is what makes this the only
layer that covers a decoder wedged inside libvlc while holding the GIL, where
the lifeline watchdog thread can never be scheduled.

Only the decoder processes go into the job, never the player itself: a job is
inherited by every child, and QDesktopServices.openUrl launches the log viewer
as one, which would then be killed along with the player.
"""

import ctypes
import logging

from gridplayer.params import env


class _NoJob:
    """Stand-in for platforms without job objects, and for a failed setup."""

    is_active = False

    def assign(self, pid: int) -> None:
        """Nothing to assign to"""

    def close(self) -> None:
        """Nothing to close"""


if env.IS_WINDOWS:
    from ctypes import wintypes

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            (field_name, ctypes.c_ulonglong)
            for field_name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobObjectBasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _WindowsKillOnCloseJob:
        is_active = True

        def __init__(self):
            self._log = logging.getLogger(self.__class__.__name__)
            self._handle = self._create()

        def assign(self, pid: int) -> None:
            """Put a process under the job, so it cannot outlive us."""
            if self._handle is None:
                return

            try:
                self._assign(pid)
            except OSError:
                # Not fatal on its own, the lifeline still covers a child that
                # is healthy enough to run Python.
                self._log.warning(
                    f"Could not put process {pid} under the job object",
                    exc_info=True,
                )

        def close(self) -> None:
            """Drop the job, terminating anything still in it."""
            if self._handle is None:
                return

            _kernel32.CloseHandle(self._handle)
            self._handle = None

        def _create(self):
            handle = _kernel32.CreateJobObjectW(None, None)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())

            limits = _JobObjectExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = (
                _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )

            is_set = _kernel32.SetInformationJobObject(
                handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            )
            if not is_set:
                error = ctypes.WinError(ctypes.get_last_error())
                _kernel32.CloseHandle(handle)
                raise error

            return handle

        def _assign(self, pid: int) -> None:
            process = _kernel32.OpenProcess(
                _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid
            )
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())

            try:
                if not _kernel32.AssignProcessToJobObject(self._handle, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _kernel32.CloseHandle(process)


def create_kill_on_close_job():
    """Make a job that terminates its members once this process is gone."""
    if not env.IS_WINDOWS:
        return _NoJob()

    try:
        return _WindowsKillOnCloseJob()
    except OSError:
        logging.getLogger(__name__).warning(
            "Could not create a job object,"
            " decoder processes will rely on the lifeline alone",
            exc_info=True,
        )

        return _NoJob()
