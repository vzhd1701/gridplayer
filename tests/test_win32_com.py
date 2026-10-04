"""COM's multithreaded apartment must outlive the threads that join it.

VLC's Windows video outputs use COM from threads that join the apartment and
leave it, and from threads that never join. Once the last thread that joined
has left, COM takes the apartment down and unloads what was loaded into it --
SensorsApi.dll, in VLC's case -- under the threads still using it.
"""

import subprocess
import sys
import textwrap

import pytest

from gridplayer.params import env
from gridplayer.utils import win32_com

CO_E_NOTINITIALIZED = 0x800401F0
APTTYPE_MTA = 1
APTTYPEQUALIFIER_IMPLICIT_MTA = 1

# Run apart: what COM does to a process lasts as long as the process.
PROBE = textwrap.dedent(
    """
    import ctypes
    import sys
    import threading
    import time
    from types import SimpleNamespace

    import gridplayer.utils.win32_com as win32_com

    ole32 = ctypes.WinDLL("ole32")

    def apartment():
        kind, qualifier = ctypes.c_int(), ctypes.c_int()
        result = ole32.CoGetApartmentType(ctypes.byref(kind), ctypes.byref(qualifier))
        return result & 0xFFFFFFFF, kind.value, qualifier.value

    def in_another_thread(func):
        results = []
        thread = threading.Thread(target=lambda: results.append(func()))
        thread.start()
        thread.join()
        return results[0]

    def join_and_leave():
        ole32.CoInitializeEx(None, 0)
        ole32.CoUninitialize()

    mode = sys.argv[1]

    if mode == "without_increment":
        class _Ole32WithoutIncrement:
            def __getattr__(self, name):
                if name == "CoIncrementMTAUsage":
                    raise AttributeError(name)
                return getattr(ole32, name)

        win32_com.ctypes = SimpleNamespace(
            WinDLL=lambda name: _Ole32WithoutIncrement(),
            c_void_p=ctypes.c_void_p,
            byref=ctypes.byref,
        )

    if mode != "plain":
        win32_com.keep_mta_alive()

    in_another_thread(join_and_leave)

    # the fallback joins from a thread of its own, which takes a moment
    end = time.monotonic() + 5
    while True:
        seen = in_another_thread(apartment)
        if seen[0] == 0 or time.monotonic() > end:
            break
        time.sleep(0.05)

    print(*seen)
    """
)


def _apartment_seen(mode):
    result = subprocess.run(
        [sys.executable, "-c", PROBE, mode],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return tuple(int(value) for value in result.stdout.split())


windows_only = pytest.mark.skipif(not env.IS_WINDOWS, reason="COM is Windows only")


@windows_only
def test_without_it_the_apartment_goes_with_the_last_thread_to_leave():
    """What the rest of this is about, so it shows if Windows ever changes."""
    assert _apartment_seen("plain")[0] == CO_E_NOTINITIALIZED


@windows_only
def test_the_apartment_stays_once_its_last_thread_has_left():
    assert _apartment_seen("keep") == (0, APTTYPE_MTA, APTTYPEQUALIFIER_IMPLICIT_MTA)


@windows_only
def test_it_stays_on_windows_7_too():
    """No CoIncrementMTAUsage there: a thread joins and never leaves."""
    assert _apartment_seen("without_increment") == (
        0,
        APTTYPE_MTA,
        APTTYPEQUALIFIER_IMPLICIT_MTA,
    )


def test_nothing_to_keep_elsewhere(mocker):
    mocker.patch.object(env, "IS_WINDOWS", False)
    mocker.patch.object(win32_com, "_is_kept", False)
    win_dll = mocker.patch.object(win32_com.ctypes, "WinDLL", create=True)

    win32_com.keep_mta_alive()

    win_dll.assert_not_called()


def test_vlc_has_it_before_it_starts(mocker):
    from gridplayer.vlc_player import instance as instance_mod

    order = []
    mocker.patch.object(
        instance_mod, "keep_mta_alive", side_effect=lambda: order.append("keep")
    )
    mocker.patch.object(
        instance_mod.vlc,
        "Instance",
        side_effect=lambda *args: order.append("vlc") or None,
    )
    mocker.patch.object(
        instance_mod.InstanceVLC, "init_options", new_callable=mocker.PropertyMock
    )

    with pytest.raises(RuntimeError):
        instance_mod.InstanceVLC(0, []).init_instance()

    assert order == ["keep", "vlc"]
