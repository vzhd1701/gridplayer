import dataclasses
import logging
import math
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path

from PyQt5.QtCore import (
    QElapsedTimer,
    QMargins,
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
    SharedView,
    ViewPlacement,
    calc_dragged_shift,
    calc_followed_view,
    calc_moved_shift,
    calc_picture_rect,
    calc_selection_zoom,
    calc_shared_view,
    calc_shift_range,
    calc_view_geometry,
    calc_view_placement,
    calc_vlc_picture,
    calc_whole_placement,
    calc_zoomed_shift,
)
from gridplayer.utils.qt import MILLISECONDS, QABC, qt_connect
from gridplayer.utils.screenshots import ScreenshotView
from gridplayer.utils.win32_vlc_vout import (
    VlcPicture,
    fit_vlc_vout_windows,
    vlc_picture,
)
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

# How often to look for VLC's first picture of a video just loaded, how long
# to wait for it at most, and how long for it to go where the view puts it
# once it is up: see VideoFrameVLC.is_picture_pending. Measured opening a
# 3x3 grid, it was up 70-280ms after the load and in place within ~100ms.
FIRST_PICTURE_POLL_MS = 10
FIRST_PICTURE_TIMEOUT_MS = 1500
FIRST_PICTURE_PLACE_TIMEOUT_MS = 300

# How long to wait at most for a stream loaded with no frame size to start
# playing: see VideoFrameVLC.is_picture_pending. Measured opening 4 HLS
# streams at once, it was 750-1050ms after the load.
FIRST_PLAYBACK_TIMEOUT_MS = 3000

# VLC's crop can leave a 2px black border around hardware output.
VLC_CROP_BORDER_PX = 2

# VLC's Direct3D11 hardware output on Windows can also leave the last few
# rows of its own video window unpainted at some pane sizes (up to ~7px,
# depending on the integer placement; NVIDIA drivers show it, AMD may not).
# A wider hidden margin keeps those rows outside the visible frame.
VLC_WINDOWS_CROP_BORDER_PX = 8

# VLC's Direct3D11 output draws its picture into a buffer a whole number of
# 4-row blocks tall, and Windows squeezes that into the picture's window:
# where the window is not, the rows the buffer has past it come out black
# along the bottom, 4 - height % 4 of them. The margin hides them, until
# the picture is stretched before VLC draws one of the new size, as a cell
# going single: ~3x, past the margin, a black line under the video for a
# frame. Measured, on NVIDIA, the line at every size the picture window was
# 1 or 2 rows past a whole block and at none it was whole.
VLC_WINDOWS_PICTURE_ROW_BLOCK = 4

# How much the surface is grown by at most for that, across and down.
_PICTURE_BLOCK_MAX_PAD = 7

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


def calc_picture_block_padding(
    surface_size: QSize, ratio: float, picture_height
) -> QMargins:
    """What to grow a surface by for VLC's picture in it to be whole blocks.

    See VLC_WINDOWS_PICTURE_ROW_BLOCK. `picture_height` is how tall VLC
    makes its picture window in a window of the given size, in the window's
    own pixels, None where that is not known; the surface is `ratio` of
    those to its own. VLC fills its window across or down, whichever it
    reaches first, and the other side follows from the picture's shape, so
    either side can be what makes the height; the least growth that makes
    it whole is kept, split between both sides to keep the picture centred.
    Nothing where nothing within reach does, or where it is not known.
    """
    for total in range(2 * _PICTURE_BLOCK_MAX_PAD + 1):
        for pad_w in range(
            max(total - _PICTURE_BLOCK_MAX_PAD, 0),
            min(total, _PICTURE_BLOCK_MAX_PAD) + 1,
        ):
            pad_h = total - pad_w
            height = picture_height(
                _native_px(surface_size.width() + pad_w, ratio),
                _native_px(surface_size.height() + pad_h, ratio),
            )

            if height is None:
                return QMargins()

            if height % VLC_WINDOWS_PICTURE_ROW_BLOCK == 0:
                return QMargins(
                    pad_w // 2, pad_h // 2, pad_w - pad_w // 2, pad_h - pad_h // 2
                )

    return QMargins()


def _native_px(length: int, ratio: float) -> int:
    """A length or position in Qt pixels in the window's own, rounded the
    way Qt does: halves up, -13.5 to -13 too."""

    return math.floor(length * ratio + 0.5)


