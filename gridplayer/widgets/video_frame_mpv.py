"""The mpv driver: playing in this process, on the render thread of
gridplayer.mpv_player.renderer, painting as the software drivers do.

A resize never reaches mpv while it's happening: the picture keeps its current
frame size and is scaled while painting. Once geometry has been quiet for
RESIZE_SETTLE_MS, mpv is told the new size and switches on the render thread,
the old frame staying up until the new one is ready. The frame has the shape
of the picture, and letterboxing, zoom, pan and flips are all just how it's
painted.
"""

from PyQt5.QtCore import QRectF, Qt, QTimer

from gridplayer.mpv_player.player import MpvPlayer
from gridplayer.mpv_player.renderer import MpvRenderService, RenderedVideo
from gridplayer.params.static import ROTATION_TRANSFORMS, VideoTransform
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import (
    ViewPlacement,
    calc_full_size,
    calc_render_size,
)
from gridplayer.utils.qt import translate
from gridplayer.vlc_player.static import DISABLED_TRACK, NO_TRACK, Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC, native_px
from gridplayer.widgets.video_surface_sw import PaintedVideoFrame, SoftwareVideoSurface

# How long geometry has to stay put before a video is rendered at the new size
RESIZE_SETTLE_MS = 150

# How long a screenshot waits for the frame at the picture's own size, before
# making do with the one on show
SCREENSHOT_WAIT_MS = 2000

# Across and up and down, after whatever turn there is: see player._TURNS. For
# a file that says to turn the picture on its side, the other way round: a flip
# is of the frame as the file stores it, as on the VLC drivers.
_FLIPS = {
    VideoTransform.HFLIP: (True, False),
    VideoTransform.VFLIP: (False, True),
    VideoTransform.TRANSPOSE: (True, False),
    VideoTransform.ANTITRANSPOSE: (False, True),
}


