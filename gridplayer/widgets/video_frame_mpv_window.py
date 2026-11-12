"""MPV's third output: mpv draws into a native window a cell itself, with its
own video output (Direct3D 11 on Windows), rather than through the render
API into frames the window paints. Nothing is read back or copied, and
hardware decoding stays on the GPU where OpenGL would take a copy.

The surface is VLC Hardware's: a native window over the picture, inside a
clip that cuts it to the cell, kept out of the layout, and the cell's overlay
in a window of its own on top, which takes the mouse. mpv makes a window of
its own inside the surface, on a thread of its own, and fills it.

mpv can still be drawing into it while it terminates, after the frame has
gone. So the clip, with the surface in it, is taken out of the frame as the
video goes and kept, hidden, until mpv is done with it.
"""

import math
from contextlib import suppress
from typing import NamedTuple

from PyQt5.QtCore import QMargins, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QWidget

from gridplayer.mpv_player.player import MpvPlayer, WindowPicture
from gridplayer.mpv_player.renderer import MpvRenderService
from gridplayer.mpv_player.subtitles import subtitle_view
from gridplayer.params import env
from gridplayer.params.static import ROTATION_TRANSFORMS
from gridplayer.utils.aspect_calc import Rect, ViewPlacement
from gridplayer.utils.screenshots import ScreenshotView
from gridplayer.vlc_player.static import MediaInput
from gridplayer.widgets.video_frame_mpv import MpvFrame, VideoDriverMpv, shown_flip
from gridplayer.widgets.video_frame_vlc_base import (
    PICTURE_BLOCK_MAX_PAD,
    VLC_WINDOWS_PICTURE_ROW_BLOCK,
    VideoFrameVLC,
    calc_vlc_hw_clip_rect,
    calc_vlc_hw_surface_rect,
    fill_black,
    native_px,
    native_rect,
)


class VideoDriverMpvWindow(VideoDriverMpv):
    """The mpv driver with no render thread: mpv starts as soon as it's made,
    into the window it's given, `win_id`, inside `window`."""

    # A picture from mpv, None where it had none, for a screenshot or not:
    # see take_screenshot. Said on mpv's event thread.
    _picture_taken = pyqtSignal(object, bool)
    # The picture a paused live stream stopped on, see snapshot
    snapshot_image = pyqtSignal(object)

    def __init__(self, win_id: int, window: QWidget, **kwargs):
        super().__init__(surface=None, full_size=None, is_software=False, **kwargs)

        self._win_id = win_id
        self._window = window

        # the picture for the screenshot said to be taken, for the frame to take
        self.taken_picture: QImage | None = None
        # a live stream loaded paused, let go of once its picture is up
        self._is_pause_due = False

        self._picture_taken.connect(self._on_picture_taken, Qt.QueuedConnection)

    def _new_player(self, media_input: MediaInput, **options) -> MpvPlayer:
        return super()._new_player(media_input, wid=self._win_id, **options)

    def _start_drawing(self) -> None:
        self._render_service.add_own_window(self._player, self._start_player)

    def _stop_drawing(self, player: MpvPlayer) -> None:
        # Out of the frame, which goes, into the app's window, hidden: no window
        # of its own left about, which Windows could activate (as SetParent does
        # one that's a popup then, see the bench's away._child_before_parent).
        app_window = self._window.window()

        self._window.hide()
        if app_window is not self._window:
            self._window.setParent(app_window)

        self._render_service.remove_own_window(player, self._window)
        # nothing on a render thread to let go of first
        player.on_render_context_gone()

    def _on_video_size(self, width: int, height: int, sar) -> None:
        super()._on_video_size(width, height, sar)

        # what it draws once it knows the picture: Stage 14.3 waits for it
        if not self._has_frame:
            self._has_frame = True
            self._report_load()

    def screenshot(self):
        self._take_picture(is_screenshot=True)

    def snapshot(self):
        """Before a live stream is let go of as it's paused: mpv's window shows
        nothing once it is."""

        self._take_picture(is_screenshot=False)

    def _take_picture(self, is_screenshot: bool) -> None:
        player = self._player

        if player is None or player.is_picture_held:
            self._on_picture_taken(None, is_screenshot)
            return

        def taken(image) -> None:
            # gone with its video by then, or not
            with suppress(RuntimeError):
                self._picture_taken.emit(image, is_screenshot)

        player.take_screenshot(taken)

    def _pause_live_at_load(self, player: MpvPlayer) -> None:
        """mpv's window shows nothing once the stream is let go of: its picture
        first, as for a pause (see snapshot)."""

        self._is_pause_due = True
        self._take_picture(is_screenshot=False)

    def _on_picture_taken(self, picture, is_screenshot: bool) -> None:
        if is_screenshot:
            self.taken_picture = picture
            self.screenshot_taken_emit("")
            return

        if not self._is_pause_due:
            self.snapshot_image.emit(picture)
            return

        self._is_pause_due = False

        # played in the meantime: nothing to put up, and it plays on
        if self._player is None or not self._player.is_pause_asked:
            return

        self.snapshot_image.emit(picture)
        self._player.set_pause(True)

    def _on_playback_restarted(self) -> None:
        super()._on_playback_restarted()

        # a live stream back from a pause: see
        # VideoFrameMpvWindow._on_playback_started
        self.playback_started_emit()

    def set_on_show(self, is_on_show: bool) -> None:
        """Stage 14.5."""

    def set_window_picture(self, picture) -> None:
        """See MpvPlayer.set_window_picture."""

        if self._player is not None:
            self._player.set_window_picture(picture)