def apply_vlc_hw_surface_geometry(
    frame: QWidget,
    clip: QWidget,
    surface: QWidget,
    offset: int,
    target: Rect | None = None,
    shown: Rect | None = None,
    padding: QMargins | None = None,
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
    still has to size it. On Windows it sizes VLC's own windows inside it
    along with it (see fit_vlc_vout_windows).

    `padding` grows it a little more on top of that, see
    calc_picture_block_padding.
    """
    width = frame.width()
    height = frame.height()
    if width <= 0 or height <= 0:
        return

    frame_rect = QRect(0, 0, width, height)
    clip_rect = frame_rect if shown is None else frame_rect & _pixels_in(shown)

    if clip_rect.isEmpty():
        clip_rect = frame_rect

    surface_geometry = calc_vlc_hw_surface_rect(
        frame.size(), offset, target, padding
    ).translated(-clip_rect.topLeft())

    was_shown = _shown_of(clip.size(), surface.geometry())

    clip.setGeometry(clip_rect)
    surface.setGeometry(surface_geometry)

    fit_vlc_vout_windows(
        surface, was_shown, _shown_of(clip_rect.size(), surface_geometry)
    )


def calc_vlc_hw_surface_rect(
    frame_size: QSize,
    offset: int,
    target: Rect | None = None,
    padding: QMargins | None = None,
) -> QRect:
    """Where apply_vlc_hw_surface_geometry puts the surface, in the frame."""

    frame_rect = QRect(QPoint(0, 0), frame_size)
    surface_rect = frame_rect if target is None else _pixels_in(target)

    padding = padding or QMargins()

    return surface_rect.adjusted(
        -offset - padding.left(),
        -offset - padding.top(),
        offset + padding.right(),
        offset + padding.bottom(),
    )


def _shown_of(clip_size: QSize, surface_geometry: QRect) -> QRect:
    """The part of the surface the clip leaves on show, in its own coordinates."""

    shown = QRect(QPoint(0, 0), clip_size) & surface_geometry
    return shown.translated(-surface_geometry.topLeft())


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
        VideoFrameVLC._shown_picture_rect). Fitted into the pane, in the
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


class VideoFrameVLC(QWidget, metaclass=QABC):
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
    # Such a surface is positioned by apply_vlc_hw_surface_geometry and is kept
    # out of the layout: QStackedLayout resets every item to the frame rect on
    # each resize, which undid the hw crop border offset between our updates
    # and left the native window jumping in and out of place during a drag.
    # So is video_clip, the window it is inside of, which cuts it down.
    # Nothing the cell paints shows over such a video, so the cell puts its
    # overlay in a window of its own (see VideoBlock.init_overlay).
    is_native_surface = False

    def __init__(self, vlc_options, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        self._resize_view_clock = QElapsedTimer()
        self._resize_view_timer = QTimer(self)
        self._resize_view_timer.setSingleShot(True)
        self._resize_view_timer.timeout.connect(self._adjust_view_now)

        self._first_picture_clock = QElapsedTimer()
        self._picture_up_clock = QElapsedTimer()
        self._picture_in_place_clock = QElapsedTimer()
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
        # the frame points the last zoom about a point kept under it, and
        # what for: see zoomed_shift
        self._zoom_kept = None
        # another video's view, to follow once the frame's size is known
        self._shared_to_follow: SharedView | None = None

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
    def is_picture_pending(self) -> bool:
        """Loaded, with the video not on show as it should be yet.

        VLC's hardware output on Windows is black until VLC draws its first
        picture (see vlc_picture), which comes after the player says the
        video is loaded: a cell showed black for that long, its loading
        status taken off on the load. And that picture can be all of the
        frame, VLC taking up the view it was given only after it: then it
        moves its picture window to the view's shape and stretches that
        picture over it until it draws the next, a portrait video squashed
        flat across its cell for a frame.

        So until VLC's picture window is up where VLC puts the view's
        picture (see calc_vlc_picture), and has been for a frame. Or for at
        most FIRST_PICTURE_TIMEOUT_MS, or FIRST_PICTURE_PLACE_TIMEOUT_MS
        once it is up anywhere. Then picture_shown.

        Not always enough: VLC can draw that first picture whole into a
        window placed for the view, and keep it until the video starts
        playing. Seen for 100-180ms in 3 of 108 portrait videos opened at a
        saved position into landscape cells.

        A stream can load with no frame size, and VLC only finds it a few
        tens of ms after its video output is up. VLC shows the stream's
        first picture as soon as it is decoded and keeps it up, frozen,
        until playback proper starts, 650-850ms later on 4 HLS streams
        opened at once; and that picture is often drawn for the view worked
        out without the size, the whole frame with bars, then stretched
        over the view's shape once VLC takes the view up. Its window is
        where it should be then, so nothing here could tell. For one of
        those the wait goes on until the player says VLC is playing (see
        VlcPlayerBase._check_playback_started), on every platform, within
        FIRST_PLAYBACK_TIMEOUT_MS; and then, on Windows, as above. Not for
        one loaded paused, which never plays.
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

        offset, target, shown, padding = self._native_surface_layout()

        apply_vlc_hw_surface_geometry(
            self,
            self.video_clip,
            self.video_surface,
            offset,
            target,
            shown,
            padding,
        )

        if not self.native_surface_rect().contains(self.rect()):
            self._fill_uncovered_black(is_letterboxed=True)

        window_size = self._window_size()

        self._log.debug(
            f"HW surface: offset={offset}"
            f", frame={self.size().width()}x{self.size().height()}"
            f", window={window_size.width()}x{window_size.height()}"
            f", clip={self.video_clip.geometry().getRect()}"
            f", surface={self.video_surface.geometry().getRect()}"
        )

    def _native_surface_layout(
        self,
    ) -> tuple[int, Rect | None, Rect | None, QMargins]:
        """Where the native surface goes: apply_vlc_hw_surface_geometry's
        offset, target, part on show and padding."""

        offset = vlc_hw_crop_border_offset(self.size(), self._window_size())
        placement = self._native_surface_placement()
        target = placement.target if placement is not None else None
        shown = None

        if self._is_drawn_whole():
            view_placement = self.view_placement()
            shown = view_placement.target if view_placement is not None else None

        return offset, target, shown, self._picture_block_padding(target, offset)

    def _window_size(self) -> QSize:
        win = self.window()

        return win.size() if win is not None else self.size()

    def _picture_block_padding(self, target: Rect | None, offset: int) -> QMargins:
        """See calc_picture_block_padding: Windows only, where it is known.

        Not for a picture VLC turns as the file says (see
        calc_whole_placement): it turns it in placing it too.
        """
        if not env.IS_WINDOWS or target is None or self._is_drawn_whole():
            return QMargins()

        frame_size = self._view_frame_size()
        geometry = calc_view_geometry(
            frame_size, self._pane_size(), self._view, self._transform
        )

        def picture_height(width: int, height: int) -> int | None:
            picture = calc_vlc_picture(frame_size, geometry, (width, height))
            return picture[3] if picture is not None else None

        return calc_picture_block_padding(
            _pixels_in(target).size().grownBy(QMargins(offset, offset, offset, offset)),
            self.video_surface.devicePixelRatioF(),
            picture_height,
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

    def error_emit(self, error: str, vlc_lines: tuple[str, ...]) -> None:
        self.cleanup()

        self.error.emit(error, vlc_lines)

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

        # the playback is something to wait for wherever VLC draws
        if vlc_picture(self.video_surface) is None and not self._is_playback_awaited:
            return

        self._first_picture_clock.start()
        self._picture_up_clock.invalidate()
        self._picture_in_place_clock.invalidate()
        self._first_picture_timer.start()

    def _look_for_first_picture(self) -> None:
        if not self._is_first_picture_settled():
            return

        self._first_picture_timer.stop()

        self.picture_shown.emit()

    def _is_first_picture_settled(self) -> bool:
        if self._is_playback_awaited:
            if self._first_picture_clock.hasExpired(FIRST_PLAYBACK_TIMEOUT_MS):
                return True

            # the picture on show until then is the first one, frozen
            if not self._is_playback_started:
                return False

        elif self._first_picture_clock.hasExpired(FIRST_PICTURE_TIMEOUT_MS):
            return True

        picture = vlc_picture(self.video_surface)

        if picture is None:
            return True

        if picture.is_shown and not self._picture_up_clock.isValid():
            self._picture_up_clock.start()

        # where it goes is worked out from the frame's size
        if not all(self._frame_size()):
            return False

        if not self._is_picture_in_place(picture):
            self._picture_in_place_clock.invalidate()

            # not where it was worked out to go, and not going there
            return self._picture_up_clock.isValid() and (
                self._picture_up_clock.hasExpired(FIRST_PICTURE_PLACE_TIMEOUT_MS)
            )

        if not self._picture_in_place_clock.isValid():
            self._picture_in_place_clock.start()

        # VLC draws the view's picture there with the next frame
        return self._picture_in_place_clock.elapsed() > self.get_ms_per_frame()

    def _is_picture_in_place(self, picture: VlcPicture) -> bool:
        if not picture.is_shown:
            return False

        if picture.window_size != picture.surface_size:
            return False

        rect = self._vlc_picture_rect(picture.surface_size)

        return rect is None or picture.rect == rect

    def _vlc_picture_rect(self, window_size: tuple[int, int]) -> Rect | None:
        """Where VLC puts the view's picture in its window, if that is known.

        See calc_vlc_picture. Not for a picture VLC turns as the file says
        (see calc_whole_placement): it turns it in placing it too.
        """
        if self._is_drawn_whole():
            return None

        frame_size = self._view_frame_size()
        geometry = calc_view_geometry(
            frame_size, self._pane_size(), self._view, self._transform
        )

        return calc_vlc_picture(frame_size, geometry, window_size)

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

    def _shown_picture_rect(self) -> Rect | None:
        """Where the picture of the view is on show in the pane, as drawn.

        The view's target, but a native surface is grown past that (see
        apply_vlc_hw_surface_geometry) and VLC scales its picture up into
        the margin with it: 8px each way take a 550x500 cell's picture ~3%
        bigger than the target. So where VLC puts it in a surface that
        size (see calc_vlc_picture), past the pane's edges where it goes
        past them. Not for a picture VLC draws whole (see
        calc_whole_placement), nor where it is not known.
        """
        placement = self.view_placement()

        if placement is None:
            return None

        if not self.is_native_surface or self._is_drawn_whole():
            return placement.target

        # in the window's own pixels, as Qt puts it there: the clip, which
        # the surface is placed in, is the frame for a picture not drawn whole
        offset, target, _, padding = self._native_surface_layout()
        surface = calc_vlc_hw_surface_rect(self.size(), offset, target, padding)
        ratio = self.video_surface.devicePixelRatioF()
        window_w = _native_px(surface.width(), ratio)
        window_h = _native_px(surface.height(), ratio)

        picture = self._vlc_picture_rect((window_w, window_h))

        if picture is None:
            return placement.target

        x, y, width, height = picture

        # VLC's OpenGL output hands the picture's place, counted from the
        # top, to glViewport, which counts from the bottom: where the rows
        # left over are odd, the picture is a row lower than VLC worked out.
        # Measured letterboxed on X11.
        if env.IS_LINUX:
            y = window_h - y - height

        return (
            (_native_px(surface.x(), ratio) + x) / ratio,
            (_native_px(surface.y(), ratio) + y) / ratio,
            width / ratio,
            height / ratio,
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
        kept = (None, None)

        if self._zoom_kept is not None:
            kept_for, kept_points = self._zoom_kept

            if kept_for == (frame_size, pane_size, focus, self._view):
                kept = kept_points

        shift, kept = calc_zoomed_shift(
            frame_size,
            pane_size,
            self._view,
            scale,
            self._view_point(focus),
            self._transform,
            kept,
        )

        zoomed = self._view._replace(scale=scale, shift=shift)
        self._zoom_kept = ((frame_size, pane_size, focus, zoomed), kept)

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
        )

    def shared_view(self) -> SharedView | None:
        """Where the picture is, for other videos to show theirs alike.

        See calc_shared_view. None where it is not known.
        """

        return calc_shared_view(
            self._view_frame_size(), self._pane_size(), self._view, self._transform
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
            frame_size, self._pane_size(), self._view, shared, self._transform
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
            self._view_frame_size(), self._pane_size(), self._view, self._transform
        )

    def picture_rect(self) -> Rect | None:
        """Where all of the picture is, in the pane or past its edges."""

        return calc_picture_rect(
            self._view_frame_size(), self._pane_size(), self._view, self._transform
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

    def set_zoom(self, scale, shift: VideoShift) -> None:
        """Zoom and move the picture in one, for a zoom about a point.

        One after the other, the picture would be on show zoomed about the
        anchor for a moment before it moved: the hardware drivers place
        VLC's window at once, and the crop reaches the player after.
        """
        self._view = self._view._replace(scale=scale, shift=shift)

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

        if not is_updated:
            return

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

        # the picture on show is a new one now; see _is_first_picture_settled
        self._picture_up_clock.invalidate()

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


class VideoFrameVLCProcess(VideoFrameVLC, ABC):
    def __init__(self, process_manager, **kwargs):
        self.process_manager = process_manager

        super().__init__(**kwargs)
