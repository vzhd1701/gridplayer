"""The mpv driver: playing in this process, on the render thread of
gridplayer.mpv_player.renderer, painting as the software drivers do, or with
GL output drawing the frame's texture.

A resize reaches mpv once it's over: the picture keeps its current frame size
and is scaled while painting. Once geometry has been quiet for
RESIZE_SETTLE_MS, mpv is told the new size and switches on the render thread,
the old frame staying up until the new one is ready. Only a picture growing
well past its frame catches up every RESIZE_CATCH_UP_MS on the way, as it
would otherwise be blown up until the resize ends. The frame has the shape
of the picture, and letterboxing, zoom, pan and flips are all just how it's
painted.
"""

from PyQt5.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage

from gridplayer.models.stream import Stream
from gridplayer.mpv_player.conf import conf_lines
from gridplayer.mpv_player.player import MpvPlayer
from gridplayer.mpv_player.renderer import MpvRenderService, RenderedVideo
from gridplayer.mpv_player.subtitles import (
    SubtitleView,
    current_subtitle_style,
    subtitle_view,
)
from gridplayer.params.static import (
    ROTATION_TRANSFORMS,
    SeekAim,
    SeekPrecision,
    VideoTransform,
)
from gridplayer.settings import Settings
from gridplayer.utils.aspect_calc import (
    ViewPlacement,
    calc_full_size,
    calc_render_size,
)
from gridplayer.utils.media_libs import MediaLib
from gridplayer.utils.qt import translate
from gridplayer.vlc_player.static import DISABLED_TRACK, NO_TRACK, Media, MediaInput
from gridplayer.vlc_player.video_driver_base import VLCVideoDriver
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC, native_px
from gridplayer.widgets.video_surface_gl import GLVideoSurface
from gridplayer.widgets.video_surface_sw import (
    PaintedVideoFrame,
    SoftwareVideoSurface,
    unflipped_source,
)

# How long geometry has to stay put before a video is rendered at the new size
RESIZE_SETTLE_MS = 150

# While a resize goes on, how often a picture grown past its frame by
# RESIZE_CATCH_UP_GROWTH is rendered at the size it has got to
RESIZE_CATCH_UP_MS = 100
RESIZE_CATCH_UP_GROWTH = 1.1

# How long a screenshot waits for the frame at the picture's own size, before
# making do with the one on show
SCREENSHOT_WAIT_MS = 2000

# which seeks land on a key frame, for each setting
_FAST_SEEK_AIMS = {
    SeekPrecision.EXACT: frozenset(),
    SeekPrecision.EXACT_MARKS: frozenset({SeekAim.HAND}),
    SeekPrecision.FAST: frozenset({SeekAim.HAND, SeekAim.MARK}),
}

# Across and up and down, after whatever turn there is: see player._TURNS. For
# a file that says to turn the picture on its side, the other way round: a flip
# is of the frame as the file stores it, as on the VLC drivers.
_FLIPS = {
    VideoTransform.HFLIP: (True, False),
    VideoTransform.VFLIP: (False, True),
    VideoTransform.TRANSPOSE: (True, False),
    VideoTransform.ANTITRANSPOSE: (False, True),
}


def shown_flip(
    transform: VideoTransform, is_file_on_its_side: bool
) -> tuple[bool, bool] | None:
    """Across and up and down, for the picture as it's shown: see _FLIPS."""

    flip = _FLIPS.get(transform)

    if flip is not None and is_file_on_its_side:
        return flip[::-1]

    return flip


