import logging
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path

from PyQt5.QtCore import QElapsedTimer, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QStackedLayout, QWidget

from gridplayer.params import env
from gridplayer.params.static import HWCropBorderOffset, VideoAspect, VideoCrop
from gridplayer.settings import Settings
from gridplayer.utils.qt import MILLISECONDS, QABC, QT_ASPECT_MAP, qt_connect
from gridplayer.vlc_player.static import Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_status import VideoStatus

DEFAULT_FPS = 25.0

# Pushing the view to a native vout is expensive: a SetWindowPos on the native
# surface plus three libvlc control calls, per video, and the surface is one
# VLC is actively presenting into. A resize drag delivers a resizeEvent per
# video per mouse step, so applying every one of them inline is what makes the
# window feel like it is resisting the drag. Frames with a native vout coalesce
# instead (see VideoFrameVLC._adjust_view_on_resize): the video trails the pane
# by up to this long mid-drag, the way VLC's own window does, and lands on the
# final size as soon as the drag stops.
NATIVE_VIEW_RESIZE_INTERVAL_MS = 100

# VLC's crop can leave a 2px black border around hardware output.
VLC_CROP_BORDER_PX = 2

# VLC's Direct3D11 hardware output on Windows can also leave the last few
# rows of its own video window unpainted at some pane sizes (up to ~7px,
# depending on the integer placement; NVIDIA drivers show it, AMD may not).
# A wider hidden margin keeps those rows outside the visible frame.
VLC_WINDOWS_CROP_BORDER_PX = 8

HW_CROP_BORDER_OFFSETS = {
    HWCropBorderOffset.DISABLED: 0,
    HWCropBorderOffset.PX2: 2,
    HWCropBorderOffset.PX4: 4,
    HWCropBorderOffset.PX6: 6,
    HWCropBorderOffset.PX8: 8,
    HWCropBorderOffset.PX10: 10,
    HWCropBorderOffset.PX12: 12,
}


def vlc_hw_crop_border_offset(frame_size: QSize, window_size: QSize) -> int:
    """How far to shift the native vout to hide VLC's hardware output edges.

    Hides VLC's 2px crop border on all platforms, plus the unpainted bottom
    rows of the Direct3D11 output on Windows.

    Explicit values from the hw_crop_border_offset setting bypass the
    platform defaults. With Auto, on Linux a window-filling surface at
    (-2, -2) sits outside the top-level window and KWin draws a seam, so
    the shift is skipped only when the frame already fills the window;
    interior grid tiles keep it.
    """
    setting = Settings().get("internal/hw_crop_border_offset")

    if setting != HWCropBorderOffset.AUTO:
        return HW_CROP_BORDER_OFFSETS[setting]

    if env.IS_WINDOWS:
        return VLC_WINDOWS_CROP_BORDER_PX

    if not env.IS_LINUX:
        return VLC_CROP_BORDER_PX

    fills_window = (
        frame_size.width() >= window_size.width() - VLC_CROP_BORDER_PX
        and frame_size.height() >= window_size.height() - VLC_CROP_BORDER_PX
    )
    return 0 if fills_window else VLC_CROP_BORDER_PX


def apply_vlc_hw_surface_geometry(
    frame: QWidget, surface: QWidget, offset: int
) -> None:
    """Place a native vout surface over the frame, shifted out by `offset`.

    This is the only thing that positions a native surface: it is kept out of
    the frame layout (see VideoFrameVLC.is_native_surface), so a zero offset
    still has to size it.
    """
    width = frame.width()
    height = frame.height()
    if width <= 0 or height <= 0:
        return

    surface.setGeometry(
        -offset,
        -offset,
        width + 2 * offset,
        height + 2 * offset,
    )


def is_uncovered_fill_useful() -> bool:
    """Whether painting under a native vout surface hides anything.

    On Windows the frame and the surface reach the screen together, so the
    strip the surface has not caught up to is the only thing showing and
    filling it black turns a near-white tear into letterbox.

    On X11 there is nothing left to hide. Once the surface is out of Qt's
    paint path (see detach_native_surface_from_qt) the strip it has not caught
    up to already comes up black, because the X server leaves the newly
    exposed part of a backgroundless window undefined. Filling measured
    identical to not filling, so leave X11 alone rather than repaint every
    cell for a colour it already has.
    """
    return env.IS_WINDOWS