_WS_CLIPCHILDREN = 0x02000000

# How big mpv's window over all of the picture can get before it's only over the
# part on show, mpv placing the picture in it (see WindowPicture). Moving a window
# over all of it follows a pan or a resize at once, where mpv takes 70 ms to place
# the picture again playing, 20-40 paused. But its buffers grow with it, and
# Direct3D takes no window past 16384. Measured on an RTX 3060.
_WHOLE_MAX_SHARE = 4
_WHOLE_ALWAYS_PIXELS = 1920 * 1080
_WHOLE_MAX_SIDE = 8192


class _SurfaceView(NamedTuple):
    """Where the surface goes, as apply_vlc_hw_surface_geometry takes it, and
    where mpv puts the picture in it, if the surface is only over the part on
    show. None for the surface over all of the picture. With the view's
    placement it's worked out from, None where there's none yet."""

    layout: tuple[int, Rect | None, Rect | None, QMargins]
    window_picture: WindowPicture | None
    placement: ViewPlacement | None


def _whole_picture(placement: ViewPlacement, frame_size: tuple[int, int]) -> Rect:
    """All of the picture in the pane, past its edges: where the part on show is,
    grown by the rest of the frame at the same scale."""

    source_x, source_y, source_w, source_h = placement.source
    target_x, target_y, target_w, target_h = placement.target
    frame_w, frame_h = frame_size

    per_x, per_y = target_w / source_w, target_h / source_h

    return (
        target_x - source_x * per_x,
        target_y - source_y * per_y,
        frame_w * per_x,
        frame_h * per_y,
    )


def _is_window_whole(picture: Rect, shown: Rect, ratio: float) -> bool:
    """Whether mpv's window goes over all of the picture: see _WHOLE_MAX_SHARE.

    Not on X11: under XWayland a GL window reaching past the screen's edge shows
    what's drawn as if from where the screen's edge is, the picture moved by as
    much (seen with Fill on sway). mpv places it there, in a window on show.
    """

    if not env.IS_WINDOWS:
        return False

    width, height = picture[2] * ratio, picture[3] * ratio
    shown_pixels = shown[2] * shown[3] * ratio * ratio

    return max(width, height) <= _WHOLE_MAX_SIDE and width * height <= max(
        _WHOLE_ALWAYS_PIXELS, _WHOLE_MAX_SHARE * shown_pixels
    )


# for the float error in a size that's a whole number of pixels
_SIZE_SLACK = 1e-6