class MpvSurfaceView:
    """The frame comes at whatever size was last asked for, unlike a software
    driver's, so its size says nothing about the picture's. Goes before the
    surface's class in its bases."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self._is_file_on_its_side = False
        self._is_flip_in_mpv = False
        # the last placement worked out, by what it was worked out from: a
        # paint a frame, about 25 us each, 1% of a core at 9 cells
        self._last_placement: tuple[tuple, ViewPlacement | None] | None = None

    def set_file_on_its_side(self, is_on_its_side: bool) -> None:
        self._is_file_on_its_side = is_on_its_side
        self.update()

    def set_flip_in_mpv(self, is_in_mpv: bool) -> None:
        if is_in_mpv != self._is_flip_in_mpv:
            self._is_flip_in_mpv = is_in_mpv
            self.update()

    def flip(self) -> tuple[bool, bool] | None:
        """Across and up and down, for the picture as it's shown."""

        return shown_flip(self._transform, self._is_file_on_its_side)

    def _painted_flip(self) -> tuple[bool, bool] | None:
        return None if self._is_flip_in_mpv else self.flip()

    def picture_size(self) -> tuple[int, int]:
        if self._track_size is not None and all(self._track_size):
            return self._track_size

        return self.frame_size()

    def placement(self) -> ViewPlacement | None:
        key = (
            self.frame_size(),
            self._track_size,
            self.width(),
            self.height(),
            self.devicePixelRatioF(),
            self._view,
            self._transform,
            self._pixel_aspect,
        )

        if self._last_placement is None or self._last_placement[0] != key:
            self._last_placement = key, self._placement()

        return self._last_placement[1]

    def _placement(self) -> ViewPlacement | None:
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
        flip = self._painted_flip()

        return image.mirrored(*flip) if image is not None and flip else image


class MpvVideoSurface(MpvSurfaceView, SoftwareVideoSurface):
    # never: it draws from the start
    drawing_started = pyqtSignal()

    def is_drawing(self) -> bool:
        return True

    def present_frame(self, slot) -> None:
        image_format = QImage.Format_RGBX8888 if slot.is_rgba else QImage.Format_RGB32
        self.present_rgb32(slot.pixels, slot.width, slot.height, image_format)

    def keep_frame(self, rendered) -> None:
        """The frame on show stays as its video goes: its pixels already do."""

    def drop_frame(self) -> None:
        """Its pixels are its own, whatever became of the video's."""

    def _draw_frame(self, painter, placement) -> None:
        flip = self._painted_flip()

        if flip is None:
            super()._draw_frame(painter, placement)
            return

        is_across, is_up_down = flip
        source = unflipped_source(placement.source, self.frame_size(), flip)
        x, y, width, height = placement.target

        painter.translate(x + width / 2, y + height / 2)
        painter.scale(-1 if is_across else 1, -1 if is_up_down else 1)
        painter.drawImage(
            QRectF(-width / 2, -height / 2, width, height),
            self._image,
            QRectF(*source),
        )


class MpvGLVideoSurface(MpvSurfaceView, GLVideoSurface):
    def present_frame(self, slot) -> None:
        self.present_texture(slot.texture, slot.width, slot.height)

    def keep_frame(self, rendered) -> None:
        """The frame on show stays as its video goes, until the next one comes:
        a reload looks the same as it does painted."""

        if rendered.take_shown_texture(self._texture):
            self.own_texture()


