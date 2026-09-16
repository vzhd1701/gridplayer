import contextlib
import ctypes
import gc
import logging
import time
from multiprocessing.shared_memory import SharedMemory

# closing a mapping fails while anyone still holds a pointer into it
CLOSE_RETRIES = 10
CLOSE_RETRY_DELAY = 0.1


class releasing:
    def __init__(self, thing):
        self.thing = thing

    def __enter__(self):
        return self.thing

    def __exit__(self, *exc_info):
        with contextlib.suppress(ValueError, RuntimeError):
            self.thing.release()


class SafeSharedMemory:
    """A frame buffer shared with the process that displays the frames.

    Each buffer size gets a segment of its own, named after it, and the buffer
    only ever grows. A stream that changes format then moves both sides onto a
    new segment instead of one of them recreating the segment under the other,
    which on Windows fails outright while the other side still has it open.

    The two sides agree on nothing but the buffer size, which the reader is
    told along with the frame it belongs to.
    """

    def __init__(self, name, lock):
        self.name = name
        self.lock = lock

        self._memory = None
        self._segment_name = None
        self._retired = None

        self._buf_size = None
        self._ptr = None

        self._is_allocator = False

        self._log = logging.getLogger(self.__class__.__name__)

    @property
    def memory(self):
        if self._memory is None:
            raise RuntimeError("Memory not allocated")

        return self._memory

    @property
    def size(self):
        """How much the buffer holds, which is what names its segment."""

        return self._buf_size

    def allocate(self, size):
        """Make sure the buffer holds at least ``size`` bytes.

        It is never made smaller. A video output on its way out still copies
        frames of the size it was set up with, and shrinking underneath one
        puts that copy past the end of the buffer.
        """

        self._is_allocator = True

        if self._buf_size is not None and self._buf_size >= size:
            return

        self._use_segment(size, is_creating=True)

    def attach(self, size):
        """Follow the allocator onto the segment holding ``size`` bytes."""

        self._use_segment(size, is_creating=False)

    @property
    def ptr(self):
        if self._ptr is None:
            # https://stackoverflow.com/questions/32364876/how-to-get-the-address-of-mmap-ed-memory-in-python
            ptr = (ctypes.c_char * self._buf_size).from_buffer(self.memory._mmap)
            self._ptr = ctypes.cast(ptr, ctypes.c_void_p)

        return self._ptr

    def __enter__(self):
        return self.lock.acquire()

    def __exit__(self, *args):
        return self.lock.release()

    def close(self):
        memory = self._memory

        self._memory = None
        self._segment_name = None
        self._buf_size = None
        self._ptr = None

        self._release(self._retired)
        self._retired = None

        self._release(memory)

    def _use_segment(self, size, is_creating):
        segment_name = f"{self.name}-{size}"

        if self._segment_name == segment_name:
            return

        memory = self._open_segment(segment_name, size, is_creating)

        previous = self._memory

        self._memory = memory
        self._segment_name = segment_name
        self._buf_size = size
        self._ptr = None

        # the segment we just left stays mapped one round longer, for whoever
        # has not noticed yet that we moved on; by the next swap the output
        # that was using it is long gone
        self._release(self._retired)
        self._retired = previous

    def _open_segment(self, segment_name, size, is_creating):
        if not is_creating:
            try:
                return SharedMemory(name=segment_name)
            except FileNotFoundError:
                raise RuntimeError(f"Segment {segment_name} not allocated")

        try:
            return SharedMemory(name=segment_name, create=True, size=size)
        except FileExistsError:
            return self._reclaim_segment(segment_name, size)

    def _reclaim_segment(self, segment_name, size):
        """Take over a segment of ours that outlived the attempt to close it."""

        self._log.debug(f"Reclaiming leftover segment {segment_name}")

        memory = SharedMemory(name=segment_name)

        if memory.size < size:
            memory.close()
            raise RuntimeError(
                f"Segment {segment_name} is {memory.size} bytes, need {size}"
            )

        return memory

    def _release(self, memory):
        if memory is None:
            return

        # our own ctypes view of the mapping is only really gone once the cycle
        # holding it is collected, and mmap refuses to close until it is
        gc.collect()

        if not self._close_memory(memory):
            return

        if self._is_allocator:
            with contextlib.suppress(FileNotFoundError):
                memory.unlink()

    def _close_memory(self, memory) -> bool:
        for _ in range(CLOSE_RETRIES):
            try:
                memory.close()
            except BufferError as e:
                # VLC can still be writing through a pointer it took from us,
                # or the gc has not caught up with our own view of the mapping
                # https://github.com/python/cpython/blob/main/Modules/mmapmodule.c
                self._log.warning(f"{e}, retrying...")
                time.sleep(CLOSE_RETRY_DELAY)
                continue
            return True

        # a mapping left open is not a leak we can do anything about here, but
        # it does keep the name taken, which is what _reclaim_segment is for
        self._log.error(f"Failed to close {memory.name}, leaving it mapped")

        return False
