from multiprocessing import Lock as MPLock
from threading import Lock as ThreadLock
from uuid import uuid4

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory, releasing
from gridplayer.vlc_player.image_decoder import ImageDecoder


def test_stop_unlocked_threading_lock():
    decoder = ImageDecoder(SafeSharedMemory("test-imgdec-thread", ThreadLock()))
    decoder.stop()


def test_stop_unlocked_multiprocessing_lock():
    decoder = ImageDecoder(SafeSharedMemory("test-imgdec-mp", MPLock()))
    decoder.stop()


def test_stop_after_allocate_threading_lock():
    name = f"test-imgdec-alloc-{uuid4().hex[:12]}"
    decoder = ImageDecoder(SafeSharedMemory(name, ThreadLock()))
    decoder.set_frame(2, 2)
    decoder.stop()


def test_releasing_unlocked_threading_lock():
    lock = ThreadLock()
    with releasing(lock):
        pass
