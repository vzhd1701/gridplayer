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

from PyQt5.QtCore import QMargins, Qt
from PyQt5.QtWidgets import QWidget

from gridplayer.mpv_player.player import MpvPlayer
from gridplayer.mpv_player.renderer import MpvRenderService
from gridplayer.params import env
from gridplayer.vlc_player.static import MediaInput
from gridplayer.widgets.video_frame_mpv import MpvFrame, VideoDriverMpv
from gridplayer.widgets.video_frame_vlc_base import (
    PICTURE_BLOCK_MAX_PAD,
    VLC_WINDOWS_PICTURE_ROW_BLOCK,
    VideoFrameVLC,
    calc_vlc_hw_clip_rect,
    calc_vlc_hw_surface_rect,
    fill_black,
    native_rect,
)


class VideoDriverMpvWindow(VideoDriverMpv):
    """The mpv driver with no render thread: mpv starts as soon as it's made,
    into the window it's given, `win_id`, inside `window`."""

    def __init__(self, win_id: int, window: QWidget, **kwargs):
        super().__init__(surface=None, full_size=None, is_software=False, **kwargs)

        self._win_id = win_id
        self._window = window
        self._rows_left_out = 0.0

    def _new_player(self, media_input: MediaInput, **options) -> MpvPlayer:
        return super()._new_player(media_input, wid=self._win_id, **options)

    def _start_drawing(self) -> None:
        self._render_service.add_own_window(self._player)
        self._start_player()

    def _stop_drawing(self, player: MpvPlayer) -> None:
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
        # Stage 14.4
        self.screenshot_taken_emit("")

    def set_on_show(self, is_on_show: bool) -> None:
        """Stage 14.5."""

    def set_rows_left_out(self, share: float) -> None:
        """The share of its window's height at the bottom mpv leaves out of the
        picture: see VideoFrameMpvWindow._whole_rows."""

        if self._player is not None and share != self._rows_left_out:
            self._rows_left_out = share
            self._player.set_option("video-margin-ratio-bottom", f"{share:.6f}")


_WS_CLIPCHILDREN = 0x02000000


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

        grown = self._place_native_surface().bottom()

        self.video_driver.set_rows_left_out(self._rows_left_out(grown))

    def _native_surface_layout(self):
        """Over all of the picture, cut down by the clip to the part on show:
        mpv stretches the whole frame over its window. Stage 14.2 crops."""

        view_placement = self.view_placement()
        shown = view_placement.target if view_placement is not None else None

        whole = self._calc_whole_placement()
        target = whole.target if whole is not None else shown

        return 0, target, shown, QMargins(0, 0, 0, self._whole_rows(target, shown))

    def _whole_rows(self, target, shown) -> int:
        """Rows to grow the surface by at the bottom for it to be a whole number
        of 4-row blocks tall in the window's own pixels.

        NVIDIA's driver on Windows, drawing for a screen on another GPU, pads a
        window's buffer up to that at some widths, and Windows squeezes the
        padding into the window as black rows at the bottom: 1-3 under every
        picture. With nothing to pad there's none. mpv leaves the rows grown by
        out of the picture (see _rows_left_out), and the clip cuts them off.
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

    def _rows_left_out(self, grown: int) -> float:
        """The share of the surface's height, as placed, that's rows grown by."""

        if not grown:
            return 0.0

        surface = self.video_surface.geometry()
        whole = self._rows(surface.y(), surface.height())
        picture = self._rows(surface.y(), surface.height() - grown)

        return (whole - picture) / whole if whole > 0 else 0.0

    def _rows(self, top: int, height: int) -> int:
        """How many rows of the window's own a height at `top` in the clip is."""

        ratio = self.video_surface.devicePixelRatioF()

        return native_rect(0, top, 0, height, ratio)[3]

    def _shown_picture_rect(self):
        placement = self.view_placement()

        return placement.target if placement is not None else None
