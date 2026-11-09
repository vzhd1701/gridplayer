"""The graphics cards Windows has, for mpv to be told which one to draw with.

Asked of DXGI directly, as a laptop's cards are not all listed by anything
lighter. Over the raw COM table, there being no binding for it to hand.
"""

import ctypes
import logging
import uuid
from ctypes import POINTER, WINFUNCTYPE, byref, c_long, c_uint, c_void_p
from dataclasses import dataclass

from gridplayer.params import env
from gridplayer.params.static import GpuChoice

_IID_IDXGI_FACTORY1 = uuid.UUID("770aae78-f26f-4dba-a829-253c83d1b387")

_RELEASE = 2
_GET_DESC1 = 10
_ENUM_ADAPTERS1 = 12

_ADAPTER_FLAG_SOFTWARE = 2


class _AdapterDesc1(ctypes.Structure):
    _fields_ = (
        ("description", ctypes.c_wchar * 128),
        ("vendor_id", c_uint),
        ("device_id", c_uint),
        ("subsys_id", c_uint),
        ("revision", c_uint),
        ("dedicated_video_memory", ctypes.c_size_t),
        ("dedicated_system_memory", ctypes.c_size_t),
        ("shared_system_memory", ctypes.c_size_t),
        ("luid_low", ctypes.c_uint32),
        ("luid_high", ctypes.c_int32),
        ("flags", c_uint),
    )


@dataclass(frozen=True)
class GpuAdapter:
    name: str
    dedicated_memory: int


def _method(interface, index, *arg_types):
    table = ctypes.cast(interface, POINTER(POINTER(c_void_p))).contents

    return WINFUNCTYPE(c_long, c_void_p, *arg_types)(table[index])


def _release(interface) -> None:
    _method(interface, _RELEASE)(interface)


def _read_adapter(adapter) -> GpuAdapter | None:
    desc = _AdapterDesc1()

    if _method(adapter, _GET_DESC1, POINTER(_AdapterDesc1))(adapter, byref(desc)) < 0:
        return None

    if desc.flags & _ADAPTER_FLAG_SOFTWARE:
        return None

    return GpuAdapter(desc.description, desc.dedicated_video_memory)


def _read_adapters() -> tuple[GpuAdapter, ...]:
    create_factory = ctypes.windll.dxgi.CreateDXGIFactory1
    create_factory.argtypes = (c_void_p, POINTER(c_void_p))
    create_factory.restype = c_long

    iid = ctypes.create_string_buffer(_IID_IDXGI_FACTORY1.bytes_le)
    factory = c_void_p()

    if create_factory(iid, byref(factory)) < 0:
        return ()

    enum_adapters = _method(factory, _ENUM_ADAPTERS1, c_uint, POINTER(c_void_p))

    found = []
    index = 0

    try:
        while True:
            adapter = c_void_p()

            # it says it has run out with a failure
            if enum_adapters(factory, index, byref(adapter)) < 0:
                break

            try:
                found.append(_read_adapter(adapter))
            finally:
                _release(adapter)

            index += 1
    finally:
        _release(factory)

    return tuple(item for item in found if item is not None)


def gpu_adapters() -> tuple[GpuAdapter, ...]:
    """The real cards, the one Windows would pick for itself first."""

    if not env.IS_WINDOWS:
        return ()

    try:
        return _read_adapters()
    except (OSError, ValueError):
        logging.getLogger(__name__).warning("Could not list GPUs", exc_info=True)
        return ()


def resolve_gpu_adapter(
    choice: str, adapters: tuple[GpuAdapter, ...]
) -> str | None:
    """The name to give mpv for the setting, None to leave the pick to it.

    Never a name that isn't here: told to use a card it can't find, as with
    one taken out since it was picked, mpv opens no window at all.
    """

    if not adapters or choice == GpuChoice.AUTO:
        return None

    if choice == GpuChoice.HIGH_PERFORMANCE:
        return max(adapters, key=lambda item: item.dedicated_memory).name

    if choice == GpuChoice.POWER_SAVING:
        return min(adapters, key=lambda item: item.dedicated_memory).name

    return choice if any(item.name == choice for item in adapters) else None
