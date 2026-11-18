"""How much video memory is left, for MPV's "Decode on the CPU" on Auto: a new
video decodes on the CPU when there isn't room for it on the GPU.

Read where it can be:
- Windows 10 and later, any GPU: DXGI's budget for this process and what it
  uses of it. The system lowers the budget as other programs take video
  memory, and past it moves this process's memory out to system memory, which
  slows everything on the GPU down.
- Linux with NVIDIA: NVML, what's free on the first GPU. Running out there
  fails the decoder, as nothing is moved out.
Elsewhere nothing is read, and Auto decodes on the GPU. Intel's GPUs use the
system's memory. AMD's on Linux move memory out to system memory as Windows
does, and their sysfs figures can't tell an APU's small slice of system memory
from a card's own.
"""

import ctypes
import logging
import threading
import time
import uuid
from dataclasses import dataclass

from gridplayer.params import env

_MIB = 1024 * 1024

# What a hardware decoded video takes: so much whatever its size, and so much
# by its pixels, the decoder's frames and the output's textures. Measured on an
# RTX 3060 (docs/plans/MPV_PLAN.md, 10.11): 240 MB at 1080p, 570 at 2160p,
# either output. 10-bit takes half as much again, 365 MB at 1080p, which the
# spare covers.
# Intel's VAAPI takes about 25 bytes a pixel and nothing fixed.
FIXED_BYTES = 128 * 1024 * 1024
BYTES_PER_PIXEL = 56
# the size counted for a video that doesn't say yet, as a stream may not
_UNKNOWN_SIZE = (1920, 1080)

# Kept free for everything else: the windows, other programs, a video's
# memory growing.
_SPARE_SHARE = 0.1
_SPARE_MIN = 256 * _MIB

# What's been given to new videos is counted as used until it shows in what's
# read, as many videos start at once. NVIDIA's decoder takes it about 60 ms
# after it's given, and a playlist's videos ask about 60 ms apart, before mpv
# even says what it decodes with. So the part of it not read yet: what's been
# given less what's been taken since the first of them was given. Given up
# once mpv says what it decodes with, or after this long for a video that
# never starts.
PENDING_S = 5.0

_log = logging.getLogger(__name__)

# what's read when not told, see VideoMemoryRoom
_PLATFORM = object()


@dataclass(frozen=True)
class VideoMemory:
    # what can be used, and what is
    total: int
    used: int


class VideoMemoryRoom:
    """Whether a new video fits on the GPU, one at a time, from any thread."""

    def __init__(self, read=_PLATFORM, clock=time.monotonic):
        """`read`: what's left now, or None for nothing to read. This platform's
        if not given."""

        self._read = _platform_reader() if read is _PLATFORM else read
        self._clock = clock
        self._lock = threading.Lock()
        # (when, bytes, what was in use then) given to videos starting, by their
        # claims
        self._pending: dict[object, tuple[float, int, int]] = {}

    def take(self, size: tuple[int, int] | None) -> object | None:
        """A claim on room for a video of this size, None if there isn't any. A
        claim when nothing can be read. What it claims counts as used until
        `started` is told the video has taken it."""

        needed = bytes_needed(size)
        width, height = size if size and all(size) else _UNKNOWN_SIZE

        with self._lock:
            memory = self._read_memory()

            if memory is None:
                return object()

            now = self._clock()
            self._pending = {
                claim: given
                for claim, given in self._pending.items()
                if now - given[0] < PENDING_S
            }
            pending = self._not_read_yet(memory.used)

            free = memory.total - memory.used - pending
            spare = max(_SPARE_MIN, int(memory.total * _SPARE_SHARE))

            if free - needed < spare:
                _log.info(
                    f"Video memory low, {width}x{height} decodes on the CPU:"
                    f" {free // _MIB} MB free of {memory.total // _MIB} MB,"
                    f" {pending // _MIB} MB of it given to videos starting"
                )
                return None

            claim = object()
            self._pending[claim] = (now, needed, memory.used)

            return claim

    def _not_read_yet(self, used: int) -> int:
        if not self._pending:
            return 0

        given = sum(needed for _, needed, _ in self._pending.values())
        used_before = min(used_then for _, _, used_then in self._pending.values())

        return max(0, given - max(0, used - used_before))

    def started(self, claim: object) -> None:
        """The video has its memory now, and it shows in what's read."""

        with self._lock:
            self._pending.pop(claim, None)

    def _read_memory(self) -> VideoMemory | None:
        if self._read is None:
            return None

        try:
            return self._read()
        except (OSError, ValueError, AttributeError) as e:
            _log.warning(f"Video memory can't be read, decoding on the GPU: {e}")
            # once is enough to know
            self._read = None
            return None


def bytes_needed(size: tuple[int, int] | None) -> int:
    """What a video of this size is counted to take on the GPU."""

    width, height = size if size and all(size) else _UNKNOWN_SIZE

    return FIXED_BYTES + width * height * BYTES_PER_PIXEL


_room: VideoMemoryRoom | None = None
_room_lock = threading.Lock()


def room() -> VideoMemoryRoom:
    """The one for the process, made when first asked."""

    global _room

    with _room_lock:
        if _room is None:
            _room = VideoMemoryRoom()

        return _room