class VideoDriverMpv(VLCVideoDriver):
    def __init__(
        self,
        render_service: MpvRenderService,
        hwdec: str,
        is_software: bool,
        cpu_when_low: bool,
        surface,
        pane_box,
        full_size,
        is_on_show,
        on_scaling_changed=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._render_service = render_service
        self._hwdec = hwdec
        self._is_software = is_software
        self._cpu_when_low = cpu_when_low
        self._surface = surface
        # a GL surface draws once its window's grid surface is up
        if surface is not None:
            self._surface.drawing_started.connect(self._report_frame)
        self._pane_box = pane_box
        self._full_size = full_size
        self._is_on_show = is_on_show
        # see MpvPlayer.scaling_changed
        self._on_scaling_changed = on_scaling_changed
        # kept for the next player, see set_shown_size
        self._shown_size: tuple[tuple[int, int], tuple[int, int]] | None = None

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
        # where it is, or where it was last sent: what mpv counts a seek by so
        # much from
        self._time_ms: int | None = None

        self._load_timeout = QTimer(self)
        self._load_timeout.setSingleShot(True)
        self._load_timeout.timeout.connect(self._on_load_timeout)

        # a live stream opened again after a pause, until it plays
        self._rejoin_timeout = QTimer(self)
        self._rejoin_timeout.setSingleShot(True)
        self._rejoin_timeout.timeout.connect(self._on_rejoin_timeout)

        # screenshots asked for and the frame size they're waiting for
        self._screenshots_due = 0
        self._screenshot_size: tuple[int, int] | None = None

        self._screenshot_timeout = QTimer(self)
        self._screenshot_timeout.setSingleShot(True)
        self._screenshot_timeout.setInterval(SCREENSHOT_WAIT_MS)
        self._screenshot_timeout.timeout.connect(self._give_screenshots)

    def cleanup_start(self) -> None:
        self._load_timeout.stop()
        self._rejoin_timeout.stop()
        self._screenshot_timeout.stop()
        self._screenshots_due = 0

        player, self._player = self._player, None

        if player is None:
            return

        player.close()
        self._stop_drawing(player)

    def _stop_drawing(self, player: MpvPlayer) -> None:
        # The GUI thread is the only one to touch what's on show, so here it
        # is still the one on show: the renderer frees the rest once removed.
        self._surface.keep_frame(self._rendered)
        self._render_service.remove(self._rendered)

        self._rendered = None

    def load_video(self, media_input: MediaInput) -> None:
        self._log.info(f"Loading {media_input.uri}")

        self._time_ms = None

        try:
            self._player = self._new_player(media_input)
        # what a libmpv that won't take what it's asked can raise
        except Exception as e:
            self._log.exception("Could not start mpv")
            self.error_state(translate("Video Error", "Player error"), (str(e),))
            return

        self._player.set_on_show(self._is_on_show())
        # before the size, which can take High up
        if self._on_scaling_changed is not None:
            self._player.scaling_changed.connect(
                self._on_scaling_changed, Qt.QueuedConnection
            )
        if self._shown_size is not None:
            self._player.set_shown_size(*self._shown_size)

        # Queued for good, whatever thread these are said on: the observers
        # run on a thread Qt doesn't know, and auto can take that for this one
        for signal, slot in (
            (self._player.media_loaded, self._on_media_loaded),
            (self._player.playback_restarted, self._on_playback_restarted),
            (self._player.time_changed, self._on_time),
            (self._player.paused_changed, self.playback_status_changed_emit),
            (self._player.video_size_changed, self._on_video_size),
            (self._player.failed, self.error_state),
            (self._player.end_reached, self._on_end_reached),
            (self._player.tracks_changed, self._on_tracks_changed),
            (self._player.chapters_changed, self._on_chapters_changed),
            (self._player.render_context_ready, self._start_player),
        ):
            signal.connect(slot, Qt.QueuedConnection)

        self._start_drawing()

        timeout_s = Settings().get("player/video_init_timeout")
        self._load_timeout.start(timeout_s * 1000)

    def _new_player(self, media_input: MediaInput, **options) -> MpvPlayer:
        return MpvPlayer(
            self._render_service.mpv,
            media_input,
            hwdec=self._hwdec,
            skip_frames=Settings().get("player/mpv_skip_frames"),
            picture_quality=Settings().get("player/mpv_picture_quality"),
            direct_rendering=Settings().get("player/mpv_direct_rendering"),
            is_software=self._is_software,
            cpu_when_low=self._cpu_when_low,
            log_level=Settings().get("logging/log_level_mpv"),
            subtitle_style=current_subtitle_style(),
            wake_renderer=self._render_service.wake,
            conf=conf_lines() if Settings().get("player/mpv_conf") else None,
            **options,
        )

    def _start_drawing(self) -> None:
        """Its frames to the render thread, which starts the player once its
        render context is up."""

        self._rendered = RenderedVideo(self._player, is_software=self._is_software)
        self._render_service.add(self._rendered, self)

    def _start_player(self) -> None:
        # closed before its render context got here
        if self._player is not None:
            self._player.start(self._pane_box())

    def render_failed(self, message: str) -> None:
        # the renderer let go of the video's frames as it failed
        self._surface.drop_frame()
        self.error_state(translate("Video Error", "Player error"), (message,))

    def show_frame(self, slot) -> None:
        self._surface.present_frame(slot)

        self._report_frame()

        if self._screenshots_due and self._is_screenshot_size_shown():
            self._give_screenshots()

    def _on_media_loaded(self, media: Media) -> None:
        self._media = media
        self._report_load()

    def _on_end_reached(self) -> None:
        """As far as can be read, where only an error should bring that. Set to stay
        open, mpv says no more: it would wait there for good, and for a live stream that
        comes back as well."""

        if self._player is None:
            return

        if not self._is_load_reported:
            # as an mp4 with no way to seek to its index does, which says it has
            # started all the same
            self._player.fail(
                translate("Video Error", "Video stopped before initialization")
            )
        elif self._player.media_input.is_live:
            self._player.fail(translate("Video Error", "Live stream ended"))

    def _on_tracks_changed(self, media: Media) -> None:
        self._media = media

        self.tracks_changed_emit(media)

    def _on_chapters_changed(self, media: Media) -> None:
        self._media = media

        # until then the load has them to tell
        if self._is_load_reported:
            self.chapters_changed_emit(media.chapters)

    def _on_playback_restarted(self) -> None:
        self._has_restarted = True
        self._rejoin_timeout.stop()
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

    def _report_frame(self) -> None:
        """A picture on show, once one has come and the surface can draw it:
        the cell is loading until then."""

        if self._has_frame or not self._surface.has_frame():
            return

        if not self._surface.is_drawing():
            return

        self._has_frame = True
        self._report_load()

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

        # only known by now, and there's a picture to leave up
        if player.media_input.is_live and player.is_pause_asked:
            self._pause_live_at_load(player)

    def _pause_live_at_load(self, player: MpvPlayer) -> None:
        player.set_pause(True)

    def _on_load_timeout(self) -> None:
        self.error_state(translate("Video Error", "Timed out loading video"))

    def _on_rejoin_timeout(self) -> None:
        # as VLC says it
        self.error_state(translate("Video Error", "Buffering timeout"))

    def _set_option(self, name: str, value: str) -> None:
        if self._player is not None:
            self._player.set_option(name, value)

    def set_render_size(self, size: tuple[int, int]) -> None:
        if self._player is not None:
            self._player.set_render_size(size)

    def set_shown_size(
        self, size: tuple[int, int], source_size: tuple[int, int]
    ) -> None:
        self._shown_size = size, source_size

        if self._player is not None:
            self._player.set_shown_size(size, source_size)

    @property
    def is_scaling_high(self) -> bool:
        return self._player is not None and self._player.is_scaling_high

    def set_on_show(self, is_on_show: bool) -> None:
        if self._player is not None:
            self._player.set_on_show(is_on_show)

    def snapshot(self):
        self.snapshot_taken_emit("")

    def screenshot(self):
        """The frame on show, once it's at a size worth saving, a small cell's
        being only as big as it has to be to fill the cell. It comes back with
        no file: see PaintedVideoFrame.shown_frame_image."""

        size = self._full_size()

        # stopped, the frame on show is all there is
        if self._player is None or self._player.is_picture_held or not all(size):
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

        if not self._player.media_input.is_live:
            return

        if is_paused:
            self._rejoin_timeout.stop()
        else:
            self._rejoin_timeout.start(
                Settings().get("network/buffering_timeout") * 1000
            )

    def _on_time(self, time_ms: int) -> None:
        self._time_ms = time_ms
        self.time_changed.emit(time_ms)

    def set_time(self, seek_ms, aim=SeekAim.EXACT):
        if self._player is None or self._player.media_input.is_live:
            return

        from_ms, self._time_ms = self._time_ms, seek_ms

        # mpv goes to the first frame at or after a time, where a time here
        # means the frame it is in. Half a frame back makes it the frame nearest
        # to the time, and for the middle of a frame, which is where a frame
        # step aims, that very frame.
        exact_s = max(seek_ms - self._half_frame_ms(), 0) / 1000
        precision = Settings().get("player/mpv_seek_precision")

        if aim in _FAST_SEEK_AIMS.get(precision, ()):
            from_s = None if from_ms is None else from_ms / 1000
            self._player.seek_key_frame(seek_ms / 1000, exact_s, from_s)
        else:
            self._player.seek_exact(exact_s)

    def _half_frame_ms(self) -> float:
        track = self._media.cur_video_track if self._media is not None else None

        return 500 / track.fps if track is not None and track.fps else 0

    def set_playback_rate(self, rate):
        if self._player is not None and not self._player.media_input.is_live:
            self._player.set_option("speed", str(rate))

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

    def set_subtitle_view(self, view: SubtitleView) -> None:
        if self._player is not None:
            self._player.set_subtitle_view(view)

    def set_flip_in_mpv(self, flip: tuple[bool, bool] | None) -> bool:
        return self._player is not None and self._player.set_flip_in_mpv(flip)

    def set_subtitle_track(self, track_id):
        if self._media is not None:
            self._select_track("sid", track_id, self._media.subtitle_tracks, False)

    def add_subtitle_slave(self, uri):
        if self._player is not None:
            self._player.add_subtitle_file(uri)

    def set_subtitle_delay(self, delay_ms):
        self._set_option("sub-delay", str(delay_ms / 1000))

    def set_deinterlace(self, deinterlace, mode):
        if self._player is not None:
            self._player.set_deinterlace(deinterlace, mode)


class MpvFrame:
    """What every frame playing with mpv has, however its frames reach the
    window. Goes before the VLC frame's class in the bases."""

    is_picky_about_audio_files = False
    must_reload_for_system_device = False
    is_late_with_subtitles = False
    must_reload_for_subtitle_style = False
    must_reload_for_automatic_deinterlace = False
    media_lib = MediaLib.MPV
    has_adaptive_demuxer = False

    @staticmethod
    def streams_to_open(stream: Stream) -> tuple[Stream, tuple[str, Stream] | None]:
        """As it comes: the sound apart, and a file in fragments as that file.

        Sound behind the one demuxer, as one playlist or as EDL, had every seek on a
        YouTube video take 5.6-6 s, and as an audio file 0.25-0.8 s, in sync. A file as
        a playlist opens 3-5 times slower, and on 0.40 with FFmpeg 7.1 most seeks past
        what's been read went back to the start: tests/real_app/scenarios/mpv_streams.py.
        """

        if not stream.audio_tracks:
            return stream.as_file(), None

        video, name, audio = stream.apart()

        return video.as_file(), (name, audio.as_file())

    def _is_on_show(self) -> bool:
        """Not hidden, as the cells Single Mode leaves out are, nor its window
        minimized or in the tray."""

        return self.isVisible() and not self.window().isMinimized()

    def update_on_show(self) -> None:
        self.video_driver.set_on_show(self._is_on_show())

    # Shown again as its window comes back from being minimized, it can be before
    # the window says it no longer is: the window's own word comes as well, see
    # VideoBlocksManager.update_on_show.
    def showEvent(self, event):
        super().showEvent(event)

        self.update_on_show()

    def hideEvent(self, event):
        super().hideEvent(event)

        self.update_on_show()

    def set_time(self, seek_ms, aim=SeekAim.EXACT) -> None:
        # what it's for, which VLC's drivers have no use for
        self.video_driver.set_time(seek_ms, aim)

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

    def set_subtitle_track(self, track_id):
        super().set_subtitle_track(track_id)

        self._push_subtitle_view()

    def _on_tracks_changed(self, media: Media) -> None:
        super()._on_tracks_changed(media)

        self._push_subtitle_view()

    def _is_subtitle_on_show(self) -> bool:
        return self.media is not None and self.media.cur_subtitle_track is not None

    def _push_shown_size(self) -> None:
        placement = self.view_placement()

        if placement is not None:
            _, _, width, height = placement.target
            _, _, source_width, source_height = placement.source
            ratio = self.devicePixelRatioF()
            self.video_driver.set_shown_size(
                (round(width * ratio), round(height * ratio)),
                (round(source_width), round(source_height)),
            )

    def _push_subtitle_view(self) -> None:
        """Keeps a subtitle readable and on show, whatever the view does to the
        picture."""

        raise NotImplementedError


class VideoFrameMpv(MpvFrame, PaintedVideoFrame, VideoFrameVLC):
    def __init__(
        self,
        render_service: MpvRenderService,
        hwdec: str,
        is_software: bool = False,
        cpu_when_low: bool = False,
        **kwargs,
    ):
        self._render_service = render_service
        self._hwdec = hwdec
        # Decode on the CPU set to Auto
        self._cpu_when_low = cpu_when_low
        # libmpv's software renderer, painted: no GL at all
        self._is_software = is_software

        super().__init__(**kwargs)

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(RESIZE_SETTLE_MS)
        self._settle_timer.timeout.connect(self._push_render_size)

        self._catch_up_timer = QTimer(self)
        self._catch_up_timer.setSingleShot(True)
        self._catch_up_timer.setInterval(RESIZE_CATCH_UP_MS)
        self._catch_up_timer.timeout.connect(self._catch_up_render_size)

        # shown for the first time, it goes to its size for good right away
        self._is_first_size_due = True

    def grab(self, *args):
        # the picture, not the hole the window has for it
        with GLVideoSurface.grabbing():
            return super().grab(*args)

    def ui_video_surface(self):
        if self._render_service.is_gl_output and not self._is_software:
            return MpvGLVideoSurface(
                self, delete_textures=self._render_service.delete_textures
            )

        return MpvVideoSurface(self)

    def driver_setup(self, vlc_options) -> VideoDriverMpv:
        return VideoDriverMpv(
            render_service=self._render_service,
            hwdec=self._hwdec,
            is_software=self._is_software,
            cpu_when_low=self._cpu_when_low,
            surface=self.video_surface,
            pane_box=self._pane_box,
            full_size=self._full_render_size,
            is_on_show=self._is_on_show,
            on_scaling_changed=self._push_render_size,
            parent=self,
        )

    def adjust_view(self):
        self.video_surface.set_file_on_its_side(
            self._orientation() in ROTATION_TRANSFORMS
        )

        if super().adjust_view():
            return True

        # at once: only the frame's size has a reason to wait
        self._push_subtitle_view()
        self._push_shown_size()

        if self._is_first_size_due and self.isVisible():
            self._is_first_size_due = False
            self._push_render_size()
            return False

        self._settle_timer.start()
        # not started again by each step, so it comes round while they go on
        if not self._catch_up_timer.isActive():
            self._catch_up_timer.start()

        return False

    def cleanup_start(self) -> None:
        self._settle_timer.stop()
        self._catch_up_timer.stop()

        super().cleanup_start()

    def set_subtitle_track(self, track_id):
        super().set_subtitle_track(track_id)

        self._push_render_size()

    def _on_tracks_changed(self, media: Media) -> None:
        super()._on_tracks_changed(media)

        self._push_render_size()

    def _wanted_render_size(self, placement: ViewPlacement) -> tuple[int, int]:
        return calc_render_size(
            self._view_frame_size(),
            placement,
            self.devicePixelRatioF(),
            self._pixel_aspect(),
            self._transform,
            # A small picture is only blurred by drawing it big, its text isn't;
            # nor is it with High picture quality, as mpv makes it bigger then,
            # sharper than the surface's bilinear.
            sharp_in=self._pane_box() if self._is_drawn_big() else None,
        )

    def _is_drawn_big(self) -> bool:
        return self._is_subtitle_on_show() or self.video_driver.is_scaling_high

    def _render_size_now(self) -> tuple[int, int] | None:
        placement = self.view_placement()

        return None if placement is None else self._wanted_render_size(placement)

    def _push_render_size(self) -> None:
        wanted = self._render_size_now()

        if wanted is not None:
            self.video_driver.set_render_size(wanted)

    def _catch_up_render_size(self) -> None:
        # over already, and the frame on its way at the size it ends at
        if not self._settle_timer.isActive() or not self.video_surface.has_frame():
            return

        wanted = self._render_size_now()
        if wanted is None:
            return

        wanted_w, wanted_h = wanted
        frame_w, frame_h = self.video_surface.frame_size()

        if (
            wanted_w > frame_w * RESIZE_CATCH_UP_GROWTH
            or wanted_h > frame_h * RESIZE_CATCH_UP_GROWTH
        ):
            self.video_driver.set_render_size(wanted)

    def _push_subtitle_view(self) -> None:
        """mpv is only asked to flip while there is a subtitle: see
        player._FLIP_SHADER."""

        placement = self.view_placement()

        if placement is None:
            return

        is_on_show = self._is_subtitle_on_show()

        self.video_surface.set_flip_in_mpv(
            self.video_driver.set_flip_in_mpv(
                self.video_surface.flip() if is_on_show else None
            )
        )

        if is_on_show:
            self.video_driver.set_subtitle_view(
                subtitle_view(
                    placement.source,
                    self._view_frame_size(),
                    self._wanted_render_size(placement),
                    self._full_render_size()[1],
                )
            )