def _on_picture_pixels(
    start: int, size: int, pixels: int, shown_from: int, shown_to: int
) -> tuple[int, int]:
    """Along one side, in screen pixels: a picture `size` long from `start`, of
    `pixels` of its own, and the part of it on show. Where the edges of its own
    pixels are, at or before the part on show and at or after it, as mpv works
    them out (see WindowPicture): mpv's cut is then on them, and exact."""

    first = max(0, (shown_from - start) * pixels // size)
    last = min(pixels, -(-(shown_to - start) * pixels // size))

    return start - (-first * size // pixels), start + last * size // pixels


def _covering(start: int, end: int, ratio: float) -> tuple[int, int]:
    """The least of Qt's pixels whose screen pixels cover start to end."""

    first = math.floor(start / ratio)
    while native_px(first, ratio) > start:
        first -= 1
    while native_px(first + 1, ratio) <= start:
        first += 1

    last = math.ceil(end / ratio)
    while native_px(last, ratio) < end:
        last += 1
    while native_px(last - 1, ratio) >= end:
        last -= 1

    return first, last


def _paint_under_children(widget: QWidget) -> None:
    """Have the window's black reach under its children too, mpv's own above all.

    Windows keeps one picture of what the app's windows painted, and shows it,
    stretched, while a drag resizes them faster than they're painted again. Under
    mpv's window that held whatever was there before it came: the cell's loading
    status, as a native window over the frame (see VideoBlock._picture_shown),
    which no paint ever reached again, clipped out under mpv's. Seen as squashed
    status cards between the cells through a drag. mpv's picture is a layer of
    its own above that picture, so painting under it doesn't show while it's in
    place.
    """

    from gridplayer.utils.win32_vlc_vout import clear_window_style

    clear_window_style(int(widget.winId()), _WS_CLIPCHILDREN)

    widget.update()


class VideoFrameMpvWindow(MpvFrame, VideoFrameVLC):
    # Each step of a resize, unlike VLC's windows: mpv's own follows the surface by
    # itself within a millisecond, and moving the surface costs no call into mpv.
    resize_view_interval_ms = 0
    is_native_surface = True
    # as on X11 mpv waits for its window to be mapped before drawing the first
    # picture, which the load waits for; the loading status is a native window
    # over it until then (see VideoBlock._picture_shown)
    is_shown_while_loading = True
    # a paused live stream's picture, all of it, see _on_snapshot_image
    _paused_picture: QImage | None = None

    def __init__(
        self,
        render_service: MpvRenderService,
        hwdec: str,
        cpu_when_low: bool = False,
        **kwargs,
    ):
        self._render_service = render_service
        self._hwdec = hwdec
        self._cpu_when_low = cpu_when_low

        super().__init__(**kwargs)

    def ui_video_surface(self) -> QWidget:
        surface = QWidget(self.video_clip)

        surface.setMouseTracking(True)
        # On X11 mpv's window in one with no input never comes up: mpv waits for
        # it to be mapped, which it never is (seen under XWayland). The overlay is
        # a window of its own over the video there, and takes the mouse.
        if env.IS_WINDOWS:
            surface.setWindowFlags(Qt.WindowTransparentForInput)
        surface.setAttribute(Qt.WA_TransparentForMouseEvents)
        surface.setAttribute(Qt.WA_NativeWindow)

        return surface

    def load_video_finish(self, media) -> None:
        super().load_video_finish(media)

        # Black wherever mpv's window isn't over it yet, as through a resize: the
        # picture's own surroundings, not the light of the window behind. Only
        # once the video has loaded: the cell's loading status is under the
        # surface until then, as with VLC Hardware's (see
        # VideoBlock._hide_video_driver), and the surface can be there before the
        # cell has its size, a strip over it.
        if not media.is_audio_only:
            fill_black(self.video_clip)
            fill_black(self.video_surface)

            if env.IS_WINDOWS:
                _paint_under_children(self.video_clip)
                _paint_under_children(self.video_surface)

    def driver_setup(self, vlc_options) -> VideoDriverMpvWindow:
        return VideoDriverMpvWindow(
            win_id=int(self.video_surface.winId()),
            window=self.video_clip,
            render_service=self._render_service,
            hwdec=self._hwdec,
            cpu_when_low=self._cpu_when_low,
            pane_box=self._pane_box,
            is_on_show=self._is_on_show,
            parent=self,
        )

    def adjust_view(self):
        if super().adjust_view():
            return

        view = self._surface_view()

        self._place_native_surface(view.layout)

        self.video_driver.set_flip_in_mpv(self._shown_flip())
        self.video_driver.set_window_picture(view.window_picture)

        self._push_subtitle_view(view)

    def _push_subtitle_view(self, view: _SurfaceView | None = None) -> None:
        """Keeps a subtitle readable and on show, whatever the view does to the
        picture, as for Copy and Shared, where mpv's window is over all of the
        picture. Where mpv places the picture in a window over the part on show
        (see WindowPicture), it places the line in that window, the part on show
        being all it lays out by: as for a picture not cut at all."""

        if not self._is_subtitle_on_show():
            return

        if view is None:
            view = self._surface_view()

        if view.placement is None:
            return

        frame_size = self._view_frame_size()

        if view.window_picture is not None:
            source, window = (0, 0, *frame_size), view.window_picture.window
        else:
            ratio = self.video_surface.devicePixelRatioF()
            # the surface over all of the picture
            _, (_, _, width, height), _, _ = view.layout
            source = view.placement.source
            window = (max(round(width * ratio), 1), max(round(height * ratio), 1))

        self.video_driver.set_subtitle_view(
            subtitle_view(source, frame_size, window, self._full_render_size()[1])
        )

    def _native_surface_layout(self):
        return self._surface_view().layout

    def driver_connect(self) -> None:
        super().driver_connect()

        self.video_driver.snapshot_image.connect(self._on_snapshot_image)

    def shown_frame_image(self) -> QImage | None:
        """The picture taken for the screenshot, or a paused live stream's, as
        shown, all of it: see screenshot_view."""

        driver = self.video_driver

        if driver is not None and driver.taken_picture:
            picture, driver.taken_picture = driver.taken_picture, None
            return picture

        return self._paused_picture if self.pause_snapshot.isVisible() else None

    def screenshot_view(self) -> ScreenshotView | None:
        return ScreenshotView(
            self._pane_size(),
            self._view,
            self._transform,
            self._view_frame_size(),
            self._orientation(),
            self._pixel_aspect(),
        )

    def _on_snapshot_image(self, picture) -> None:
        """The picture a paused live stream stopped on, up over the video, cut to
        the view, as VLC's is; mpv's window hidden under it, black once mpv lets
        go of the stream. Then the stream is let go of.

        Paused again before it was back, mpv has nothing to give, and the
        picture already up stays."""

        if picture is None and self.pause_snapshot.isVisible():
            picture = self._paused_picture

        self._paused_picture = picture

        if picture is None:
            self.pause_snapshot.set_snapshot_file("")
        else:
            self.pause_snapshot.set_pixmap(
                QPixmap.fromImage(self._cut_to_view(picture))
            )

        self.pause_snapshot.adjust_view(self.size(), self._shown_picture_rect())
        self.pause_snapshot.show()
        self.video_clip.hide()

        if self._is_status_change_in_progress:
            self.video_driver.set_pause(True)

    def _cut_to_view(self, image: QImage) -> QImage:
        placement = self.view_placement()

        if placement is None:
            return image

        frame_w, frame_h = self._view_frame_size()
        x, y, width, height = placement.source
        scale_x, scale_y = image.width() / frame_w, image.height() / frame_h

        return image.copy(
            QRect(
                round(x * scale_x),
                round(y * scale_y),
                max(round(width * scale_x), 1),
                max(round(height * scale_y), 1),
            )
        )

    def _on_unpaused_from_snapshot(self) -> None:
        """A live stream back from a pause keeps its snapshot up until mpv shows
        it again: see _on_playback_started."""

    def _on_playback_started(self) -> None:
        super()._on_playback_started()

        if not self.pause_snapshot.isVisible():
            return

        self._paused_picture = None
        self.video_clip.show()
        self.pause_snapshot.hide()
        self.pause_snapshot.reset()
        self.adjust_view()

    def _shown_flip(self) -> tuple[bool, bool] | None:
        return shown_flip(self._transform, self._orientation() in ROTATION_TRANSFORMS)

    def _surface_view(self) -> _SurfaceView:
        """Over all of the picture, mpv stretching it over its window, cut down
        by the clip to the part on show. Where that would make too big a window,
        over the part on show, mpv placing the picture in it."""

        placement = self.view_placement()

        if placement is None:
            return _SurfaceView((0, None, None, QMargins()), None, None)

        shown = placement.target
        picture = _whole_picture(placement, self._view_frame_size())

        if _is_window_whole(picture, shown, self.video_surface.devicePixelRatioF()):
            padding = QMargins(0, 0, 0, self._whole_rows(picture, shown))
            return _SurfaceView((0, picture, shown, padding), None, placement)

        return self._placed(placement, picture, shown)

    def _placed(
        self, placement: ViewPlacement, picture: Rect, shown: Rect
    ) -> _SurfaceView:
        """The surface over the part on show, grown out to the picture's own
        pixels' edges, and mpv told to put the picture there, leaving out what's
        past those edges: see WindowPicture."""

        ratio = self.video_surface.devicePixelRatioF()

        # the picture's own pixels as it's shown, which mpv turns
        columns, rows = self._view_frame_size()
        if self._transform in ROTATION_TRANSFORMS:
            columns, rows = rows, columns

        # on whole screen pixels, as mpv puts it
        start_x, start_y = round(picture[0] * ratio), round(picture[1] * ratio)
        width = math.floor(picture[2] * ratio + _SIZE_SLACK)
        height = math.floor(picture[3] * ratio + _SIZE_SLACK)

        clip = calc_vlc_hw_clip_rect(self.size(), shown)
        clip_x, clip_y, clip_w, clip_h = native_rect(
            clip.x(), clip.y(), clip.width(), clip.height(), ratio
        )

        left, right = _on_picture_pixels(
            start_x, width, columns, clip_x, clip_x + clip_w
        )
        top, bottom = _on_picture_pixels(start_y, height, rows, clip_y, clip_y + clip_h)

        surface_left, surface_right = _covering(left, right, ratio)
        surface_top, surface_bottom = _covering(top, bottom, ratio)
        surface = (
            surface_left,
            surface_top,
            surface_right - surface_left,
            surface_bottom - surface_top,
        )
        grown = self._whole_rows(surface, shown)

        window_left = native_px(surface_left, ratio)
        window_right = native_px(surface_right, ratio)
        window_top = native_px(surface_top, ratio)
        window_bottom = native_px(surface_bottom + grown, ratio)

        margins = (
            left - window_left,
            top - window_top,
            window_right - right,
            window_bottom - bottom,
        )
        x, y = start_x - left, start_y - top

        # mpv's flip is of the picture's area, the margins left as they are
        is_across, is_up_down = self._shown_flip() or (False, False)
        if is_across:
            x = right - start_x - width
        if is_up_down:
            y = bottom - start_y - height

        window_picture = WindowPicture(
            window=(window_right - window_left, window_bottom - window_top),
            margins=margins,
            picture=(x, y, width, height),
        )

        return _SurfaceView(
            (0, surface, shown, QMargins(0, 0, 0, grown)), window_picture, placement
        )

    def _whole_rows(self, target, shown) -> int:
        """Rows to grow the surface by at the bottom for it to be a whole number
        of 4-row blocks tall in the window's own pixels.

        NVIDIA's driver on Windows, drawing for a screen on another GPU, pads a
        window's buffer up to that at some widths, and Windows squeezes the
        padding into the window as black rows at the bottom: 1-3 under every
        picture. With nothing to pad there's none. The clip cuts the rows grown
        by off. Over all of the picture mpv stretches it over them too (it leaves
        out margins then), a picture 1-3 rows taller than it is; placing it, mpv
        leaves them out as a margin.
        """

        if not env.IS_WINDOWS or target is None:
            return 0

        surface = calc_vlc_hw_surface_rect(self.size(), 0, target)
        top = surface.y() - calc_vlc_hw_clip_rect(self.size(), shown).y()

        for grown in range(PICTURE_BLOCK_MAX_PAD + 1):
            if (
                self._rows(top, surface.height() + grown)
                % VLC_WINDOWS_PICTURE_ROW_BLOCK
                == 0
            ):
                return grown

        return 0

    def _rows(self, top: int, height: int) -> int:
        """How many rows of the window's own a height at `top` in the clip is."""

        ratio = self.video_surface.devicePixelRatioF()

        return native_rect(0, top, 0, height, ratio)[3]

    def _shown_picture_rect(self):
        placement = self.view_placement()

        return placement.target if placement is not None else None
