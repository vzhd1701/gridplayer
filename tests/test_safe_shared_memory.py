import os
from multiprocessing.shared_memory import SharedMemory
from threading import Lock
from uuid import uuid4

import pytest

from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.vlc_player.rgb_buffer import FrameReader

# a Windows segment has no name that outlives its handles
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX shared memory")


def _name():
    return f"test-ssm-{uuid4().hex[:12]}"


def _exists(segment_name):
    try:
        SharedMemory(name=segment_name).close()
    except FileNotFoundError:
        return False
    return True


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "SafeSharedMemory"]


@posix_only
def test_reader_takes_the_name_down_once_it_has_the_segment():
    name = _name()
    writer = SafeSharedMemory(name, Lock())
    reader = SafeSharedMemory(name, Lock())

    try:
        writer.allocate(64)
        reader.attach(64)

        assert not _exists(f"{name}-64")

        # the name is gone, the memory both sides share is not
        writer.memory.buf[:64] = b"\x07" * 64
        assert bytes(FrameReader().read(reader, 4, 4)) == b"\x07" * 64
    finally:
        reader.close()
        writer.close()


@posix_only
def test_nothing_is_left_behind_by_a_writer_that_never_closes(caplog):
    # what a player killed on app close amounts to
    name = _name()
    writer = SafeSharedMemory(name, Lock())
    reader = SafeSharedMemory(name, Lock())
    sizes = (64, 256, 1024)

    try:
        for size in sizes:
            writer.allocate(size)
            reader.attach(size)
        reader.close()

        assert [s for s in sizes if _exists(f"{name}-{s}")] == []
    finally:
        writer.close()

    assert _warnings(caplog) == []


def test_writer_lets_go_after_the_reader_took_the_name_down(mocker, caplog):
    name = _name()
    writer = SafeSharedMemory(name, Lock())
    reader = SafeSharedMemory(name, Lock())
    closes = mocker.spy(writer, "_close_memory")

    writer.allocate(64)
    reader.attach(64)
    writer.allocate(256)
    reader.attach(256)
    reader.close()
    writer.close()

    assert closes.spy_return_list == [True, True]
    assert _warnings(caplog) == []