def detach_native_surface_from_qt(surface: QWidget) -> None:
    """Stop Qt from painting the window VLC presents into.

    On X11 VLC presents into the window we hand it and creates nothing of its
    own: the surface has no children in the X tree. VLC's own interface embeds
    its vout the same way, but there the vout display ends up with a private
    child window, so Qt only ever paints around the video, never over it.

    We have no such child, and Qt keeps treating the surface as an ordinary
    widget, so every resize flushes its (empty) backing store across the
    window. That flush is the flicker, and its colour is whichever emptiness
    Qt is configured for: the palette background by default, black under
    WA_OpaquePaintEvent. Measured through a drag, both leave the cell ~90%
    filler and ~9% video.

    Disabling updates takes the widget out of Qt's paint path altogether.
    Nothing is flushed over the window, so the X server's NorthWest bit
    gravity keeps VLC's last frame in place until VLC draws the next one:
    same drag, ~80% video.

    X11 only. On Windows VLC creates its own child windows inside the surface
    and Qt's painting never reaches the screen to begin with, and on macOS the
    surface is a QMacCocoaViewContainer this has not been measured against.
    """
    if not env.IS_LINUX:
        return

    surface.setUpdatesEnabled(False)


def remove_snapshot_file(snapshot_file: str) -> None:
    """Remove a temp snapshot file and its directory, tolerating races.

    Never let a missing/already-deleted snapshot file raise inside a Qt slot:
    an unhandled exception in a slot aborts the whole app.
    """
    Path(snapshot_file).unlink(missing_ok=True)

    with suppress(OSError):
        Path(snapshot_file).parent.rmdir()


