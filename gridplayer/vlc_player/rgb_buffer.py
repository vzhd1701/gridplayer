import ctypes
from threading import Lock


class InProcessRgbBuffer:
    """RGB32 frame buffer in this process. Same duck type as SafeSharedMemory."""

    def __init__(self):
        self.lock = Lock()
        self._data = bytearray()
        self._holder = None
        self._retired = None
        self._ptr = None

    @property
    def size(self):
        return len(self._data)

    def allocate(self, size):
        """Make sure the buffer holds at least ``size`` bytes.

        It is never made smaller. A video output on its way out still copies
        frames of the size it was set up with, and shrinking underneath one
        puts that copy past the end of the buffer.
        """

        if size <= len(self._data):
            return

        data = bytearray(size)
        holder = (ctypes.c_char * size).from_buffer(data)

        # the buffer we just left is kept one round longer, for whoever has
        # not noticed yet that we moved on
        self._retired = (self._holder, self._data)

        self._data = data
        self._holder = holder
        self._ptr = ctypes.cast(holder, ctypes.c_void_p)

    def attach(self, size):
        """Nothing to follow: reader and writer share this object itself."""

    def close(self):
        self._ptr = None
        self._holder = None
        self._retired = None
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
