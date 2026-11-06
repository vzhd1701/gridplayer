"""The mpv driver: playing in this process, on the render thread of
gridplayer.mpv_player.renderer, painting as the software drivers do.

A resize never reaches mpv while it's happening: the picture keeps its current
frame size and is scaled while painting. Once geometry has been quiet for
RESIZE_SETTLE_MS, mpv is told the new size and switches on the render thread,
the old frame staying up until the new one is ready. The frame has the shape
of the picture, and letterboxing, zoom and pan are all just where it's painted.
"""

from PyQt5.QtCore import Qt, QTimer

from gridplayer.mpv_player.player import MpvPlayer
from gridplayer.mpv_player.renderer import MpvRenderService, RenderedVideo
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import ViewPlacement, calc_render_size
from gridplayer.utils.qt import translate
from gridplayer.vlc_player.static import Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC, native_px
from gridplayer.widgets.video_surface_sw import PaintedVideoFrame, SoftwareVideoSurface

# How long geometry has to stay put before a video is rendered at the new size
RESIZE_SETTLE_MS = 150


class MpvVideoSurface(SoftwareVideoSurface):
    """The frame comes at whatever size was last asked for, unlike a software
    driver's, so its size says nothing about the picture's."""

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


class VideoDriverMpv(VLCVideoDriver):
    def __init__(
        self, render_service: MpvRenderService, hwdec: str, surface, pane_box, **kwargs
    ):
        super().__init__(**kwargs)

        self._render_service = render_service
        self._hwdec = hwdec
        self._surface = surface
        self._pane_box = pane_box

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

    def cleanup_start(self) -> None:
        self._load_timeout.stop()

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

    def _on_media_loaded(self, media: Media) -> None:
        self._media = media
        self._report_load()

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
        # the frame on show: see VideoFrameMpv.shown_frame_image
        self.screenshot_taken_emit("")

    def play(self):
        self.set_pause(False)

    def set_pause(self, is_paused):
        if self._player is None:
            return

        # nothing would come back to say so, and the frame waits for that
        if self._player.is_paused == is_paused:
            self.playback_status_changed_emit(is_paused)
            return

        self._player.set_option("pause", "yes" if is_paused else "no")

    def set_time(self, seek_ms):
        if self._player is None:
            return

        self._player.command("seek", max(seek_ms, 0) / 1000, "absolute+exact")

    def set_playback_rate(self, rate):
        self._set_option("speed", str(rate))

    def audio_set_mute(self, is_muted):
        self._set_option("mute", "yes" if is_muted else "no")

    def audio_set_volume(self, volume):
        self._set_option("volume", str(int(volume * 100)))

    # The rest of the controls come in later stages: see docs/MPV_PLAN.md

    def set_audio_track(self, track_id): ...

    def set_audio_device(self, device): ...

    def add_audio_slave(self, uri): ...

    def set_video_track(self, track_id): ...

    def set_subtitle_track(self, track_id): ...

    def add_subtitle_slave(self, uri): ...

    def set_audio_channel_mode(self, mode): ...

    def set_deinterlace(self, deinterlace, mode): ...

    def set_audio_delay(self, delay_ms): ...

    def set_subtitle_delay(self, delay_ms): ...


class VideoFrameMpv(PaintedVideoFrame, VideoFrameVLC):
    surface_class = MpvVideoSurface

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
            parent=self,
        )

    def _pane_box(self) -> tuple[int, int]:
        """The most a frame needs, in device pixels, before there is a view.

        The cell's size: this frame stays as it was made until it is shown.
        """
        ratio = self.devicePixelRatioF()
        pane = self.parentWidget() or self

        return round(pane.width() * ratio), round(pane.height() * ratio)

    def adjust_view(self):
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
            )
        )
