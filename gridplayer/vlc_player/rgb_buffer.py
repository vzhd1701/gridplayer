import ctypes
from threading import Lock


class InProcessRgbBuffer:
    """RGB32 frame buffer in this process. Same duck type as SafeSharedMemory."""

    def __init__(self):
        self.lock = Lock()
        self._data = bytearray()
        self._holder = None
        self._ptr = None

    def allocate(self, size):
        self._ptr = None
        self._holder = None
        self._data = bytearray(size)
        self._holder = (ctypes.c_char * size).from_buffer(self._data)
        self._ptr = ctypes.cast(self._holder, ctypes.c_void_p)

    def close(self):
        self._ptr = None
        self._holder = None
        self._data = bytearray()

    @property
    def ptr(self):
        return self._ptr

    @property
    def memory(self):
        return self

    @property
    def buf(self):
        return memoryview(self._data)

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, *exc):
        self.lock.release()