class PauseSnapshot(QLabel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color:black;")

        self._snapshot_pixmap: QPixmap | None = None

    def set_snapshot_file(self, snapshot_file: str):
        # failed snapshot
        if not snapshot_file:
            pixmap = QPixmap(1, 1)
            pixmap.fill(Qt.black)
            self.set_pixmap(pixmap)
            return

        self.set_pixmap(QPixmap(snapshot_file))

    def set_pixmap(self, pixmap: QPixmap | None):
        self._snapshot_pixmap = QPixmap(pixmap) if pixmap is not None else None

    def adjust_view(self, size: QSize, aspect, scale: float):
        if self._snapshot_pixmap is None:
            return

        # video_take_snapshot captures the displayed (already cropped) frame.
        scaled_size = QSize(
            int(size.width() * scale),
            int(size.height() * scale),
        )

        self.setPixmap(
            self._snapshot_pixmap.scaled(
                scaled_size, QT_ASPECT_MAP[aspect], Qt.SmoothTransformation
            )
        )

    def reset(self):
        self._snapshot_pixmap = None


class VideoFrameVLC(QWidget, metaclass=QABC):
    time_changed = pyqtSignal(MILLISECONDS)
    playback_status_changed = pyqtSignal(bool)

    video_ready = pyqtSignal()
    tracks_changed = pyqtSignal()

    error = pyqtSignal(str)
    crash = pyqtSignal(str)
    update_status = pyqtSignal(str, int)

    is_opengl: bool | None = None

    # Non-zero coalesces resize-driven view updates to one per this many ms.
    resize_view_interval_ms = 0

    # True when video_surface is a native window VLC presents into itself.
    # Such a surface is positioned by apply_vlc_hw_surface_geometry and is kept
    # out of the layout: QStackedLayout resets every item to the frame rect on
    # each resize, which undid the hw crop border offset between our updates
    # and left the native window jumping in and out of place during a drag.
    is_native_surface = False

    def __init__(self, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._resize_view_clock = QElapsedTimer()
        self._resize_view_timer = QTimer(self)
        self._resize_view_timer.setSingleShot(True)
        self._resize_view_timer.timeout.connect(self._adjust_view_now)

        self._aspect = VideoAspect.FIT
        self._scale = 1
        self._crop = VideoCrop(0, 0, 0, 0)

        self._is_status_change_in_progress = False
        self._is_cleanup_requested = False

        self.media: Media | None = None

        self.ui_setup()

        self.audio_only_placeholder = VideoStatus(parent=self, icon="audio-only")
        self.pause_snapshot = PauseSnapshot(parent=self)

        self.ui_helper_widgets()

        self.video_surface = self.ui_video_surface()

        if self.is_native_surface:
            detach_native_surface_from_qt(self.video_surface)
            self.video_surface.setGeometry(self.rect())
        else:
            self.layout().addWidget(self.video_surface)

        self.layout().addWidget(self.pause_snapshot)
        self.layout().addWidget(self.audio_only_placeholder)

        self.video_driver: VLCVideoDriver = self.driver_setup(vlc_options=vlc_options)

        self.driver_connect()

    @property
    def length(self) -> int:
        return self.media.length

    @property
    def is_live(self) -> bool:
        return self.media.is_live

    @property
    def is_live_video(self) -> bool:
        return not self.media.is_audio_only and self.media.is_live

    @property
    def is_video_initialized(self) -> bool:
        return self.media is not None

    @property
    def video_tracks(self):
        return self.media.video_tracks

    @property
    def cur_video_track_id(self) -> int | None:
        return self.media.cur_video_track_id

    @property
    def audio_tracks(self):
        return self.media.audio_tracks

    @property
    def audio_devices(self):
        return self.media.audio_devices

    @property
    def cur_audio_track_id(self) -> int | None:
        return self.media.cur_audio_track_id

    @property
    def external_audio_ids(self) -> tuple[int, ...]:
        return self.media.external_audio_ids

    @property
    def default_audio_track_id(self) -> int | None:
        return self.media.default_audio_track_id

    @property
    def subtitle_tracks(self):
        return self.media.subtitle_tracks

    @property
    def cur_subtitle_track_id(self) -> int | None:
        return self.media.cur_subtitle_track_id

    @property
    def external_subtitle_ids(self) -> tuple[int, ...]:
        return self.media.external_subtitle_ids

    @property
    def default_subtitle_track_id(self) -> int | None:
        return self.media.default_subtitle_track_id

    @property
    def has_subtitles(self) -> bool:
        return self.media.has_subtitles

    @abstractmethod
    def driver_setup(self, vlc_options) -> VLCVideoDriver: ...

    @abstractmethod
    def ui_video_surface(self) -> QWidget: ...

    def _apply_hw_crop_border_workaround(self) -> None:
        win = self.window()
        window_size = win.size() if win is not None else self.size()
        offset = vlc_hw_crop_border_offset(self.size(), window_size)
        apply_vlc_hw_surface_geometry(self, self.video_surface, offset)

        self._log.debug(
            f"HW crop border workaround: offset={offset}"
            f", frame={self.size().width()}x{self.size().height()}"
            f", window={window_size.width()}x{window_size.height()}"
            f", surface={self.video_surface.geometry().getRect()}"
        )

    def driver_connect(self) -> None:
        qt_connect(
            (
                self.video_driver.playback_status_changed,
                self.playback_status_changed_emit,
            ),
            (self.video_driver.time_changed, self.time_changed_emit),
            (self.video_driver.load_finished, self.load_video_finish),
            (self.video_driver.tracks_changed, self._on_tracks_changed),
            (self.video_driver.snapshot_taken, self.snapshot_taken),
            (self.video_driver.video_dimensions_changed, self.set_track_dimensions),
            (self.video_driver.error, self.error_emit),
            (self.video_driver.crash, self.crash_emit),
            (self.video_driver.update_status, self.update_status_emit),
        )

    def ui_setup(self) -> None:
        self.setWindowFlags(Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.setMouseTracking(True)

        QStackedLayout(self)
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setStackingMode(QStackedLayout.StackAll)

    def _fill_uncovered_black(self) -> None:
        """Paint whatever the native surface does not cover black.

        Two strips can show through mid-resize: the frame area the surface has
        not grown into yet (it is repositioned at most every
        resize_view_interval_ms), and the part of the surface VLC's own child
        window has not caught up to. Unpainted, both show QPalette.Window,
        which is near-white on a light theme and reads as the frame tearing.
        Black matches the letterbox the video already sits in.

        Only once a video track is playing: on Windows the frame is left
        visible while the video loads (see VideoBlock._hide_video_driver), and
        filling it early would cover the loading status behind it.
        """
        if not self.is_native_surface or not is_uncovered_fill_useful():
            return

        if self.autoFillBackground():
            return

        frame_palette = self.palette()
        frame_palette.setColor(self.backgroundRole(), Qt.black)
        self.setPalette(frame_palette)

        self.setAutoFillBackground(True)

    def ui_helper_widgets(self) -> None:
        self.audio_only_placeholder.setMouseTracking(True)
        self.audio_only_placeholder.setWindowFlags(Qt.WindowTransparentForInput)
        self.audio_only_placeholder.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.audio_only_placeholder.hide()

        self.pause_snapshot.setMouseTracking(True)
        self.pause_snapshot.setWindowFlags(Qt.WindowTransparentForInput)
        self.pause_snapshot.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pause_snapshot.hide()

    def crash_emit(self, exception_txt) -> None:
        self.crash.emit(exception_txt)

    def error_emit(self, error: str) -> None:
        self.cleanup()

        self.error.emit(error)

    def update_status_emit(self, status: str, percent) -> None:
        self.update_status.emit(status, percent)

    def cleanup_start(self) -> None:
        """Ask the player to release itself, without waiting for it.

        Lets a whole grid start releasing at once instead of pane by pane;
        see VideoBlocksManager.close_all.
        """
        if self._is_cleanup_requested:
            return

        self._is_cleanup_requested = True

        self.media = None

        self.video_driver.cleanup_start()

    def cleanup(self) -> None:
        self.cleanup_start()

        self.video_driver.cleanup_wait()

    def adjust_view(self) -> bool | None:
        if self._is_cleanup_requested:
            return True

        if not self.is_video_initialized:
            return False

        if self.media.is_audio_only:
            return True

        if self.pause_snapshot.isVisible():
            self.pause_snapshot.adjust_view(self.size(), self._aspect, self._scale)

    def resizeEvent(self, event) -> None:
        self._adjust_view_on_resize()

    def _adjust_view_on_resize(self) -> None:
        """Apply the view on resize, at most once per resize_view_interval_ms.

        Leading edge so a single resize is still instant, trailing edge so the
        size the drag ends on is never left stale.
        """
        interval = self.resize_view_interval_ms

        if not interval:
            self.adjust_view()
            return

        if self._resize_view_clock.isValid():
            since_last = self._resize_view_clock.elapsed()
        else:
            since_last = interval

        if since_last >= interval:
            self._adjust_view_now()
        elif not self._resize_view_timer.isActive():
            self._resize_view_timer.start(interval - since_last)

    def _adjust_view_now(self) -> None:
        self._resize_view_timer.stop()
        self._resize_view_clock.start()

        self.adjust_view()

    def playback_status_changed_emit(self, is_paused) -> None:
        if not self.is_video_initialized:
            return

        if not is_paused and self.pause_snapshot.isVisible():
            self.pause_snapshot.hide()
            self.pause_snapshot.reset()
            # Live pause is stop/play, which rebuilds the vout.
            self.adjust_view()

        self._is_status_change_in_progress = False

        self.playback_status_changed.emit(is_paused)

    def time_changed_emit(self, new_time) -> None:
        self.time_changed.emit(new_time)

    def load_video(self, media_input: MediaInput) -> None:
        self._aspect = media_input.video.aspect_mode
        self._scale = media_input.video.scale
        self._crop = media_input.video.crop

        self.video_driver.load_video(media_input)

    def load_video_finish(self, media: Media) -> None:
        self.media = media

        if self.media.is_audio_only:
            self.video_surface.hide()
            self.audio_only_placeholder.show()
        else:
            self._fill_uncovered_black()
            self.adjust_view()

        self.video_ready.emit()

    def play(self) -> None:
        if self._is_status_change_in_progress:
            return

        self._is_status_change_in_progress = True

        self.video_driver.play()

    def set_pause(self, is_paused) -> None:
        if not self.is_video_initialized:
            return

        if self._is_status_change_in_progress:
            return

        self._is_status_change_in_progress = True

        if self.is_live_video and is_paused:
            self.take_snapshot()
        else:
            self.video_driver.set_pause(is_paused)

    def take_snapshot(self) -> None:
        self.video_driver.snapshot()

    def snapshot_taken(self, snapshot_file: str) -> None:
        self.pause_snapshot.set_snapshot_file(snapshot_file)
        self.pause_snapshot.adjust_view(self.size(), self._aspect, self._scale)
        self.pause_snapshot.show()

        if snapshot_file:
            remove_snapshot_file(snapshot_file)

        if self._is_status_change_in_progress:
            self.video_driver.set_pause(True)

    def set_time(self, seek_ms) -> None:
        self.video_driver.set_time(seek_ms)

    def set_playback_rate(self, rate) -> None:
        self.video_driver.set_playback_rate(rate)

    def get_ms_per_frame(self) -> float:
        # Not rounded to whole milliseconds: at 23.976 fps a frame lasts
        # 41.7ms, and stepping by 41 lands short of the next frame often
        # enough that a press eventually shows the frame it started on.
        # A track can also come without a frame rate at all.
        fps = None
        if self.media.cur_video_track:
            fps = self.media.cur_video_track.fps

        return 1000 / (fps or DEFAULT_FPS)

    def audio_set_mute(self, is_muted) -> None:
        self.video_driver.audio_set_mute(is_muted)

    def audio_set_volume(self, volume) -> None:
        self.video_driver.audio_set_volume(volume)

    def set_aspect_ratio(self, aspect: VideoAspect) -> None:
        self._aspect = aspect

        self.adjust_view()

    def set_scale(self, scale) -> None:
        self._scale = scale

        self.adjust_view()

    def set_crop(self, crop) -> None:
        self._crop = crop

        self.adjust_view()

    def set_track_dimensions(self, width: int, height: int) -> None:
        if self.media is None or not width or not height:
            return

        size = (width, height)
        for track in self.media.video_tracks.values():
            if not all(track.video_dimensions):
                track.video_dimensions = size

    def _on_tracks_changed(self, media: Media) -> None:
        """Take a track list that grew after the load, without reloading."""

        self.media = media

        self.tracks_changed.emit()

    def set_audio_track(self, track_id):
        self.media.cur_audio_track_id = track_id

        self.video_driver.set_audio_track(track_id)

    def set_audio_device(self, device):
        self.video_driver.set_audio_device(device)

    def add_audio_slave(self, uri: str) -> None:
        self.video_driver.add_audio_slave(uri)

    def set_video_track(self, track_id):
        self.media.cur_video_track_id = track_id

        if track_id == -1:
            self.video_surface.hide()
            self.audio_only_placeholder.show()
        else:
            self._fill_uncovered_black()
            self.video_surface.show()
            self.audio_only_placeholder.hide()

        self.video_driver.set_video_track(track_id)

        self.adjust_view()

    def set_subtitle_track(self, track_id):
        self.media.cur_subtitle_track_id = track_id

        self.video_driver.set_subtitle_track(track_id)

    def add_subtitle_slave(self, uri: str) -> None:
        self.video_driver.add_subtitle_slave(uri)

    def set_audio_channel_mode(self, mode):
        self.video_driver.set_audio_channel_mode(mode)

    def set_audio_delay(self, delay_ms):
        self.video_driver.set_audio_delay(delay_ms)

    def set_subtitle_delay(self, delay_ms):
        self.video_driver.set_subtitle_delay(delay_ms)


class VideoFrameVLCProcess(VideoFrameVLC, ABC):
    def __init__(self, process_manager, **kwargs):
        self.process_manager = process_manager

        super().__init__(**kwargs)
