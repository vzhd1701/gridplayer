"""Kernel-enforced cleanup of decoder processes, on Linux.

The counterpart of the Windows job object, doing the same job from the other
side: there the parent owns something the kernel empties when it dies, here
the child asks the kernel to kill it when its parent dies.

Like the job object, this is what covers a decoder wedged inside libvlc while
holding the GIL, where the watchdog thread can never be scheduled.

The signal is tied to the death of the parent *thread* that created this
process, not the parent process as a whole, so decoder processes have to be
started from the main thread -- which is where the video drivers are built,
and which cannot outlive the player anyway.
"""

import ctypes
import logging
import os
import signal

from gridplayer.params import env

_PR_SET_PDEATHSIG = 1


def arm_parent_death_signal() -> None:
    """Ask the kernel to kill this process once its parent is gone.

    A parent that died before this ran is not covered: the kernel does not
    report a death that already happened. The watchdog does, so it is the one
    that closes that gap.
    """
    if not env.IS_LINUX:
        return

    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
    except OSError:
        _log_not_armed("libc is not available")
        return

    if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        _log_not_armed(os.strerror(ctypes.get_errno()))


def _log_not_armed(reason: str) -> None:
    # Not fatal on its own, the watchdog still covers a child that is healthy
    # enough to run Python.
    logging.getLogger(__name__).warning(
        f"Could not arm the parent death signal ({reason}),"
        f" this process will rely on the watchdog alone"
    )
