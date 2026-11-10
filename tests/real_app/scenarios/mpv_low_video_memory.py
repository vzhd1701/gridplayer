"""Decode on the CPU set to Auto, on Hardware MPV: a video opened with no room left
for it in video memory decodes on the CPU and plays, the ones opened with room on
the GPU. What's read of the GPU is made up here, full or not as the scenario says.
Reloaded once there's room again, it goes back to the GPU."""

from gridplayer.utils import video_memory
from tests.real_app.scenarios.mpv_subtitles import _reload
from tests.real_app.scenarios.mpv_transport import _mpv

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "player/mpv_cpu_decoding": "auto",
}

_GIB = 1024**3


class _MadeUpGpu:
    def __init__(self):
        self.is_full = False

    def read(self):
        used = 4 * _GIB - 100 * 1024**2 if self.is_full else _GIB
        return video_memory.VideoMemory(total=4 * _GIB, used=used)


def scenario(d):
    gpu = _MadeUpGpu()
    video_memory._room = video_memory.VideoMemoryRoom(read=gpu.read)

    first_clip, second_clip, third_clip = d.media.clips

    first = _open_playing(d, first_clip)

    gpu.is_full = True
    second = _open_playing(d, second_clip)

    gpu.is_full = False
    third = _open_playing(d, third_clip)

    d.check("opened with room: on the GPU", _decoder(first) == "auto", _decoder(first))
    d.check("opened with none: on the CPU", _decoder(second) == "no", _decoder(second))
    d.check(
        "opened with room again: on the GPU", _decoder(third) == "auto", _decoder(third)
    )
    d.check("the one on the CPU says so", _mpv(second).hwdec_current == "no")

    _reload(d, second)
    d.wait_until(lambda: second.time > 1000, "it plays again", timeout=30)
    d.check(
        "reloaded with room: on the GPU", _decoder(second) == "auto", _decoder(second)
    )

    d.check(
        "all still playing",
        all(not cell.video_params.is_paused for cell in d.cells),
    )


def _open_playing(d, path):
    d.open(path)
    cell = d.wait_for_cell(path.name)
    d.wait_until(
        lambda: cell.is_playable and cell.time > 1000, f"{path.name} plays", timeout=30
    )

    return cell


def _decoder(cell) -> str:
    # a list from 0.36 on, as the option became one
    hwdec = _mpv(cell).hwdec

    return ",".join(hwdec) if isinstance(hwdec, list) else hwdec
