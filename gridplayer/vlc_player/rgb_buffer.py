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


class FrameReader:
    """The reader's own copy of the latest frame, refilled in place.

    A fresh bytes object per frame costs an allocation the size of the frame,
    which is most of what the copy costs. The buffer here is kept instead and
    only replaced when the frame size changes, never resized: the QImage on
    show still points into the one it was made from.

    Refilling the buffer that is on show is only safe on the thread that
    paints it, so read() belongs there too. Called from any other thread it
    would write a frame into the picture while it is being drawn.

    The copy is a memoryview slice assignment, so Python checks both ends
    against the objects themselves and refuses a size that doesn't match
    rather than trusting the arithmetic.
    """

    def __init__(self):
        self._buf = None

    def read(self, shared_memory, width, height):
        """Copy the frame out, or return None when the buffer can't hold it.

        Only ``width * height * 4`` bytes are taken, which is the frame as
        the decoder lays it out; the buffer only ever grows and can be much
        bigger than that.
        """

        size = width * height * 4

        with shared_memory:
            frame = shared_memory.memory.buf
            if frame is None or len(frame) < size:
                return None

            if self._buf is None or len(self._buf) != size:
                self._buf = bytearray(size)

            memoryview(self._buf)[:] = frame[:size]

        return self._buf

    def clear(self):
        self._buf = None
