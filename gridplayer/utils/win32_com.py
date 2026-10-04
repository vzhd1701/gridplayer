import ctypes
import logging
import threading

from gridplayer.params import env

COINIT_MULTITHREADED = 0x0

_log = logging.getLogger(__name__)

_lock = threading.Lock()
_is_kept = False


def keep_mta_alive() -> None:
    """Keep COM's multithreaded apartment up for as long as the process lives.

    VLC's Windows video outputs look for orientation sensors each time they
    open a window, through COM, from threads that join the apartment and
    leave it again as well as from threads that use it without joining.
    When the last thread that joined leaves, COM takes the apartment down
    and unloads the DLLs loaded into it, SensorsApi.dll among them, while
    other threads are still running their code: an access violation that
    takes the whole process down. Four players opening in one process at
    once, as reloading a grid of streams has them do, hit it about once in
    a hundred reloads.
    """

    global _is_kept

    if not env.IS_WINDOWS:
        return

    with _lock:
        if _is_kept:
            return
        _is_kept = True

    ole32 = ctypes.WinDLL("ole32")

    # Windows 8 and later
    increment_mta_usage = getattr(ole32, "CoIncrementMTAUsage", None)
    if increment_mta_usage is not None:
        cookie = ctypes.c_void_p()
        result = increment_mta_usage(ctypes.byref(cookie))
        if result >= 0:
            return

        _log.warning(f"CoIncrementMTAUsage failed with {result & 0xFFFFFFFF:#x}")

    # a member that never leaves, which is all there is on Windows 7
    threading.Thread(target=_stay_in_mta, daemon=True, name="com_mta").start()


def _stay_in_mta() -> None:
    ctypes.WinDLL("ole32").CoInitializeEx(None, COINIT_MULTITHREADED)

    threading.Event().wait()
