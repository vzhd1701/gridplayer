import dataclasses
import logging
import math
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path

from PyQt5.QtCore import (
    QElapsedTimer,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    QSizeF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QStackedLayout, QWidget

from gridplayer.models.chapter import Chapter
from gridplayer.mpv_player.static import Media, MediaInput
from gridplayer.mpv_player.video_driver_base import PlayerDriver
from gridplayer.params import env
from gridplayer.params.static import (
    VideoAnchor,
    VideoCellViewMode,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)
from gridplayer.utils.aspect_calc import (
    Rect,
    SharedView,
    ViewPlacement,
    calc_dragged_shift,
    calc_followed_view,
    calc_moved_shift,
    calc_picture_rect,
    calc_picture_shape,
    calc_ratio_crop,
    calc_selection_zoom,
    calc_shared_view,
    calc_shift_range,
    calc_shown_pixel_aspect,
    calc_view_placement,
    calc_whole_placement,
    calc_zoomed_shift,
)
from gridplayer.utils.qt import MILLISECONDS, QABC, qt_connect
from gridplayer.utils.screenshots import ScreenshotView
from gridplayer.widgets.video_status import VideoStatus

DEFAULT_FPS = 25.0

# Moving a native surface per video per mouse step is what makes a window feel
# like it is resisting a resize, so frames with one coalesce instead (see
# VideoFrame._adjust_view_on_resize): the video trails the pane by up to this
# long mid-drag and lands on the final size as soon as the drag stops.
NATIVE_VIEW_RESIZE_INTERVAL_MS = 100

# How often to look for a stream loaded with no frame size having started to
# play, and how long to wait for it at most: see VideoFrame.is_picture_pending.
FIRST_PICTURE_POLL_MS = 10
FIRST_PLAYBACK_TIMEOUT_MS = 3000

# How far off a whole pixel a picture edge can be and still count as on it,
# for the float error in working it out.
_PIXEL_SLACK = 1e-6


def apply_native_surface_geometry(
    frame: QWidget,
    clip: QWidget,
    surface: QWidget,
    target: Rect | None = None,
    shown: Rect | None = None,
) -> None:
    """Place a native surface over the video.

    Over the target, the part of the frame the picture is shown in, or the
    whole frame where there is none to go by. mpv fills its window with the
    picture, so the window is what puts the picture against a side or moves it.

    The surface is inside the clip, which cuts it to the frame, or, where mpv
    draws more of the picture than is on show, to `shown`.

    This is the only thing that positions a native surface: it is kept out of
    the frame layout (see VideoFrame.is_native_surface).
    """
    width = frame.width()
    height = frame.height()
    if width <= 0 or height <= 0:
        return

    frame_rect = QRect(0, 0, width, height)
    clip_rect = frame_rect if shown is None else frame_rect & _pixels_in(shown)

    if clip_rect.isEmpty():
        clip_rect = frame_rect

    surface_geometry = calc_native_surface_rect(frame.size(), target).translated(
        -clip_rect.topLeft()
    )

    clip.setGeometry(clip_rect)
    surface.setGeometry(surface_geometry)


def calc_native_surface_rect(frame_size: QSize, target: Rect | None = None) -> QRect:
    """Where apply_native_surface_geometry puts the surface, in the frame."""

    return QRect(QPoint(0, 0), frame_size) if target is None else _pixels_in(target)


def _pixels_in(rect: Rect) -> QRect:
    """Every pixel of the rect, which a part of one still is."""

    x, y, width, height = rect
    left = math.floor(x + _PIXEL_SLACK)
    top = math.floor(y + _PIXEL_SLACK)
    right = max(math.ceil(x + width - _PIXEL_SLACK), left + 1)
    bottom = max(math.ceil(y + height - _PIXEL_SLACK), top + 1)

    return QRect(left, top, right - left, bottom - top)


def is_uncovered_fill_useful(is_letterboxed: bool = False) -> bool:
    """Whether painting under a native surface hides anything.

    On Windows the frame and the surface reach the screen together, so a
    strip the surface has not caught up to would show. On X11 it comes up
    black by itself, unless the surface is only over the picture: the rest
    is then the frame's own to paint.
    """
    return env.IS_WINDOWS or is_letterboxed


def detach_native_surface_from_qt(surface: QWidget) -> None:
    """Stop Qt from painting over the window mpv presents into, on X11.

    Qt treats the surface as an ordinary widget and flushes its empty backing
    store across the window on every resize, which is the flicker.
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


class PauseSnapshot(QWidget):
    """The frame a paused live stream stopped on, up in place of the video."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setAttribute(Qt.WA_OpaquePaintEvent)

        self._snapshot_pixmap: QPixmap | None = None
        self._is_blank = False

        # the snapshot at the size it goes up at, and where in here
        self._picture: QPixmap | None = None
        self._picture_pos = QPointF()

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

    def adjust_view(self, size: QSize, rect: Rect | None):
        """Put the snapshot where the video was on show.

        VLC snapshots the frame already cut down to the view, zoom and all,
        but not yet shaped for the screen, which under a rotation leaves it
        squeezed. So it is stretched over `rect`, where the video's picture
        was on show in the pane, rather than fitted to it: past the pane's
        edges where VLC drew it past them (see
        VideoFrame._shown_picture_rect). Fitted into the pane, in the
        middle, where that is not known.
        """
        if self._snapshot_pixmap is None:
            return

        if rect is None:
            fitted = self._snapshot_pixmap.size().scaled(size, Qt.KeepAspectRatio)
            rect = (
                (size.width() - fitted.width()) // 2,
                (size.height() - fitted.height()) // 2,
                fitted.width(),
                fitted.height(),
            )

        # edges on whole pixels of the screen's
        ratio = self.devicePixelRatioF()
        x, y, width, height = rect
        left, top = round(x * ratio), round(y * ratio)
        right, bottom = round((x + width) * ratio), round((y + height) * ratio)

        self._picture = self._snapshot_pixmap.scaled(
            max(right - left, 1),
            max(bottom - top, 1),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        self._picture.setDevicePixelRatio(ratio)
        self._picture_pos = QPointF(left / ratio, top / ratio)

        self.update()

    def picture_rect(self) -> QRectF | None:
        """Where the snapshot is up, in this widget, if it is."""

        if self._picture is None:
            return None

        size = QSizeF(self._picture.size()) / self._picture.devicePixelRatio()

        return QRectF(self._picture_pos, size)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)

        if self._picture is not None:
            painter.drawPixmap(self._picture_pos, self._picture)

    def reset(self):
        self._snapshot_pixmap = None
        self._picture = None
        self._is_blank = False


class VideoFrame(QWidget, metaclass=QABC):
    time_changed = pyqtSignal(MILLISECONDS)
    playback_status_changed = pyqtSignal(bool)

    video_ready = pyqtSignal()
    # The picture of the video just loaded is on show, where it comes only
    # after video_ready: see is_picture_pending.
    picture_shown = pyqtSignal()
    tracks_changed = pyqtSignal()
    chapters_changed = pyqtSignal()
    # The view taken after another video's once the frame's size came in,
    # a ViewParams: see follow_view.
    view_followed = pyqtSignal(object)
    # How wide the picture is for its height, now that it is known or
    # since it changed: see picture_shape.
    picture_shape_changed = pyqtSignal(float)

    # the error, and what VLC said went wrong with the video as it did
    error = pyqtSignal(str, tuple)
    crash = pyqtSignal(str)
    update_status = pyqtSignal(str, int)

    # The frame a screenshot was asked for: the path of a PNG in a temp
    # folder, which the receiver removes once done with it, or a QImage
    # where VLC had no frame to give but one is on show all the same, or
    # None when there is nothing to save. Then the ScreenshotView to cut
    # it down to, or None to keep all of it.
    screenshot_taken = pyqtSignal(object, object)

    # Non-zero coalesces resize-driven view updates to one per this many ms.
    resize_view_interval_ms = 0

    # True when video_surface is a native window VLC presents into itself.
    # Such a surface is positioned by apply_native_surface_geometry and is kept
    # out of the layout: QStackedLayout resets every item to the frame rect on
    # each resize, which undid the hw crop border offset between our updates
    # and left the native window jumping in and out of place during a drag.
    # So is video_clip, the window it is inside of, which cuts it down.
    # Nothing the cell paints shows over such a video, so the cell puts its
    # overlay in a window of its own (see VideoBlock.init_overlay).
    is_native_surface = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._resize_view_clock = QElapsedTimer()
        self._resize_view_timer = QTimer(self)
        self._resize_view_timer.setSingleShot(True)
        self._resize_view_timer.timeout.connect(self._adjust_view_now)

        self._first_picture_clock = QElapsedTimer()
        # loaded with no frame size, as a stream can be, to play, and playing
        # since: see is_picture_pending
        self._is_paused_on_load = False
        self._is_playback_awaited = False
        self._is_playback_started = False
        self._first_picture_timer = QTimer(self)
        self._first_picture_timer.setInterval(FIRST_PICTURE_POLL_MS)
        self._first_picture_timer.timeout.connect(self._look_for_first_picture)

        self._view = ViewParams()
        self._transform = VideoTransform.NONE
        # the aspect ratio and the crop shape the video's list says, shown
        # where none is picked
        self._list_ratios = ("", "")
        # the frame points the last zoom about a point kept under it, and
        # what for: see zoomed_shift
        self._zoom_kept = None
        # another video's view, to follow once the frame's size is known
        self._shared_to_follow: SharedView | None = None
        # the picture's shape last said with picture_shape_changed
        self._picture_shape: float | None = None

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

        # The layout shows the first widget it is given, as its current one,
        # and a native surface is kept out of it: the snapshot, black over
        # the video until it played, which a video loaded paused never did.
        self.pause_snapshot.hide()

        self.video_driver: PlayerDriver = self.driver_setup()

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
    def is_picture_pending(self) -> bool:
        """Loaded with no frame size, as a stream can be, and not playing yet.

        Until then the picture on show can be the wrong shape, so a cell keeps
        its loading status up, for at most FIRST_PLAYBACK_TIMEOUT_MS.
        """
        return self._first_picture_timer.isActive()

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

    @property
    def chapters(self) -> tuple[Chapter, ...]:
        return self.media.chapters

    @abstractmethod
    def driver_setup(self) -> PlayerDriver: ...

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
        """Put the surface mpv presents into over the video.

        See apply_native_surface_geometry. Where mpv draws all of the frame
        (see calc_whole_placement), it is cut down to the part on show.
        Whatever of the frame it leaves uncovered is letterbox, filled black.
        """

        target, shown = self._native_surface_layout()

        apply_native_surface_geometry(
            self, self.video_clip, self.video_surface, target, shown
        )

        if not self.native_surface_rect().contains(self.rect()):
            self._fill_uncovered_black(is_letterboxed=True)

    def _native_surface_layout(self) -> tuple[Rect | None, Rect | None]:
        """Where the native surface goes, and the part of it on show."""

        placement = self._native_surface_placement()
        target = placement.target if placement is not None else None
        shown = None

        if self._is_drawn_whole():
            view_placement = self.view_placement()
            shown = view_placement.target if view_placement is not None else None

        return target, shown

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
            (self.video_driver.chapters_changed, self._on_chapters_changed),
            (self.video_driver.snapshot_taken, self.snapshot_taken),
            (self.video_driver.screenshot_taken, self._on_screenshot_taken),
            (self.video_driver.video_dimensions_changed, self.set_track_dimensions),
            (self.video_driver.playback_started, self._on_playback_started),
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

    def error_emit(self, error: str, player_lines: tuple[str, ...]) -> None:
        self.cleanup()

        self.error.emit(error, player_lines)

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

        self._first_picture_timer.stop()

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

        # the margins that cut it to a shape go by the frame, only known
        # once loaded, and by its shape, which the aspect ratio changes
        self._view = self._view._replace(crop=self.shown_crop())

        shape = self.picture_shape()
        if shape is not None and shape != self._picture_shape:
            self._picture_shape = shape
            self.picture_shape_changed.emit(shape)

        if self.pause_snapshot.isVisible():
            self.pause_snapshot.adjust_view(self.size(), self._shown_picture_rect())

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

        self._view = media_input.view
        self._list_ratios = (media_input.list_aspect_ratio, media_input.list_crop_ratio)
        # changing it reloads the video, so it holds for as long as this does
        self._transform = video.transform
        self._shared_to_follow = None

        self._is_paused_on_load = video.is_paused
        self._is_playback_started = False

        self.video_driver.load_video(media_input)

    def load_video_finish(self, media: Media) -> None:
        self.media = media

        if self.media.is_audio_only:
            self._video_widget().hide()
            self.audio_only_placeholder.show()
        else:
            self._fill_uncovered_black()
            self.adjust_view()
            self._wait_for_first_picture()

        self.video_ready.emit()

    def _wait_for_first_picture(self) -> None:
        if not self.is_native_surface:
            return

        # one loaded paused never plays to wait for
        self._is_playback_awaited = (
            not all(self._frame_size()) and not self._is_paused_on_load
        )

        if not self._is_playback_awaited:
            return

        self._first_picture_clock.start()
        self._first_picture_timer.start()

    def _look_for_first_picture(self) -> None:
        if not self._is_first_picture_settled():
            return

        self._first_picture_timer.stop()

        self.picture_shown.emit()

    def _is_first_picture_settled(self) -> bool:
        if self._first_picture_clock.hasExpired(FIRST_PLAYBACK_TIMEOUT_MS):
            return True

        return self._is_playback_started

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
        self.pause_snapshot.adjust_view(self.size(), self._shown_picture_rect())
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
            self._pixel_aspect(),
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
        # mpv crops before it rotates, so a picture turned or flipped either
        # by the file or by the viewer is drawn whole
        is_transformed = self._transform not in {None, VideoTransform.NONE}

        if self._orientation() == VideoTransform.NONE and not is_transformed:
            return None

        return calc_whole_placement(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def _orientation(self) -> VideoTransform:
        """What the file says to turn or flip the picture by to show it."""

        track = self.media.cur_video_track if self.media else None

        return track.orientation if track is not None else VideoTransform.NONE

    def view_placement(self) -> ViewPlacement | None:
        """Where the video is on show in the pane, and what of it."""

        return calc_view_placement(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def _shown_picture_rect(self) -> Rect | None:
        """Where the picture of the view is on show in the pane."""

        placement = self.view_placement()

        return placement.target if placement is not None else None

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
            pixel_aspect=self._pixel_aspect(),
        )

    def dragged_shift(
        self, moved_x: float, moved_y: float
    ) -> tuple[VideoShift, tuple[float, float]]:
        """The shift a drag of so many pane pixels takes the picture to.

        Right and down, left and up negative, with what is left over of
        them; see calc_dragged_shift.
        """

        return calc_dragged_shift(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            (moved_x, moved_y),
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def zoomed_shift(self, scale: float, focus: tuple[float, float]) -> VideoShift:
        """The shift a zoom to `scale` about a pane point comes to.

        See calc_zoomed_shift. The point is where the viewer sees it, on
        the picture as drawn (see _view_point). The frame points it keeps
        under it are kept here, for the next zoom to go on from where it
        is about the same point of the same picture in the same pane: one
        wheel notch after another with the pointer still.
        """

        frame_size, pane_size = self._view_frame_size(), self._pane_size()
        shape = self._pixel_aspect()
        kept = (None, None)

        if self._zoom_kept is not None:
            kept_for, kept_points = self._zoom_kept

            if kept_for == (frame_size, pane_size, focus, self._view, shape):
                kept = kept_points

        shift, kept = calc_zoomed_shift(
            frame_size,
            pane_size,
            self._view,
            scale,
            self._view_point(focus),
            self._transform,
            kept,
            pixel_aspect=shape,
        )

        zoomed = self._view._replace(scale=scale, shift=shift)
        self._zoom_kept = ((frame_size, pane_size, focus, zoomed, shape), kept)

        return shift

    def selection_zoom(self, selection: Rect) -> tuple[float, VideoShift] | None:
        """The zoom and shift a part of the pane selected comes to.

        See calc_selection_zoom. The part is where the viewer sees it, on
        the picture as drawn (see _view_point), and (x, y, width, height).
        It goes into as much of the pane as is on show of the picture as
        the view has it: drawn bigger, the selection fitted into all of the
        pane would go past its edges as drawn, ~8 pixels each side.
        """

        pane_w, pane_h = self._pane_size()
        x, y, width, height = selection

        left, top = self._view_point((x, y))
        right, bottom = self._view_point((x + width, y + height))

        room_left, room_top = self._view_point((0, 0))
        room_right, room_bottom = self._view_point((pane_w, pane_h))

        return calc_selection_zoom(
            self._view_frame_size(),
            (pane_w, pane_h),
            self._view,
            (left, top, right - left, bottom - top),
            self._transform,
            room=(room_right - room_left, room_bottom - room_top),
            pixel_aspect=self._pixel_aspect(),
        )

    def shared_view(self) -> SharedView | None:
        """Where the picture is, for other videos to show theirs alike.

        See calc_shared_view. None where it is not known.
        """

        return calc_shared_view(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def follow_view(self, shared: SharedView) -> ViewParams | None:
        """Show the part of the picture another video shows of its own.

        See calc_followed_view. Where the frame's size is not known yet, as
        it is not for a stream until its first picture, kept until it is
        (see set_track_dimensions), view_followed saying what it came to.
        The view, None where it is kept for later.
        """

        view = self._followed_view(shared)

        if view is None:
            self._shared_to_follow = shared
            return None

        self._shared_to_follow = None

        # unchanged where this one's edges hold it, the other dragged on
        if view != self._view:
            self._view = view
            self.adjust_view()

        return view

    def _followed_view(self, shared: SharedView) -> ViewParams | None:
        frame_size = self._view_frame_size()

        # the software drivers know the frame's size from a frame, which
        # has not come yet where a video has only just loaded
        if not all(frame_size):
            frame_size = self._frame_size()

        return calc_followed_view(
            frame_size,
            self._pane_size(),
            self._view,
            shared,
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def shown_picture_area(self) -> Rect | None:
        """The part of the pane the picture is drawn over, None for none.

        As the viewer sees it (see _shown_picture_rect), within the pane.
        """

        shown = self._shown_picture_rect()

        if shown is None:
            return None

        x, y, width, height = shown
        pane_w, pane_h = self._pane_size()

        left, top = max(x, 0), max(y, 0)
        right, bottom = min(x + width, pane_w), min(y + height, pane_h)

        if right <= left or bottom <= top:
            return None

        return left, top, right - left, bottom - top

    def _view_point(self, point: tuple[float, float]) -> tuple[float, float]:
        """Where a point of the pane is in the view's placement of the picture.

        The same point, but on a native surface, where VLC draws the
        picture a little bigger than the view has it (see
        _shown_picture_rect): what is on show at a point off the middle is
        what the view has a little nearer the middle. Zoomed about the
        point as drawn instead, the part of the picture under the pointer
        would slide away from it, by ~40 pixels at 10x near a side of a
        900 pixel cell.
        """

        placement = self.view_placement()
        shown = self._shown_picture_rect()

        if placement is None or shown is None:
            return point

        target_x, target_y, target_w, target_h = placement.target
        shown_x, shown_y, shown_w, shown_h = shown

        if shown_w <= 0 or shown_h <= 0:
            return point

        return (
            target_x + (point[0] - shown_x) * target_w / shown_w,
            target_y + (point[1] - shown_y) * target_h / shown_h,
        )

    def shift_range(self) -> tuple[VideoShift, VideoShift]:
        """The least and the most the shift can be; see calc_shift_range."""

        return calc_shift_range(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def picture_shape(self) -> float | None:
        """How wide the picture is for its height on screen: turned, in the
        aspect ratio picked and cut by the crop, at no zoom. None until the
        frame's size is known."""

        return calc_picture_shape(
            self._frame_size(),
            self._view.crop,
            self._transform,
            self._pixel_aspect(),
        )

    def picture_rect(self) -> Rect | None:
        """Where all of the picture is, in the pane or past its edges."""

        return calc_picture_rect(
            self._view_frame_size(),
            self._pane_size(),
            self._view,
            self._transform,
            pixel_aspect=self._pixel_aspect(),
        )

    def _pane_size(self) -> tuple[int, int]:
        return self.size().width(), self.size().height()

    def _view_frame_size(self) -> tuple[int, int]:
        """The frame's size in the pixels the view is in."""

        return self._frame_size()

    def _pixel_aspect(self) -> float:
        """How wide a frame pixel is for its height, in the frame as it is
        shown: see VideoTrack.pixel_aspect. The aspect ratio picked makes
        it whatever gives the picture that shape."""

        track = self.media.cur_video_track if self.media else None

        return calc_shown_pixel_aspect(
            self._frame_size(),
            self._transform,
            self._view.aspect_ratio,
            track.pixel_aspect if track is not None else 1,
        )

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

    def set_time_keyframe(self, seek_ms) -> None:
        self.video_driver.set_time_keyframe(seek_ms)

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

    def set_cell_view_mode(self, mode: VideoCellViewMode) -> None:
        self._view = self._view._replace(cell_view_mode=mode)

        self.adjust_view()

    def set_fill_limit(self, fill_limit: int) -> None:
        """See ViewParams.fill_limit. Before the video is loaded too: until
        then, nothing is shown to change, and it loads with its own."""

        self._view = self._view._replace(fill_limit=fill_limit)

        if self.is_video_initialized:
            self.adjust_view()

    def set_aspect_ratio(self, aspect_ratio: str) -> None:
        self._repick(aspect_ratio=aspect_ratio)

        self.adjust_view()

    def forget_list_ratios(self, **picked) -> None:
        """The video is off its list: the shapes it said are shown no more,
        but where picked, these too."""

        self._list_ratios = ("", "")
        self._repick(**picked)

        self.adjust_view()

    def _repick(self, **picked) -> None:
        """The view with these picked, the list's shapes shown where none is."""

        self._view = (
            self._view.picked()._replace(**picked).with_list(*self._list_ratios)
        )

    def set_scale(self, scale) -> None:
        self._view = self._view._replace(scale=scale)

        self.adjust_view()

    def set_zoom(self, scale, shift: VideoShift) -> None:
        """Zoom and move the picture in one, for a zoom about a point.

        One after the other, the picture would be on show zoomed about the
        anchor for a moment before it moved: the hardware drivers place
        VLC's window at once, and the crop reaches the player after.
        """
        self._view = self._view._replace(scale=scale, shift=shift)

        self.adjust_view()

    def set_crop(self, crop) -> None:
        """Cut the picture by these margins, and to no shape: none at all
        leaves it to the list."""

        self._repick(crop=crop, crop_ratio="")

        self.adjust_view()

    def set_crop_ratio(self, crop_ratio: str) -> None:
        """Cut the picture to this shape, as it is shown: "2.35:1", or
        empty for none, leaving it to the list, and by no margins of its own."""

        self._repick(crop=VideoCrop(0, 0, 0, 0), crop_ratio=crop_ratio)

        self.adjust_view()

    def shown_crop(self) -> VideoCrop:
        """The margins the picture is cut by: its own, or those that cut it
        to the shape picked or its list's, none until its frame is known."""

        if not self._view.crop_ratio:
            return self._view.crop

        return calc_ratio_crop(
            self._frame_size(),
            self._transform,
            self._view.crop_ratio,
            self._pixel_aspect(),
        )

    def set_anchor(self, anchor: VideoAnchor) -> None:
        self._view = self._view._replace(anchor=anchor)

        self.adjust_view()

    def set_shift(self, shift: VideoShift) -> None:
        self._view = self._view._replace(shift=shift)

        self.adjust_view()

    def set_shift_past_edges(self, is_shift_past_edges: bool) -> None:
        self._view = self._view._replace(is_shift_past_edges=is_shift_past_edges)

        self.adjust_view()

    def set_track_dimensions(
        self, width: int, height: int, sar: tuple[int, int] | None = None
    ) -> None:
        """What the tracks were read without, found once the video plays:
        the size, and how wide its pixels are for their height.

        Said only when the player has found something. A player in this
        process has put it on the tracks already, being the same tracks,
        so the view is worked out again whether anything is left to fill
        in here or not.
        """

        if self.media is None:
            return

        for track in self.media.video_tracks.values():
            if width and height and not all(track.video_dimensions):
                track.video_dimensions = (width, height)

            if sar is not None and track.sar is None:
                track.sar = sar

        if self._shared_to_follow is not None:
            view = self._followed_view(self._shared_to_follow)

            if view is not None:
                self._shared_to_follow = None
                self._view = view
                self.view_followed.emit(view)

        # the view here is worked out from them too
        self.adjust_view()

    def _on_playback_started(self) -> None:
        self._is_playback_started = True

    def _on_tracks_changed(self, media: Media) -> None:
        """Take a track list that grew after the load, without reloading."""

        self.media = media

        self.tracks_changed.emit()

    def _on_chapters_changed(self, chapters: tuple) -> None:
        """Take chapters the file listed only after the load was done."""

        # the player only sends these once it has reported the load, but
        # a video let go of in between has no media left to put them on
        if self.media is None:
            return

        self.media = dataclasses.replace(self.media, chapters=chapters)

        self.chapters_changed.emit()

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


class VideoFrameProcess(VideoFrame, ABC):
    def __init__(self, process_manager, **kwargs):
        self.process_manager = process_manager

        super().__init__(**kwargs)