class MpvVideoSurface(SoftwareVideoSurface):
    """The frame comes at whatever size was last asked for, unlike a software
    driver's, so its size says nothing about the picture's."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_file_on_its_side = False

    def set_file_on_its_side(self, is_on_its_side: bool) -> None:
        self._is_file_on_its_side = is_on_its_side
        self.update()

    def _flips(self) -> tuple[bool, bool] | None:
        flips = _FLIPS.get(self._transform)

        if flips is not None and self._is_file_on_its_side:
            return flips[::-1]

        return flips

    def picture_size(self) -> tuple[int, int]:
        if self._track_size is not None and all(self._track_size):
            return self._track_size

        return self.frame_size()

    def placement(self) -> ViewPlacement | None:
        placement = super().placement()

        if placement is None:
            return None

        # On whole device pixels: an edge between two of them is blended, and
        # shimmers as the cell changes size.
        ratio = self.devicePixelRatioF()
        x, y, width, height = placement.target

        left, top = native_px(x, ratio), native_px(y, ratio)
        right, bottom = native_px(x + width, ratio), native_px(y + height, ratio)

        return ViewPlacement(
            source=placement.source,
            target=(
                left / ratio,
                top / ratio,
                (right - left) / ratio,
                (bottom - top) / ratio,
            ),
        )

    def frame_image(self):
        image = super().frame_image()
        flips = self._flips()

        return image.mirrored(*flips) if image is not None and flips else image

    def _draw_frame(self, painter, placement) -> None:
        flips = self._flips()

        if flips is None:
            super()._draw_frame(painter, placement)
            return

        is_across, is_up_down = flips
        frame_w, frame_h = self.frame_size()
        source_x, source_y, source_w, source_h = placement.source
        x, y, width, height = placement.target

        # the source is a part of the picture as shown, the frame being unflipped
        if is_across:
            source_x = frame_w - source_x - source_w
        if is_up_down:
            source_y = frame_h - source_y - source_h

        painter.translate(x + width / 2, y + height / 2)
        painter.scale(-1 if is_across else 1, -1 if is_up_down else 1)
        painter.drawImage(
            QRectF(-width / 2, -height / 2, width, height),
            self._image,
            QRectF(source_x, source_y, source_w, source_h),
        )


class VideoDriverMpv(VLCVideoDriver):
    def __init__(
        self,
        render_service: MpvRenderService,
        hwdec: str,
        surface,
        pane_box,
        full_size,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._render_service = render_service
        self._hwdec = hwdec
        self._surface = surface
        self._pane_box = pane_box
        self._full_size = full_size

        self._player: MpvPlayer | None = None
        self._rendered: RenderedVideo | None = None

        # all three are needed to say the video has loaded
        self._media: Media | None = None
        self._has_restarted = False
        self._has_frame = False
        self._is_load_reported = False
        # what the decoder says of the picture, which can come before the load
        # has been reported, when the frame has no tracks to put it on yet
        self._video_size: tuple[int, int, object] | None = None

        self._load_timeout = QTimer(self)
        self._load_timeout.setSingleShot(True)
        self._load_timeout.timeout.connect(self._on_load_timeout)

        # screenshots asked for and the frame size they're waiting for
        self._screenshots_due = 0
        self._screenshot_size: tuple[int, int] | None = None

        self._screenshot_timeout = QTimer(self)
        self._screenshot_timeout.setSingleShot(True)
        self._screenshot_timeout.setInterval(SCREENSHOT_WAIT_MS)
        self._screenshot_timeout.timeout.connect(self._give_screenshots)

    def cleanup_start(self) -> None:
        self._load_timeout.stop()
        self._screenshot_timeout.stop()
        self._screenshots_due = 0

        if self._player is None:
            return

        self._player.close()
        self._render_service.remove(self._rendered)

        self._player = None
        self._rendered = None

    def load_video(self, media_input: MediaInput) -> None:
        self._log.info(f"Loading {media_input.uri}")

        try:
            self._player = MpvPlayer(
                self._render_service.mpv,
                media_input,
                hwdec=self._hwdec,
                skip_frames=Settings().get("player/mpv_skip_frames"),
                wake_renderer=self._render_service.wake,
            )
        # what a libmpv that won't take what it's asked can raise
        except Exception as e:
            self._log.exception("Could not start mpv")
            self.error_state(translate("Video Error", "Player error"), (str(e),))
            return

        # Queued for good, whatever thread these are said on: the observers
        # run on a thread Qt doesn't know, and auto can take that for this one
        for signal, slot in (
            (self._player.media_loaded, self._on_media_loaded),
            (self._player.playback_restarted, self._on_playback_restarted),
            (self._player.time_changed, self.time_changed),
            (self._player.paused_changed, self.playback_status_changed_emit),
            (self._player.video_size_changed, self._on_video_size),
            (self._player.failed, self.error_state),
            (self._player.tracks_changed, self._on_tracks_changed),
            (self._player.render_context_ready, self._start_player),
        ):
            signal.connect(slot, Qt.QueuedConnection)

        self._rendered = RenderedVideo(self._player)
        self._render_service.add(self._rendered, self)

        timeout_s = Settings().get("player/video_init_timeout")
        self._load_timeout.start(timeout_s * 1000)

    def _start_player(self) -> None:
        # closed before its render context got here
        if self._player is not None:
            self._player.start(self._pane_box())

    def render_failed(self, message: str) -> None:
        self.error_state(translate("Video Error", "Player error"), (message,))

    def show_frame(self, slot) -> None:
        self._surface.present_rgb32(slot.pixels, slot.width, slot.height)

        if not self._has_frame:
            self._has_frame = True
            self._report_load()

        if self._screenshots_due and self._is_screenshot_size_shown():
            self._give_screenshots()

    def _on_media_loaded(self, media: Media) -> None:
        self._media = media
        self._report_load()

    def _on_tracks_changed(self, media: Media) -> None:
        self._media = media

        self.tracks_changed_emit(media)

    def _on_playback_restarted(self) -> None:
        self._has_restarted = True
        self._report_load()

    def _on_video_size(self, width: int, height: int, sar) -> None:
        self._video_size = (width, height, sar)

        if self._is_load_reported:
            self._put_video_size_on_track(self._media)
            self.set_video_dimensions(width, height, sar)

    def _put_video_size_on_track(self, media: Media) -> None:
        """A stream's tracks can say nothing of the picture until it plays, and
        what it plays can change size as it goes. They're the frame's tracks too,
        which only fills in what's missing."""

        track = media.cur_video_track

        if track is None or self._video_size is None:
            return

        width, height, sar = self._video_size

        if width and height:
            track.video_dimensions = (width, height)

        if sar is not None:
            track.sar = sar

    def _report_load(self) -> None:
        player = self._player

        # closed with this already on its way
        if player is None:
            return

        if self._is_load_reported or self._media is None or not self._has_restarted:
            return

        # with no picture coming there is no picture to wait for
        if not self._has_frame and not self._media.is_audio_only:
            return

        self._is_load_reported = True
        self._load_timeout.stop()

        self._put_video_size_on_track(self._media)

        self.load_video_done(self._media)

        self.playback_status_changed_emit(player.is_paused)
        self.time_changed.emit(player.media_input.initial_time)

    def _on_load_timeout(self) -> None:
        self.error_state(translate("Video Error", "Timed out loading video"))

    def _set_option(self, name: str, value: str) -> None:
        if self._player is not None:
            self._player.set_option(name, value)

    def set_render_size(self, size: tuple[int, int]) -> None:
        if self._player is not None:
            self._player.set_render_size(size)

    def snapshot(self):
        self.snapshot_taken_emit("")

    def screenshot(self):
        """The frame on show, once it's at a size worth saving, a small cell's
        being only as big as it has to be to fill the cell. It comes back with
        no file: see PaintedVideoFrame.shown_frame_image."""

        size = self._full_size()

        if self._player is None or not all(size):
            self.screenshot_taken_emit("")
            return

        self._screenshots_due += 1
        self._screenshot_size = size

        if self._is_screenshot_size_shown():
            self._give_screenshots()
            return

        self._player.hold_render_size(size)
        self._screenshot_timeout.start()

    def _is_screenshot_size_shown(self) -> bool:
        return self._surface.frame_size() == self._screenshot_size

    def _give_screenshots(self) -> None:
        self._screenshot_timeout.stop()

        if self._player is not None:
            self._player.hold_render_size(None)

        due, self._screenshots_due = self._screenshots_due, 0

        for _ in range(due):
            self.screenshot_taken_emit("")

    def play(self):
        self.set_pause(False)

    def set_pause(self, is_paused):
        if self._player is None:
            return

        # nothing would come back to say so, and the frame waits for that
        if self._player.is_pause_asked == is_paused:
            self.playback_status_changed_emit(is_paused)
            return

        self._player.set_pause(is_paused)

    def set_time(self, seek_ms):
        if self._player is None:
            return

        # mpv goes to the first frame at or after a time, where a time here
        # means the frame it is in. Half a frame back makes it the frame nearest
        # to the time, and for the middle of a frame, which is where a frame
        # step aims, that very frame.
        aim_ms = max(seek_ms - self._half_frame_ms(), 0)

        self._player.command("seek", aim_ms / 1000, "absolute+exact")

    def _half_frame_ms(self) -> float:
        track = self._media.cur_video_track if self._media is not None else None

        return 500 / track.fps if track is not None and track.fps else 0

    def set_playback_rate(self, rate):
        self._set_option("speed", str(rate))

    def audio_set_mute(self, is_muted):
        self._set_option("mute", "yes" if is_muted else "no")

    def audio_set_volume(self, volume):
        self._set_option("volume", str(int(volume * 100)))

    def set_audio_track(self, track_id):
        if self._media is None:
            return

        media = self._media

        self._select_track("aid", track_id, media.audio_tracks, media.is_audio_only)

    def set_video_track(self, track_id):
        if self._media is None:
            return

        media = self._media
        is_sound_off = media.cur_audio_track_id in NO_TRACK

        self._select_track("vid", track_id, media.video_tracks, is_sound_off)

    def _select_track(self, option, track_id, tracks, is_other_off) -> None:
        if self._player is None:
            return

        # mpv would have nothing to play, and end the file
        if track_id == DISABLED_TRACK and is_other_off:
            self._log.warning("Cannot disable both audio & video tracks")
            return

        # None is nothing read back yet, and an id can be from before a reload
        if track_id != DISABLED_TRACK and track_id not in tracks:
            return

        self._player.select_track(option, track_id)

    def set_audio_device(self, device):
        if self._player is not None:
            self._player.set_audio_device(device)

    def add_audio_slave(self, uri):
        if self._player is not None:
            self._player.add_audio_file(uri)

    def set_audio_channel_mode(self, mode):
        if self._player is not None:
            self._player.set_channel_mode(mode)

    def set_audio_delay(self, delay_ms):
        self._set_option("audio-delay", str(delay_ms / 1000))

    # The rest of the controls come in later stages: see docs/MPV_PLAN.md

    def set_subtitle_track(self, track_id): ...

    def add_subtitle_slave(self, uri): ...

    def set_deinterlace(self, deinterlace, mode): ...

    def set_subtitle_delay(self, delay_ms): ...


