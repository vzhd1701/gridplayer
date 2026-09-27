import logging
import math
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path

from PyQt5.QtCore import QElapsedTimer, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QStackedLayout, QWidget

from gridplayer.params import env
from gridplayer.params.static import (
    HWCropBorderOffset,
    VideoAnchor,
    VideoAspect,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import (
    Rect,
    ViewPlacement,
    calc_moved_shift,
    calc_view_placement,
    calc_whole_placement,
)
from gridplayer.utils.qt import MILLISECONDS, QABC, qt_connect
from gridplayer.utils.screenshots import ScreenshotView
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

# How far off a whole pixel a picture edge can be and still count as on it,
# for the float error in working it out.
_PIXEL_SLACK = 1e-6

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
    frame: QWidget,
    clip: QWidget,
    surface: QWidget,
    offset: int,
    target: Rect | None = None,
    shown: Rect | None = None,
) -> None:
    """Place a native vout surface over the video, grown by `offset` each way.

    Over the target, the part of the frame the picture is shown in, or
    the whole frame where there is none to go by. VLC fills its window
    with the picture, centred, so the window is what puts the picture
    against a side or moves it. Grown on every side, it stays centred on
    the target, and VLC scales the picture up into the margin: past the
    frame where the picture reaches it, which hides VLC's edges there, and
    into the black around it where it does not.

    The surface is inside the clip, which cuts it to the frame, or, where
    VLC draws more of the picture than is on show, to `shown`, the part of
    the frame the picture is on show in.

    This is the only thing that positions a native surface: it is kept out of
    the frame layout (see VideoFrameVLC.is_native_surface), so a zero offset
    still has to size it.
    """
    width = frame.width()
    height = frame.height()
    if width <= 0 or height <= 0:
        return

    frame_rect = QRect(0, 0, width, height)
    surface_rect = frame_rect if target is None else _pixels_in(target)
    clip_rect = frame_rect if shown is None else frame_rect & _pixels_in(shown)

    if clip_rect.isEmpty():
        clip_rect = frame_rect

    clip.setGeometry(clip_rect)
    surface.setGeometry(
        surface_rect.adjusted(-offset, -offset, offset, offset).translated(
            -clip_rect.topLeft()
        )
    )


def _pixels_in(rect: Rect) -> QRect:
    """Every pixel of the rect, which a part of one still is."""

    x, y, width, height = rect
    left = math.floor(x + _PIXEL_SLACK)
    top = math.floor(y + _PIXEL_SLACK)
    right = max(math.ceil(x + width - _PIXEL_SLACK), left + 1)
    bottom = max(math.ceil(y + height - _PIXEL_SLACK), top + 1)

    return QRect(left, top, right - left, bottom - top)


