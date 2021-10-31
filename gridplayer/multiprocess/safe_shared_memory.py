import contextlib
import ctypes
import gc
import logging
import time
from multiprocessing.shared_memory import SharedMemory


class releasing(object):
    def __init__(self, thing):
        self.thing = thing

    def __enter__(self):
        return self.thing

    def __exit__(self, *exc_info):
        with contextlib.suppress(ValueError):
            self.thing.release()


class SafeSharedMemory(object):
    def __init__(self, name, lock):
        self.name = name
        self.lock = lock

        self._memory = None

        self._buf_size = None
        self._ptr = None

        self._is_allocator = False
        self._is_cleaned = False

        self.logger = logging.getLogger("SafeSharedMemory")

    @property
    def memory(self):
        if self._memory is None:
            try:
                self._memory = SharedMemory(name=self.name)
            except FileNotFoundError:
                raise RuntimeError("Memory not allocated")

        return self._memory

    def allocate(self, size):
        self._is_allocator = True

        self._buf_size = size
        self._memory = SharedMemory(name=self.name, create=True, size=size)

    @property
    def ptr(self):
        if self._ptr is None:
            # https://stackoverflow.com/questions/32364876/how-to-get-the-address-of-mmap-ed-memory-in-python
            ptr = (ctypes.c_char * self._buf_size).from_buffer(
                self.memory._mmap  # noqa: WPS437
            )
            self._ptr = ctypes.cast(ptr, ctypes.c_void_p)

        return self._ptr

    def __enter__(self):
        return self.lock.acquire()

    def __exit__(self, *args):
        return self.lock.release()

    def close(self):
        if self._memory is None:
            return

        # https://stackoverflow.com/questions/53339931/properly-discarding-ctypes-pointers-to-mmap-memory-in-python
        self._ptr = None
        gc.collect()

        for _ in range(10):
            try:
                self._memory.close()
            except BufferError as e:
                # Rare race condition
                # probably happens because VLC hold pointer to the buffer??
                # or gc is slow
                # https://github.com/python/cpython/blob/main/Modules/mmapmodule.c
                # cannot close exported pointers exist
                self.logger.warning(f"{e}, retrying...")
                time.sleep(0.1)
                continue
            break

        if self._is_allocator:
            self._memory.unlink()
            self._memory = None