def _platform_reader():
    if env.IS_WINDOWS:
        return _DxgiReader().read

    if env.IS_LINUX:
        return _NvmlReader.reader()

    return None


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def of(cls, text: str) -> "_GUID":
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class _DxgiVideoMemoryInfo(ctypes.Structure):
    _fields_ = [
        ("Budget", ctypes.c_uint64),
        ("CurrentUsage", ctypes.c_uint64),
        ("AvailableForReservation", ctypes.c_uint64),
        ("CurrentReservation", ctypes.c_uint64),
    ]


_IID_DXGI_FACTORY1 = "770aae78-f26f-4dba-a829-253c83d1b387"
_IID_DXGI_ADAPTER3 = "645967a4-1392-4310-a798-8053ce3e93fd"
_DXGI_ERROR_NOT_FOUND = ctypes.c_long(0x887A0002).value
_DXGI_MEMORY_SEGMENT_GROUP_LOCAL = 0

# places in the COM interfaces' tables of methods
_RELEASE = 2
_QUERY_INTERFACE = 0
_ENUM_ADAPTERS1 = 12
_QUERY_VIDEO_MEMORY_INFO = 14


def _com_call(obj: ctypes.c_void_p, index: int, argtypes: tuple = (), *args) -> int:
    """A method of a COM object, by its place, as an HRESULT."""

    table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])

    return method(obj, *args)


_OUT = ctypes.POINTER(ctypes.c_void_p)
_IN_GUID = ctypes.POINTER(_GUID)


class _DxgiReader:
    """The GPU this process uses the most of, as the one its videos are
    decoded on: with two, the one GL draws with, which mpv decodes on. The
    first one, the system's pick, until there's anything on one."""

    def __init__(self):
        self._adapters: list[ctypes.c_void_p] | None = None

    def read(self) -> VideoMemory | None:
        if self._adapters is None:
            self._adapters = _dxgi_adapters()

        readings = [_dxgi_memory(adapter) for adapter in self._adapters]

        # max keeps the first of equals
        return max(readings, key=lambda m: m.used, default=None)


def _dxgi_adapters() -> list[ctypes.c_void_p]:
    """Every GPU's IDXGIAdapter3, kept for the life of the process. Before
    Windows 10 there's no budget to read."""

    factory = ctypes.c_void_p()
    hresult = ctypes.WinDLL("dxgi").CreateDXGIFactory1(
        ctypes.byref(_GUID.of(_IID_DXGI_FACTORY1)), ctypes.byref(factory)
    )
    if hresult < 0:
        raise OSError(f"CreateDXGIFactory1 failed: {hresult & 0xFFFFFFFF:#x}")

    adapters = []

    try:
        while True:
            adapter = ctypes.c_void_p()
            hresult = _com_call(
                factory,
                _ENUM_ADAPTERS1,
                (ctypes.c_uint, _OUT),
                len(adapters),
                ctypes.byref(adapter),
            )
            if hresult == _DXGI_ERROR_NOT_FOUND:
                break
            if hresult < 0:
                raise OSError(f"EnumAdapters1 failed: {hresult & 0xFFFFFFFF:#x}")

            adapter3 = ctypes.c_void_p()
            hresult = _com_call(
                adapter,
                _QUERY_INTERFACE,
                (_IN_GUID, _OUT),
                ctypes.byref(_GUID.of(_IID_DXGI_ADAPTER3)),
                ctypes.byref(adapter3),
            )
            _com_call(adapter, _RELEASE)

            if hresult < 0:
                raise OSError("no IDXGIAdapter3, before Windows 10")

            adapters.append(adapter3)
    finally:
        _com_call(factory, _RELEASE)

    return adapters


def _dxgi_memory(adapter: ctypes.c_void_p) -> VideoMemory:
    info = _DxgiVideoMemoryInfo()
    hresult = _com_call(
        adapter,
        _QUERY_VIDEO_MEMORY_INFO,
        (ctypes.c_uint, ctypes.c_int, ctypes.POINTER(_DxgiVideoMemoryInfo)),
        0,
        _DXGI_MEMORY_SEGMENT_GROUP_LOCAL,
        ctypes.byref(info),
    )
    if hresult < 0:
        raise OSError(f"QueryVideoMemoryInfo failed: {hresult & 0xFFFFFFFF:#x}")

    return VideoMemory(total=info.Budget, used=info.CurrentUsage)


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


class _NvmlReader:
    def __init__(self, lib):
        self._lib = lib
        self._device = ctypes.c_void_p()

        self._check(lib.nvmlInit_v2(), "nvmlInit_v2")
        self._check(
            lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self._device)),
            "nvmlDeviceGetHandleByIndex_v2",
        )

    @classmethod
    def reader(cls):
        """None with no NVIDIA driver, or none working."""

        try:
            lib = ctypes.CDLL("libnvidia-ml.so.1")
        except OSError:
            return None

        try:
            return cls(lib).read
        except OSError as e:
            _log.info(f"NVML can't be used: {e}")
            return None

    def read(self) -> VideoMemory:
        memory = _NvmlMemory()
        self._check(
            self._lib.nvmlDeviceGetMemoryInfo(self._device, ctypes.byref(memory)),
            "nvmlDeviceGetMemoryInfo",
        )

        return VideoMemory(total=memory.total, used=memory.total - memory.free)

    @staticmethod
    def _check(result: int, name: str) -> None:
        if result != 0:
            raise OSError(f"{name} failed: {result}")