def is_uncovered_fill_useful(is_letterboxed: bool = False) -> bool:
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

    Unless the surface is only over the picture, smaller than the frame or
    off its middle: the rest is then the frame's own to paint, for good,
    and Qt paints it in the palette colour.
    """
    return env.IS_WINDOWS or is_letterboxed


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
        self._is_blank = False

    def set_snapshot_file(self, snapshot_file: str):
        # failed snapshot
        if not snapshot_file:
            pixmap = QPixmap(1, 1)
            pixmap.fill(Qt.black)
            self.set_pixmap(pixmap)
            self._is_blank = True
            return

        self.set_pixmap(QPixmap(snapshot_file))

    def set_pixmap(self, pixmap: QPixmap | None):
        self._snapshot_pixmap = QPixmap(pixmap) if pixmap is not None else None
        self._is_blank = False

    def frame_image(self) -> QImage | None:
        """The frame being shown in place of the video, if there is one."""

        if self._snapshot_pixmap is None or self._is_blank:
            return None

        return self._snapshot_pixmap.toImage()

    def adjust_view(self, size: QSize, placement: ViewPlacement | None):
        """Put the snapshot where the video was on show.

        VLC snapshots the frame already cut down to the view, zoom and all,
        but not yet shaped for the screen, which under a rotation leaves it
        squeezed. So it is stretched over the part of the pane the video
        took up, rather than fitted to it.
        """
        if self._snapshot_pixmap is None:
            return

        if placement is None:
            self.setContentsMargins(0, 0, 0, 0)
            self.setPixmap(
                self._snapshot_pixmap.scaled(
                    size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            return

        x, y, width, height = (round(v) for v in placement.target)
        width, height = max(width, 1), max(height, 1)

        self.setContentsMargins(
            x,
            y,
            max(size.width() - x - width, 0),
            max(size.height() - y - height, 0),
        )
        self.setPixmap(
            self._snapshot_pixmap.scaled(
                width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
        )

    def reset(self):
        self._snapshot_pixmap = None
        self._is_blank = False


class VideoFrameVLC(QWidget, metaclass=QABC):
    time_changed = pyqtSignal(MILLISECONDS)
    playback_status_changed = pyqtSignal(bool)

    video_ready = pyqtSignal()
    tracks_changed = pyqtSignal()

    error = pyqtSignal(str)
    crash = pyqtSignal(str)
    update_status = pyqtSignal(str, int)

    # The frame a screenshot was asked for: the path of a PNG in a temp
    # folder, which the receiver removes once done with it, or a QImage
    # where VLC had no frame to give but one is on show all the same, or
    # None when there is nothing to save. Then the ScreenshotView to cut
    # it down to, or None to keep all of it.
    screenshot_taken = pyqtSignal(object, object)

    is_opengl: bool | None = None

    # Non-zero coalesces resize-driven view updates to one per this many ms.
    resize_view_interval_ms = 0

    # True when video_surface is a native window VLC presents into itself.
    # Such a surface is positioned by apply_vlc_hw_surface_geometry and is kept
    # out of the layout: QStackedLayout resets every item to the frame rect on
    # each resize, which undid the hw crop border offset between our updates
    # and left the native window jumping in and out of place during a drag.
    # So is video_clip, the window it is inside of, which cuts it down.
    is_native_surface = False

    def __init__(self, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._resize_view_clock = QElapsedTimer()
        self._resize_view_timer = QTimer(self)
        self._resize_view_timer.setSingleShot(True)
        self._resize_view_timer.timeout.connect(self._adjust_view_now)

        self._view = ViewParams()
        self._transform = VideoTransform.NONE

        self._is_status_change_in_progress = False
        self._is_cleanup_requested = False

        self.media: Media | None = None

        self.ui_setup()

        self.audio_only_placeholder = VideoStatus(parent=self, icon="audio-only")
        self.pause_snapshot = PauseSnapshot(parent=self)

        self.ui_helper_widgets()

        # the native surface's parent, made before it so it stacks the same
        self.video_clip = self.ui_video_clip() if self.is_native_surface else None

        self.video_surface = self.ui_video_surface()

        if self.is_native_surface:
            detach_native_surface_from_qt(self.video_surface)
            self.video_clip.setGeometry(self.rect())
            self.video_surface.setGeometry(self.video_clip.rect())
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

    def ui_video_clip(self) -> QWidget:
        """The window a native surface is inside of, to be cut down by.

        Nothing of its own shows: where the surface leaves it uncovered,
        Qt paints what is under it, the frame, as it did with no clip.
        """

        video_clip = QWidget(self)
        video_clip.setMouseTracking(True)
        video_clip.setWindowFlags(Qt.WindowTransparentForInput)
        video_clip.setAttribute(Qt.WA_TransparentForMouseEvents)

        return video_clip

    def _place_native_surface(self) -> None:
        """Put the surface VLC presents into over the video.

        See apply_vlc_hw_surface_geometry. Where VLC draws all of the frame
        (see calc_whole_placement), it is cut down to the part on show.
        Whatever of the frame it leaves uncovered is letterbox, filled
        black.
        """

        win = self.window()
        window_size = win.size() if win is not None else self.size()
        offset = vlc_hw_crop_border_offset(self.size(), window_size)
        placement = self._native_surface_placement()
        target = placement.target if placement is not None else None
        shown = None

        if self._is_drawn_whole():
            view_placement = self.view_placement()
            shown = view_placement.target if view_placement is not None else None

        apply_vlc_hw_surface_geometry(
            self, self.video_clip, self.video_surface, offset, target, shown
        )

        if not self.native_surface_rect().contains(self.rect()):
            self._fill_uncovered_black(is_letterboxed=True)

        self._log.debug(
            f"HW surface: offset={offset}"
            f", frame={self.size().width()}x{self.size().height()}"
            f", window={window_size.width()}x{window_size.height()}"
            f", clip={self.video_clip.geometry().getRect()}"
            f", surface={self.video_surface.geometry().getRect()}"
        )

    def native_surface_rect(self) -> QRect:
        """What of the frame the native surface covers, clip and all."""

        clip_rect = self.video_clip.geometry()
        surface_rect = self.video_surface.geometry().translated(clip_rect.topLeft())

        return clip_rect & surface_rect

    def _video_widget(self) -> QWidget:
        """What to hide for there to be no video on show."""

        return self.video_clip if self.is_native_surface else self.video_surface

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
            (self.video_driver.screenshot_taken, self._on_screenshot_taken),
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

    def _fill_uncovered_black(self, is_letterboxed: bool = False) -> None:
        """Paint whatever the native surface does not cover black.

        Two strips can show through mid-resize: the frame area the surface has
        not grown into yet (it is repositioned at most every
        resize_view_interval_ms), and the part of the surface VLC's own child
        window has not caught up to. Unpainted, both show QPalette.Window,
        which is near-white on a light theme and reads as the frame tearing.
        Black matches the letterbox the video already sits in, and where the
        surface is only over the picture it is that letterbox.

        Only once a video track is playing: on Windows the frame is left
        visible while the video loads (see VideoBlock._hide_video_driver), and
        filling it early would cover the loading status behind it.
        """
        if not self.is_native_surface:
            return

        if not is_uncovered_fill_useful(is_letterboxed):
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
            self.pause_snapshot.adjust_view(self.size(), self.view_placement())

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
        video = media_input.video

        self._view = ViewParams(
            video.aspect_mode,
            video.scale,
            video.crop,
            video.anchor,
            video.shift,
            video.is_shift_past_edges,
        )
        # changing it reloads the video, so it holds for as long as this does
        self._transform = video.transform

        self.video_driver.load_video(media_input)

    def load_video_finish(self, media: Media) -> None:
        self.media = media

        if self.media.is_audio_only:
            self._video_widget().hide()
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
        self.pause_snapshot.adjust_view(self.size(), self.view_placement())
        self.pause_snapshot.show()

        if snapshot_file:
            remove_snapshot_file(snapshot_file)

        if self._is_status_change_in_progress:
            self.video_driver.set_pause(True)

    def take_screenshot(self) -> None:
        self.video_driver.screenshot()

    def _on_screenshot_taken(self, frame_file: str) -> None:
        view = self.screenshot_view()

        if frame_file:
            self.screenshot_taken.emit(frame_file, view)
            return

        # A paused live stream is stopped, so VLC has no video output left
        # to grab from, while its last frame is still up on the pane.
        self.screenshot_taken.emit(self.shown_frame_image(), view)

    def screenshot_view(self) -> ScreenshotView | None:
        """How to make a screenshot the picture on show.

        The hardware drivers have VLC crop the frame to the view, zoom
        included, and its snapshot comes out cropped with it, with no way
        to ask for the whole frame. What is left to do is shaping a rotated
        frame back. Frames drawn here get the same cut on top, so a
        screenshot is the same picture whichever driver took it.
        """

        if self._is_drawn_whole():
            # all of the picture, for the pane to cut: cut it the same
            view = self._view
        else:
            view = None

        return ScreenshotView(
            self._pane_size(),
            view,
            self._transform,
            self._frame_size(),
            self._orientation(),
        )

    def _native_surface_placement(self) -> ViewPlacement | None:
        """What VLC is asked to draw into its window, and where that goes.

        The part on show, but all of a picture VLC turns or flips, which
        it crops wrong: see calc_whole_placement. The player makes the
        same choice from the same track.
        """

        return self._whole_placement() or self.view_placement()

    def _is_drawn_whole(self) -> bool:
        return self._whole_placement() is not None

    def _whole_placement(self) -> ViewPlacement | None:
        if self._orientation() == VideoTransform.NONE:
            return None

        return calc_whole_placement(
            self._view_frame_size(), self._pane_size(), self._view, self._transform
        )

    def _orientation(self) -> VideoTransform:
        """What the file says to turn or flip the picture by to show it."""

        track = self.media.cur_video_track if self.media else None

        return track.orientation if track is not None else VideoTransform.NONE

    def view_placement(self) -> ViewPlacement | None:
        """Where the video is on show in the pane, and what of it."""

        return calc_view_placement(
            self._view_frame_size(), self._pane_size(), self._view, self._transform
        )

    def shifted_by(self, steps_x: int, steps_y: int) -> VideoShift:
        """The shift a move of so many steps right and down comes to.

        Left and up are negative; see calc_moved_shift. What is kept is
        where the picture really goes.
        """

        return calc_moved_shift(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            (steps_x, steps_y),
            self._transform,
        )

    def _pane_size(self) -> tuple[int, int]:
        return self.size().width(), self.size().height()

    def _view_frame_size(self) -> tuple[int, int]:
        """The frame's size in the pixels the view is in."""

        return self._frame_size()

    def _frame_size(self) -> tuple[int, int]:
        """The frame's size as the video output gets it, (0, 0) if unknown.

        Turned where the file says to show it on its side, which VLC does
        before anything here sees it.
        """

        track = self.media.cur_video_track if self.media else None

        if track is None:
            return 0, 0

        width, height = track.video_dimensions

        return (height, width) if track.is_turned else (width, height)

    def shown_frame_image(self) -> QImage | None:
        """The frame on show when VLC can't give one, if there is any."""

        if not self.pause_snapshot.isVisible():
            return None

        return self.pause_snapshot.frame_image()

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
        self._view = self._view._replace(aspect=aspect)

        self.adjust_view()

    def set_scale(self, scale) -> None:
        self._view = self._view._replace(scale=scale)

        self.adjust_view()

    def set_crop(self, crop) -> None:
        self._view = self._view._replace(crop=crop)

        self.adjust_view()

    def set_anchor(self, anchor: VideoAnchor) -> None:
        self._view = self._view._replace(anchor=anchor)

        self.adjust_view()

    def set_shift(self, shift: VideoShift) -> None:
        self._view = self._view._replace(shift=shift)

        self.adjust_view()

    def set_shift_past_edges(self, is_shift_past_edges: bool) -> None:
        self._view = self._view._replace(is_shift_past_edges=is_shift_past_edges)

        self.adjust_view()

    def set_track_dimensions(self, width: int, height: int) -> None:
        if self.media is None or not width or not height:
            return

        size = (width, height)
        is_updated = False
        for track in self.media.video_tracks.values():
            if not all(track.video_dimensions):
                track.video_dimensions = size
                is_updated = True

        # the view here is worked out from them too
        if is_updated:
            self.adjust_view()

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
            self._video_widget().hide()
            self.audio_only_placeholder.show()
        else:
            self._fill_uncovered_black()
            self._video_widget().show()
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

    def set_deinterlace(self, deinterlace, mode):
        self.video_driver.set_deinterlace(deinterlace, mode)

    def set_audio_delay(self, delay_ms):
        self.video_driver.set_audio_delay(delay_ms)

    def set_subtitle_delay(self, delay_ms):
        self.video_driver.set_subtitle_delay(delay_ms)


class VideoFrameVLCProcess(VideoFrameVLC, ABC):
    def __init__(self, process_manager, **kwargs):
        self.process_manager = process_manager

        super().__init__(**kwargs)
