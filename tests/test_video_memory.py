"""What's left of video memory, for Decode on the CPU set to Auto."""

import ctypes

import pytest

from gridplayer.params import env
from gridplayer.utils import video_memory
from gridplayer.utils.video_memory import (
    PENDING_S,
    VideoMemory,
    VideoMemoryRoom,
    bytes_needed,
)

_MIB = 1024 * 1024
_GIB = 1024 * _MIB

_1080P = bytes_needed((1920, 1080))


class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _room(total=4 * _GIB, used=0, clock=None):
    memory = {"now": VideoMemory(total=total, used=used)}

    room = VideoMemoryRoom(read=lambda: memory["now"], clock=clock or _Clock())
    room.memory = memory

    return room


def test_fits_with_room_to_spare():
    assert _room().take((1920, 1080)) is not None


def test_not_past_what_s_kept_free():
    # a tenth of 4 GiB kept free, and the video on top of it
    spare = 4 * _GIB // 10

    assert _room(used=4 * _GIB - spare - _1080P).take((1920, 1080)) is not None
    assert _room(used=4 * _GIB - spare - _1080P + _MIB).take((1920, 1080)) is None


def test_keeps_a_floor_free_on_a_small_gpu():
    total = _GIB
    floor = 256 * _MIB

    assert (
        _room(total=total, used=total - floor - _1080P + _MIB).take((1920, 1080))
        is None
    )


def test_what_s_given_to_videos_starting_counts_until_their_decoders_take_it():
    clock = _Clock()
    # room for 3 and a bit
    room = _room(used=int(4 * _GIB * 0.9) - _1080P * 3 - _MIB, clock=clock)

    assert [room.take((1920, 1080)) is not None for _ in range(4)] == [
        True,
        True,
        True,
        False,
    ]

    clock.now += PENDING_S

    assert room.take((1920, 1080)) is not None


def test_what_s_given_counts_only_until_it_shows_in_what_s_read():
    # room for 2
    room = _room(used=int(4 * _GIB * 0.9) - _1080P * 2 - _MIB)
    before = room.memory["now"]

    assert room.take((1920, 1080)) is not None

    # the first one's decoder has taken its memory, before mpv says so
    room.memory["now"] = VideoMemory(total=before.total, used=before.used + _1080P)

    assert room.take((1920, 1080)) is not None
    assert room.take((1920, 1080)) is None


def test_a_video_started_counts_by_what_s_read_alone():
    room = _room(used=int(4 * _GIB * 0.9) - _1080P * 2 - _MIB)

    first = room.take((1920, 1080))
    assert room.take((1920, 1080)) is not None
    assert room.take((1920, 1080)) is None

    # its memory shows in what's read instead
    room.started(first)

    assert room.take((1920, 1080)) is not None

    # told twice, as closing after starting does
    room.started(first)


def test_counted_as_measured_on_nvidia():
    assert 230 * _MIB < bytes_needed((1920, 1080)) < 260 * _MIB
    assert 550 * _MIB < bytes_needed((3840, 2160)) < 600 * _MIB


def test_platform_s_reading_unless_told(mocker):
    mocker.patch.object(video_memory, "_platform_reader", return_value="platform")

    assert VideoMemoryRoom()._read == "platform"
    assert VideoMemoryRoom(read=None)._read is None


def test_a_bigger_video_needs_more():
    room = _room(used=int(4 * _GIB * 0.9) - _1080P * 2)

    assert room.take((3840, 2160)) is None
    assert room.take((1920, 1080)) is not None


@pytest.mark.parametrize("size", [None, (0, 0)])
def test_a_video_that_doesn_t_say_its_size_counts_as_1080p(size):
    clock = _Clock()
    room = _room(used=int(4 * _GIB * 0.9) - _1080P - _MIB, clock=clock)

    assert room.take(size) is not None
    assert room.take(size) is None


def test_on_the_gpu_when_nothing_can_be_read():
    assert VideoMemoryRoom(read=None).take((1920, 1080)) is not None


def test_a_reading_that_fails_is_not_tried_again(caplog):
    calls = []

    def refuse():
        calls.append(1)
        raise OSError("QueryVideoMemoryInfo failed")

    room = VideoMemoryRoom(read=refuse)

    assert room.take((1920, 1080)) is not None
    assert room.take((1920, 1080)) is not None
    assert len(calls) == 1
    assert "can't be read" in caplog.text


def test_the_gpu_the_process_uses_the_most_of(mocker):
    adapters = ["display", "decoding", "basic"]
    used = {"display": 10, "decoding": 500, "basic": 0}

    mocker.patch.object(video_memory, "_dxgi_adapters", return_value=adapters)
    mocker.patch.object(
        video_memory,
        "_dxgi_memory",
        side_effect=lambda adapter: VideoMemory(total=1000, used=used[adapter]),
    )

    assert video_memory._DxgiReader().read().used == 500


def test_the_system_s_pick_before_anything_is_on_one(mocker):
    mocker.patch.object(video_memory, "_dxgi_adapters", return_value=["first", "b"])
    mocker.patch.object(
        video_memory,
        "_dxgi_memory",
        side_effect=lambda adapter: VideoMemory(total=len(adapter), used=0),
    )

    assert video_memory._DxgiReader().read().total == len("first")


@pytest.mark.skipif(not env.IS_WINDOWS, reason="DXGI")
def test_dxgi_is_read():
    memory = video_memory._DxgiReader().read()

    assert memory is not None
    assert memory.total > 0
    assert memory.used >= 0


class _FakeNvml:
    def __init__(self, init=0, total=8 * _GIB, free=6 * _GIB):
        self._init = init
        self._total = total
        self._free = free

    def nvmlInit_v2(self):
        return self._init

    def nvmlDeviceGetHandleByIndex_v2(self, index, _handle):
        assert index == 0
        return 0

    def nvmlDeviceGetMemoryInfo(self, _device, memory):
        memory._obj.total = self._total
        memory._obj.free = self._free
        memory._obj.used = self._total - self._free
        return 0


def test_nvml_says_what_s_free(mocker):
    mocker.patch.object(ctypes, "CDLL", return_value=_FakeNvml())

    read = video_memory._NvmlReader.reader()

    assert read() == VideoMemory(total=8 * _GIB, used=2 * _GIB)


def test_no_nvml_without_nvidia(mocker):
    mocker.patch.object(ctypes, "CDLL", side_effect=OSError("not found"))

    assert video_memory._NvmlReader.reader() is None


def test_no_nvml_with_its_driver_not_working(mocker):
    # NVML_ERROR_DRIVER_NOT_LOADED
    mocker.patch.object(ctypes, "CDLL", return_value=_FakeNvml(init=9))

    assert video_memory._NvmlReader.reader() is None


def test_nothing_read_on_macos(monkeypatch):
    monkeypatch.setattr(env, "IS_WINDOWS", False)
    monkeypatch.setattr(env, "IS_LINUX", False)

    assert video_memory._platform_reader() is None