class VideoFrameMpv(PaintedVideoFrame, VideoFrameVLC):
    surface_class = MpvVideoSurface

    is_picky_about_audio_files = False
    must_reload_for_system_device = False

    def __init__(self, render_service: MpvRenderService, hwdec: str, **kwargs):
        self._render_service = render_service
        self._hwdec = hwdec

        super().__init__(**kwargs)

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(RESIZE_SETTLE_MS)
        self._settle_timer.timeout.connect(self._push_render_size)

        # shown for the first time, it goes to its size for good right away
        self._is_first_size_due = True

    def driver_setup(self, vlc_options) -> VideoDriverMpv:
        return VideoDriverMpv(
            render_service=self._render_service,
            hwdec=self._hwdec,
            surface=self.video_surface,
            pane_box=self._pane_box,
            full_size=self._full_render_size,
            parent=self,
        )

    def _pane_box(self) -> tuple[int, int]:
        """The most a frame needs, in device pixels, before there is a view.

        The cell's size: this frame stays as it was made until it is shown.
        """
        ratio = self.devicePixelRatioF()
        pane = self.parentWidget() or self

        return round(pane.width() * ratio), round(pane.height() * ratio)

    def _full_render_size(self) -> tuple[int, int]:
        return calc_full_size(
            self._view_frame_size(), self._transform, self._pixel_aspect()
        )

    def adjust_view(self):
        self.video_surface.set_file_on_its_side(
            self._orientation() in ROTATION_TRANSFORMS
        )

        if super().adjust_view():
            return True

        if self._is_first_size_due and self.isVisible():
            self._is_first_size_due = False
            self._push_render_size()
            return False

        self._settle_timer.start()

        return False

    def cleanup_start(self) -> None:
        self._settle_timer.stop()

        super().cleanup_start()

    def _push_render_size(self) -> None:
        placement = self.view_placement()

        if placement is None:
            return

        self.video_driver.set_render_size(
            calc_render_size(
                self._view_frame_size(),
                placement,
                self.devicePixelRatioF(),
                self._pixel_aspect(),
                self._transform,
            )
        )
