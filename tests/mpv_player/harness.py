"""The real player classes against the real libmpv, driven as the app drives them."""

import array
import itertools
import math
import multiprocessing
import time
from dataclasses import dataclass
from multiprocessing import Pipe
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.models.audio_selection import AudioDefault
from gridplayer.models.subtitle_selection import SubtitleDisabled
from gridplayer.models.video import Video
from gridplayer.mpv_player.rgb_buffer import FrameReader
from gridplayer.mpv_player.static import MediaInput
from gridplayer.multiprocess.safe_shared_memory import SafeSharedMemory
from gridplayer.params.static import VideoInitialState
from gridplayer.widgets.video_frame_mpv_hw import PlayerProcessSingleMPVHW
from gridplayer.widgets.video_frame_mpv_sw import PlayerProcessSingleMPVSW

PANE_SIZE = (640, 360)
PCM_RATE = 48000

open_sessions = []


def make_input(uri, **kwargs) -> MediaInput:
    is_live = kwargs.pop("is_live", False)
    audio_slave = kwargs.pop("audio_slave", None)
    sub_slaves = kwargs.pop("sub_slaves", ())
    headers = kwargs.pop("headers", {})
    paused = kwargs.pop("paused", True)
    position = kwargs.pop("position", 2000)

    video = Video(
        uri=uri if str(uri).startswith("http") else Path(uri),
        playback_state=(
            VideoInitialState.PAUSED if paused else VideoInitialState.PLAYING
        ),
        current_position=position,
        is_start_random=False,
        audio_selection=kwargs.pop("audio", AudioDefault()),
        subtitle_selection=kwargs.pop("sub", SubtitleDisabled()),
        **kwargs,
    )

    return MediaInput(
        uri=str(uri),
        is_live=is_live,
        is_audio_only=False,
        size=PANE_SIZE,
        video=video,
        selected_audio_slave=audio_slave,
        selected_subtitle_slaves=tuple(sub_slaves),
        http_headers=headers,
    )


class Session:
    """One player, in this process, and what it has told us so far."""

    def __init__(self, out: Path, extra=None, is_software=False):
        extra = extra or {}

        self.out = out
        self.is_software = is_software
        self.events = []
        self.lines = []
        self.crashed = None

        self.window = QWidget()
        self.window.setAttribute(Qt.WA_NativeWindow)
        self.window.resize(*PANE_SIZE)
        self.window.show()
        QApplication.processEvents()

        player_end, self.conn = Pipe()

        self._frame_lock = multiprocessing.Lock()
        self._frame_name = f"mpvtest{time.monotonic_ns()}"

        if is_software:
            init_data = {
                "shared_memory": SafeSharedMemory(self._frame_name, self._frame_lock)
            }
        else:
            init_data = {"win_id": int(self.window.winId())}

        base = PlayerProcessSingleMPVSW if is_software else PlayerProcessSingleMPVHW
        lines = self.lines

        class Player(base):
            def _mpv_options(self):
                return {**base._mpv_options(self), **extra}

            def _subtitle_style(self):
                return {}

            def _on_log(self, level, prefix, text):
                lines.append(f"{prefix}: {text.strip()}")
                base._on_log(self, level, prefix, text)

        self.player = Player(
            player_id="test",
            release_callback=lambda _id: self.player.cleanup_final(),
            init_data=init_data,
            crash_func=self._on_crash,
            pipe=(player_end, self.conn),
        )

        open_sessions.append(self)

    def _on_crash(self, text):
        self.crashed = text

    def cmd(self, name, *args):
        self.player.cmd_send_self(name, *args)

    def pump(self, seconds):
        end = time.monotonic() + seconds

        while time.monotonic() < end:
            while self.conn.poll():
                self.events.append(self.conn.recv())

            QApplication.processEvents()
            time.sleep(0.01)

    def wait(self, name, timeout=15, after=0):
        end = time.monotonic() + timeout

        while time.monotonic() < end:
            for event_name, args in self.events[after:]:
                if event_name == name:
                    return args

            self.pump(0.02)

        return None

    def mark(self) -> int:
        return len(self.events)

    def load(self, media_input, timeout=15):
        self.cmd("load_video", media_input)

        got = self.wait("load_video_done", timeout)

        return got[0] if got else None

    def screenshot(self) -> str:
        mark = self.mark()
        self.cmd("screenshot")

        got = self.wait("screenshot_taken_emit", 8, after=mark)

        return got[0] if got else ""

    def prop(self, name):
        return getattr(self.player._mpv, name.replace("-", "_"))

    def software_frame(self) -> QImage | None:
        """The latest frame out of the shared memory, the way the window reads it."""

        sizes = [args for name, args in self.events if name == "init_frame"]

        if not sizes:
            return None

        width, height, size = sizes[-1]

        reader = SafeSharedMemory(self._frame_name, self._frame_lock)
        reader.attach(size)

        frame = FrameReader().read(reader, width, height)
        image = QImage(bytes(frame), width, height, width * 4, QImage.Format_RGB32)
        image = image.copy()

        reader.close()

        return image

    def close(self):
        if self in open_sessions:
            open_sessions.remove(self)

        self.cmd("cleanup")

        if not self.is_software:
            self.wait("player_released", 8)

        self.player._thread.join(8)
        self.window.close()
        QApplication.processEvents()
        self.pump(0.05)


def pcm_options(target: Path) -> dict:
    target.unlink(missing_ok=True)

    return {
        "ao": "pcm",
        "ao_pcm_file": str(target),
        "ao_pcm_waveheader": "no",
        "audio_format": "s16",
        "audio_samplerate": str(PCM_RATE),
        "audio_channels": "stereo",
    }


@dataclass
class Sound:
    left: float
    right: float
    left_freq: float
    right_freq: float


def measure_sound(path: Path) -> Sound:
    """How loud each side ended up, and at what pitch, near the end of a run."""

    data = path.read_bytes()

    samples = array.array("h")
    samples.frombytes(data[: len(data) // 2 * 2])

    usable = samples[-PCM_RATE * 2 : -int(PCM_RATE * 0.2) * 2]
    left, right = usable[0::2], usable[1::2]

    return Sound(_rms(left), _rms(right), _freq(left), _freq(right))


def _rms(samples) -> float:
    return math.sqrt(sum(v * v for v in samples) / max(len(samples), 1)) / 32768


def _freq(samples) -> float:
    if not samples:
        return 0

    crossings = sum(1 for a, b in itertools.pairwise(samples) if (a < 0) != (b < 0))

    return crossings / 2 / (len(samples) / PCM_RATE)


def changed_pixels(path_a, path_b) -> int:
    """How many pixels of the lower half differ between two pictures."""

    a, b = QImage(str(path_a)), QImage(str(path_b))

    if a.isNull() or b.isNull() or a.size() != b.size():
        return -1

    return sum(
        1
        for y in range(a.height() // 2, a.height(), 2)
        for x in range(0, a.width(), 2)
        if a.pixel(x, y) != b.pixel(x, y)
    )


def is_red(image: QImage, x: int, y: int) -> bool:
    color = image.pixelColor(x, y)

    return color.red() > 180 and color.green() < 70 and color.blue() < 70
