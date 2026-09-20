import dataclasses
import logging
import random
import secrets
from functools import partial
from pathlib import Path

from pydantic_extra_types.color import Color
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QFileDialog, QStackedLayout, QWidget

from gridplayer.dialogs.input_dialog import (
    QCustomSpinboxInput,
    QCustomSpinboxTimeInput,
    QCustomTextInput,
)
from gridplayer.dialogs.rename_dialog import QVideoRenameDialog
from gridplayer.exceptions import PlayerException
from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioExternal,
    AudioLanguage,
    AudioPreferred,
    AudioTrackId,
    track_of_file,
)
from gridplayer.models.stream import (
    STANDING_QUALITIES,
    STREAM_QUALITY_AUTO,
    StreamOrigin,
    Streams,
)
from gridplayer.models.video import (
    Video,
    VideoBlockMime,
    default_audio_selection,
)
from gridplayer.params import env
from gridplayer.params.extensions import SUPPORTED_AUDIO_EXT
from gridplayer.params.static import (
    CHROME_MIN_SIZE,
    MAX_RATE,
    MAX_SCALE,
    MIN_RATE,
    MIN_SCALE,
    OVERLAY_ACTIVITY_EVENT,
    PLAYER_ID_LENGTH,
    NetworkRetryMode,
    VideoAspect,
    VideoCrop,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.settings import Settings
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.utils.external_audio import (
    discover_audio_files,
    silenced_by_seeking,
    unplayable_as_audio_slave,
)
from gridplayer.utils.libvlc_options_parser import get_vlc_options
from gridplayer.utils.next_file import next_video_file, previous_video_file
from gridplayer.utils.qt import MILLISECONDS, qt_connect, translate
from gridplayer.utils.track_language import normalize, pick_track
from gridplayer.utils.url_resolve.static import ResolvedVideo
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolver
from gridplayer.vlc_player.static import (
    DISABLED_TRACK,
    NO_TRACK,
    MediaInput,
    is_loop_wrapped,
    wanted_audio_track_id,
)
from gridplayer.widgets.cell_chrome import paint_idle_disc, paint_solid_outline
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC
from gridplayer.widgets.video_overlay import (
    OverlayBlock,
    OverlayBlockFloating,
    OverlayFakeInvisible,
)
from gridplayer.widgets.video_status import VideoStatus

IN_PROGRESS_THRESHOLD_MS = 500

# A seek sends the time backwards the same way the end of a pass does, and the
# player takes a few time updates to settle on the new position. Loop detection
# stays off for this long after one, so an update sent before the seek landed
# is not mistaken for the video wrapping around.
SEEK_SETTLE_MS = 500

# a pane that has to sit still for an hour before following its size is
# as good as one that never follows it at all
MAX_QUALITY_ADAPT_DELAY_S = 3600

MAX_NETWORK_RETRIES = 1000

# how long to wait before trying a failed network video again. A host that
# just turned us away is unlikely to change its mind within a second, and
# retrying forever at full speed would be indistinguishable from an attack
NETWORK_RETRY_DELAYS_S = (1, 2, 5, 15, 30)


class QStackedLayoutFloating(QStackedLayout):
    """overridden setGeometry for children is not honored due to type casting inside Qt,
    need to override setGeometry in Layout to make floating windows resize with parent

    https://code.qt.io/cgit/qt/qtbase.git/tree/src/widgets/kernel/qstackedlayout.cpp#n474
    """

    def setGeometry(self, rect):
        if self.stackingMode() == QStackedLayout.StackOne:
            widget = self.currentWidget()
            if widget:
                widget.setGeometry(rect)
        if self.stackingMode() == QStackedLayout.StackAll:
            for i in range(self.count()):
                widget = self.itemAt(i).widget()
                if widget:
                    widget.setGeometry(rect)


def only_initialized(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_video_initialized:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_seekable(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if self.is_live:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_with_video_tacks(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.video_tracks:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_live(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_live:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_local_file(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.is_local_file:
            return None
        return func(*args, **kwargs)

    return wrapper


def only_streamable(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.streams:
            return None
        return func(*args, **kwargs)

    return wrapper


def _file_names(file_paths) -> str:
    return ", ".join(file_path.name for file_path in file_paths)


def _audio_files_filter() -> str:
    extensions = " ".join(f"*.{ext}" for ext in sorted(SUPPORTED_AUDIO_EXT))

    audio = translate("Dialog - Add external audio", "Audio", "File formats")
    every = translate("Dialog - Add external audio", "All", "File formats")

    return f"{audio} ({extensions});;{every} (*)"


class VideoBlock(QWidget):
    load_video = pyqtSignal(MediaInput)

    about_to_close = pyqtSignal(str)

    sync_percent_single = pyqtSignal(float)
    sync_time_single = pyqtSignal(MILLISECONDS)
    sync_percent = pyqtSignal(float)
    sync_time = pyqtSignal(MILLISECONDS)
    sync_paused = pyqtSignal(bool)

    time_change = pyqtSignal(MILLISECONDS, MILLISECONDS)
    volume_change = pyqtSignal(float)
    label_change = pyqtSignal(str)
    color_change = pyqtSignal(str)
    loop_start_change = pyqtSignal(float)
    loop_end_change = pyqtSignal(float)
    is_paused_change = pyqtSignal(bool)
    is_stopped_change = pyqtSignal(bool)
    is_muted_change = pyqtSignal(bool)
    info_change = pyqtSignal(str)
    is_in_progress_change = pyqtSignal()
    is_active_change = pyqtSignal(bool)
    is_audio_present_change = pyqtSignal(bool)

    def __init__(self, video_driver, context, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

        # Internal
        self.video_driver_cls = video_driver
        self.id = secrets.token_hex(PLAYER_ID_LENGTH)
        self._ctx = context

        # Static Params
        self.video_params: Video | None = None

        # Runtime Params
        self._is_error = False
        self._is_active = False
        self._is_closing = False
        self._drop_indicator = DropIndicator.NONE

        self._title = None
        self._color = None
        self._default_title = None
        self.is_live = False
        self.streams = Streams()

        self._is_state_change_in_progress = False

        # last time update seen, to tell a finished pass from a running one
        self._last_time = None

        # Components
        self.overlay_hide_timer = QTimer(self)
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self.hide_overlay)

        self._in_progress_timer = QTimer(self)
        self._in_progress_timer.setSingleShot(True)
        self._in_progress_timer.setInterval(IN_PROGRESS_THRESHOLD_MS)
        self._in_progress_timer.timeout.connect(self.is_in_progress_change)

        self._reload_timer = QTimer(self)
        self._reload_timer.timeout.connect(self.reload)

        self._network_retries = 0
        self._network_retry_countdown = 0

        self._network_retry_timer = QTimer(self)
        self._network_retry_timer.setInterval(1000)
        self._network_retry_timer.timeout.connect(self._network_retry_tick)

        self._stream_quality_playing = None
        self._audio_language_playing = None

        # the audio file this load was opened with, which libVLC holds on to
        # until the next one whatever track is picked meanwhile
        self._attached_audio_file: Path | None = None

        self._quality_adapt_timer = QTimer(self)
        self._quality_adapt_timer.setSingleShot(True)
        self._quality_adapt_timer.timeout.connect(self._adapt_stream_quality)

        self._seek_settle_timer = QTimer(self)
        self._seek_settle_timer.setSingleShot(True)
        self._seek_settle_timer.setInterval(SEEK_SETTLE_MS)

        self.url_resolver = self.init_url_resolver()
        self.video_driver: VideoFrameVLC | None = None

        self.overlay = self.init_overlay()

        self.ui_setup()

        self.video_status.show()
        self.overlay.hide()

    def _driver_is_opengl(self) -> bool:
        cls = self.video_driver_cls
        if isinstance(cls, partial):
            cls = cls.func
        return bool(getattr(cls, "is_opengl", False))

    def init_video_driver(self) -> VideoFrameVLC:
        vlc_options = get_vlc_options(self.video_params)
        self._log.debug(f"vlc_options: {vlc_options}")

        video_driver = self.video_driver_cls(vlc_options=vlc_options, parent=self)

        qt_connect(
            (video_driver.video_ready, self.load_video_finish),
            (video_driver.tracks_changed, self.tracks_changed),
            (video_driver.time_changed, self.time_changed),
            (video_driver.playback_status_changed, self.playback_status_changed),
            (video_driver.error, self.video_driver_error),
            (video_driver.crash, self.crash),
            (video_driver.update_status, self.update_status),
            (self.load_video, video_driver.load_video),
        )

        return video_driver

    def _ensure_video_driver(self) -> VideoFrameVLC:
        if self.video_driver is not None:
            return self.video_driver

        self.video_driver = self.init_video_driver()
        overlay_index = self.layout_main.indexOf(self.overlay)
        if overlay_index < 0:
            self.layout_main.addWidget(self.video_driver)
        else:
            self.layout_main.insertWidget(overlay_index, self.video_driver)
        self._hide_video_driver()
        return self.video_driver

    def _hide_video_driver(self):
        if self.video_driver is None:
            return

        # Don't hide VLC HW frame widget, otherwise first frame comes out glitchy and takes time to normalize
        # Happens only on Windows
        # Possibly related issue - short ~100-300ms "freeze-frame" lag before video starts actually playing
        # especially noticeable on streaming vids, also happens on Linux
        if env.IS_WINDOWS and self._driver_is_opengl():
            return

        self.video_driver.hide()

    def _destroy_video_driver(self):
        self._is_state_change_in_progress = False
        self._in_progress_timer.stop()

        if self.video_driver is None:
            return

        self.load_video.disconnect()
        self.video_driver.video_ready.disconnect()
        self.video_driver.time_changed.disconnect()
        self.video_driver.playback_status_changed.disconnect()
        self.video_driver.error.disconnect()
        self.video_driver.crash.disconnect()
        self.video_driver.update_status.disconnect()

        old_driver = self.video_driver
        self.video_driver = None
        self.layout_main.removeWidget(old_driver)
        old_driver.hide()
        old_driver.cleanup()
        old_driver.deleteLater()

    def init_url_resolver(self):
        url_resolver = VideoURLResolver(parent=self)
        url_resolver.error.connect(self.network_error)
        url_resolver.url_resolved.connect(self.set_video_url)
        url_resolver.update_status.connect(self.update_status)

        return url_resolver

    def reset_url_resolver(self):
        self.url_resolver.error.disconnect()
        self.url_resolver.url_resolved.disconnect()

        self.url_resolver.cleanup()

        self.url_resolver = self.init_url_resolver()

    def reset(self):
        self._is_error = False
        self.set_status("processing")

        self._destroy_video_driver()
        self.reset_url_resolver()

    def init_overlay(self):
        if self._driver_is_opengl():
            if Settings().get("internal/fake_overlay_invisibility"):
                overlay = OverlayFakeInvisible(self)
            else:
                overlay = OverlayBlockFloating(self)
            self.installEventFilter(overlay)
        else:
            overlay = OverlayBlock(self)

        qt_connect(
            (overlay.set_vid_pos, partial(self.manual_seek, "seek_percent")),
            (overlay.set_volume, self.set_volume),
            (overlay.exit_clicked, self.close),
            (overlay.play_pause_clicked, self.play_pause),
            (overlay.mute_unmute_clicked, self.mute_unmute),
            (self.time_change, overlay.set_position),
            (self.volume_change, overlay.set_volume_position),
            (self.label_change, overlay.set_label),
            (self.color_change, overlay.set_color),
            (self.loop_start_change, overlay.set_loop_start),
            (self.loop_end_change, overlay.set_loop_end),
            (self.is_paused_change, overlay.set_is_paused),
            (self.is_stopped_change, overlay.set_is_stopped),
            (self.is_in_progress_change, overlay.set_is_in_progress),
            (self.is_muted_change, overlay.set_is_muted),
            (self.info_change, overlay.set_info_label),
            (self.is_active_change, overlay.set_is_active),
            (self.is_audio_present_change, overlay.set_volume_button_visible),
        )

        return overlay

    def ui_setup(self):
        self.setMouseTracking(True)

        if self._driver_is_opengl():
            self.layout_main = QStackedLayoutFloating(self)
        else:
            self.layout_main = QStackedLayout(self)

        self.layout_main.setSpacing(0)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setStackingMode(QStackedLayout.StackAll)

        self.video_status = VideoStatus(
            parent=self, status_text=translate("Video Status", "Initializing")
        )
        self.video_status.setMouseTracking(True)
        self.video_status.setWindowFlags(Qt.WindowTransparentForInput)

        self.layout_main.addWidget(self.video_status)
        self.layout_main.addWidget(self.overlay)

        if type(self.overlay) is OverlayBlock:
            self.overlay.raise_()

    def crash(self, traceback_txt):
        raise PlayerException(traceback_txt)

    def cleanup_start(self):
        """Ask the video driver to release itself, without waiting for it.

        Closing a grid goes through here first so every pane starts releasing
        at once; the waiting happens later, in cleanup().
        """
        if self.video_driver is not None:
            self.video_driver.cleanup_start()

    def cleanup(self):
        self.overlay_hide_timer.stop()
        self._in_progress_timer.stop()
        self._network_retry_timer.stop()
        self._quality_adapt_timer.stop()

        self._log.debug(f"{self.id}: cleaning up resolver")
        self.url_resolver.cleanup()

        self._log.debug(f"{self.id}: cleaning up driver ")
        self._destroy_video_driver()

        self._log.debug(f"{self.id}: cleaning up done")

    def video_driver_error(self, error):
        self.update_status(translate("Video Error", error))

        if not self.video_params.is_local_file:
            return self.network_error()

        return self.error()

    def error(self):
        self._is_error = True
        self._is_state_change_in_progress = False
        self.set_status("error")
        self.cleanup()

    def network_error(self):
        if self._schedule_network_retry():
            return

        self._network_retries = 0

        self._is_error = True
        self._is_state_change_in_progress = False
        self.set_status("network-error")
        self.cleanup()

    def _schedule_network_retry(self) -> bool:
        """Try the video again later instead of giving up on it.

        Streams break for reasons that pass: a host hiccups, a laptop wakes
        up with no network yet, a signed URL runs out. Showing the error is
        the last resort, not the first answer.
        """

        retry_limit = self._network_retry_limit

        if retry_limit == 0:
            return False

        if retry_limit > 0 and self._network_retries >= retry_limit:
            self._log.debug(f"Giving up after {self._network_retries} retries")
            return False

        self._network_retries += 1

        delay_idx = min(self._network_retries - 1, len(NETWORK_RETRY_DELAYS_S) - 1)
        self._network_retry_countdown = NETWORK_RETRY_DELAYS_S[delay_idx]

        self._log.debug(
            f"Network error, retry {self._network_retries}"
            f" in {self._network_retry_countdown}s"
        )

        self._is_error = False
        self._is_state_change_in_progress = False

        # the driver is of no use until the video is loaded again, and
        # holding on to it keeps a VLC player busy for the whole wait
        self.cleanup()

        self.set_status("network-error")
        self._show_network_retry_status()

        self._network_retry_timer.start()

        return True

    def _network_retry_tick(self):
        self._network_retry_countdown -= 1

        if self._network_retry_countdown > 0:
            self._show_network_retry_status()
            return

        self._network_retry_timer.stop()

        if self._is_closing or self.video_params is None:
            return

        self.reload()

    def _show_network_retry_status(self):
        self.update_status(
            translate("Video Status", "Reconnecting in {SECONDS}s ({ATTEMPT})").format(
                SECONDS=self._network_retry_countdown,
                ATTEMPT=self._network_retry_attempt_txt,
            )
        )

    @property
    def _network_retry_attempt_txt(self) -> str:
        retry_limit = self._network_retry_limit

        if retry_limit < 0:
            return str(self._network_retries)

        return f"{self._network_retries}/{retry_limit}"

    def set_status(self, status):
        self.overlay.hide()
        self._hide_video_driver()

        self.video_status.icon = status
        self.video_status.show()
        self.repaint()

    def update_status(self, info_text, percent=0):
        self.video_status.status_text = translate("Video Status", info_text)
        self.video_status.percent = percent

    def reload(self):
        self._network_retry_timer.stop()
        self._quality_adapt_timer.stop()

        self.is_live = False
        self._is_error = False
        self.streams = Streams()
        self._title = None
        self._default_title = None

        self.reset()

        video_params = self.video_params
        self.video_params = None

        self.set_video(video_params)

    def close_silently(self):
        self.close(notify=False)

    def close(self, notify=True):
        if self._is_closing:
            return

        self._is_closing = True

        self._log.debug(f"Closing video block {self.id}")

        if notify:
            self.about_to_close.emit(self.id)

        super().close()

    def closeEvent(self, event) -> None:
        self.cleanup()
        event.accept()

    def wheelEvent(self, event):
        if self._ctx.is_disable_mouse_wheel_events:
            event.ignore()
            return

        if self._dispatch_mouse_action(event):
            # Accept so the event does not bubble to Player and re-trigger
            # the same mouse shortcut (e.g. open Settings twice).
            event.accept()
            return

        event.ignore()

    def mousePressEvent(self, event) -> None:
        if Settings().get("internal/fake_overlay_invisibility"):
            self.window().raise_()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # Overlay hide-on-timeout hides the overlay widget, so hover activity
        # never comes from overlay children. Restart the overlay from the cell
        # itself — including stopped tiles with no VLC widget.
        self.show_overlay()
        event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        if self._ctx.is_disable_mouse_click_events:
            event.ignore()
            return

        if self._dispatch_mouse_action(event):
            event.accept()
            return

        event.ignore()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._ctx.is_disable_mouse_click_events:
            event.ignore()
            return

        if self._dispatch_mouse_action(event):
            event.accept()
            return

        event.ignore()

    def _dispatch_mouse_action(self, event) -> bool:
        try:
            actions_manager = self._ctx.actions_manager
        except KeyError:
            return False
        return actions_manager.handle_mouse_event(event)

    def hideEvent(self, event):
        # OverlayBlockFloating is a Qt.Tool window, so hiding this cell does
        # not hide it. Always unmap it here — hide_overlay() is chrome-timeout
        # policy and is a no-op when overlays stay visible.
        self.overlay_hide_timer.stop()
        self.overlay.hide()

    def paintEvent(self, event):
        super().paintEvent(event)
        self._paint_stopped_chrome()

    def _paint_stopped_chrome(self):
        if not self.is_stopped:
            return
        paint_solid_outline(self)
        if self._drop_indicator == DropIndicator.NONE:
            paint_idle_disc(self)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_overlay_size_policy()
        self._schedule_quality_adapt()

    @property
    def is_overlay_fits(self) -> bool:
        return (
            self.width() >= CHROME_MIN_SIZE[0] and self.height() >= CHROME_MIN_SIZE[1]
        )

    def _apply_overlay_size_policy(self):
        if not self.is_overlay_fits:
            self.overlay_hide_timer.stop()
            self.overlay.hide()
            return

        if not self._ctx.is_overlay_hide_on_timeout:
            self.show_overlay()

    def showEvent(self, event):
        if not self._ctx.is_overlay_hide_on_timeout:
            self.show_overlay()

    def customEvent(self, event):
        if event.type() == OVERLAY_ACTIVITY_EVENT:
            self.show_overlay()

    @only_initialized
    @only_seekable
    def manual_seek(self, command, *args):
        getattr(self, command)(*args)

        # a seek past the end is the end arriving early, and the end action
        # may have taken the player away with it -- stopped, closed, or left
        # loading the next file, with no position to report either way
        if not self.is_video_initialized:
            return

        if command in {"next_frame", "previous_frame"} and self.video_tracks:
            self.sync_paused.emit(True)

        self.sync_percent.emit(self.position)
        self.sync_time.emit(int(self.video_driver.length * self.position))

    @only_initialized
    @only_seekable
    def sync_others_percent(self):
        self.sync_percent_single.emit(self.position)

    @only_initialized
    @only_seekable
    def sync_others_time(self):
        self.sync_time_single.emit(int(self.video_driver.length * self.position))

    @only_initialized
    @only_seekable
    def seek_timecode(self):
        time_ms = QCustomSpinboxTimeInput.get_time_ms_int(
            self.parent(),
            translate("Dialog - Enter timecode", "Enter timecode", "Header"),
        )

        if time_ms is None:
            return

        self.manual_seek("seek", time_ms)

    def set_network_retry_mode(self, mode):
        self.video_params.network_retry_mode = mode

        # a new policy starts with a full budget rather than what is left
        self._network_retries = 0

        if not self._network_retry_timer.isActive():
            return

        if self._network_retry_limit != 0:
            return

        # the reload this video was counting down to has just been called off
        self._network_retry_timer.stop()
        self.network_error()

    def network_retry_times(self):
        times = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate(
                "Dialog - Set reload attempts", "Set reload attempts", "Header"
            ),
            initial_value=self.video_params.network_retry_times,
            _min=1,
            _max=MAX_NETWORK_RETRIES,
        )

        self.video_params.network_retry_times = times

        self._network_retries = 0

    def get_network_retry_times(self):
        return str(self.video_params.network_retry_times)

    @only_streamable
    def quality_adapt_delay(self):
        delay_sec = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate(
                "Dialog - Set quality adapt delay", "Set quality adapt delay", "Header"
            ),
            initial_value=self.video_params.quality_adapt_delay_sec,
            _min=1,
            _max=MAX_QUALITY_ADAPT_DELAY_S,
        )

        self.set_quality_adapt_delay(delay_sec)

    @only_streamable
    def set_quality_adapt_delay(self, delay_sec):
        self.video_params.quality_adapt_delay_sec = delay_sec

        # a pane already waiting was counting to the old delay
        if self._quality_adapt_timer.isActive():
            self._quality_adapt_timer.start(self._quality_adapt_delay_ms)

    @only_streamable
    def get_quality_adapt_delay(self):
        return "{} {}".format(
            self.video_params.quality_adapt_delay_sec,
            translate("Quality Adapt Delay", "second(s)"),
        )

    @only_initialized
    @only_live
    def auto_reload_timer(self):
        time_min = QCustomSpinboxInput.get_int(
            parent=self.parent(),
            title=translate(
                "Dialog - Set auto reload timer", "Set auto reload timer", "Header"
            ),
            special_text=translate("Auto Reload Timer", "Disabled"),
            initial_value=self.video_params.auto_reload_timer_min,
            _min=0,
            _max=1000,
        )

        self.set_auto_reload_timer(time_min)

    @only_initialized
    @only_live
    def set_auto_reload_timer(self, time_min):
        self.video_params.auto_reload_timer_min = time_min

        time_ms = time_min * 60 * 1000

        if time_ms == 0:
            self._reload_timer.stop()
            self._reload_timer.setInterval(0)
            return

        self._reload_timer.setInterval(time_ms)
        self._reload_timer.start()

    @only_initialized
    @only_live
    def get_auto_reload_timer(self):
        if self.video_params.auto_reload_timer_min == 0:
            return translate("Auto Reload Timer", "Disabled")

        return "{} {}".format(
            self.video_params.auto_reload_timer_min,
            translate("Auto Reload Timer", "minute(s)"),
        )

    def is_under_cursor(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, is_active):
        self._is_active = is_active

        if is_active and not self._ctx.is_show_overlay_border:
            return

        self.is_active_change.emit(is_active)

    def refresh_overlay_border(self):
        self.is_active_change.emit(self._is_active and self._ctx.is_show_overlay_border)

    @property
    def drag_data(self):
        return VideoBlockMime(id=self.id, video=self.video_params)

    @property
    def size_tuple(self) -> tuple[int, int]:
        return self.size().width(), self.size().height()

    @property
    def is_video_initialized(self):
        if self.video_driver is None:
            return False

        return self.video_driver.is_video_initialized

    @property
    def is_local_file(self):
        return isinstance(self.video_params.uri, Path)

    @property
    def video_tracks(self):
        if self.video_driver is None or not self.is_video_initialized:
            return {}
        return self.video_driver.video_tracks

    @property
    def audio_tracks(self):
        if self.video_driver is None or not self.is_video_initialized:
            return {}
        return self.video_driver.audio_tracks

    def set_audio_track(self, track_id):
        self._log.debug(
            f"Set audio track {track_id},"
            f" initialized={self.is_video_initialized},"
            f" video track off={self._is_video_track_off}"
        )

        if track_id == DISABLED_TRACK and self._is_video_track_off:
            self._ctx.commands.warning(
                translate("Warning", "Cannot disable both video & audio tracks")
            )
            return

        # a track chosen by hand outranks the languages asked for, and has
        # to outlive the reload that would otherwise resolve them again
        self.video_params.audio_selection = self._audio_selection_for(track_id)

        # a video part way through a reload has no tracks to switch between
        # yet, and will settle on this one once it does
        if self.is_video_initialized:
            self.video_driver.set_audio_track(track_id)

    def _audio_selection_for(self, track_id):
        """How to remember this track, by the steadiest name it answers to.

        A file of its own keeps its name whatever the tracks do, a language
        outlives a source that renumbers them, and an id is what is left
        where neither says anything.
        """

        if track_id == DISABLED_TRACK:
            return AudioDisabled()

        external_file = self.external_audio_tracks.get(track_id)

        if external_file is not None:
            return AudioExternal(
                file=external_file,
                track=self.external_audio_track_ids.index(track_id),
            )

        language = self._track_language_key(track_id)

        if language is not None:
            return AudioLanguage(tag=language)

        return AudioTrackId(id=track_id)

    def restore_audio_selection(self, selection) -> None:
        """Put a remembered choice of sound back in force, as a snapshot does."""

        self.video_params.audio_selection = selection

        self._apply_wanted_audio_track()

    @property
    def _is_video_track_off(self) -> bool:
        """Whether there would be nothing left to watch without the sound.

        Only an id of -1 says the picture was switched off. None says the
        player had nothing to report when it was last asked, which is not
        the same thing and must not cost the sound.
        """

        if self.video_driver is None or not self.is_video_initialized:
            # part way through a load, where the player settles this itself
            return False

        return self.video_driver.cur_video_track_id == DISABLED_TRACK

    def _track_language_key(self, track_id) -> str | None:
        """The language to remember this track by, where one will do.

        An id is only as good as the media it was read from, and a stream
        is demuxed afresh on every reload. A language outlives that, but
        only while it picks out one track rather than several.
        """

        track = self.audio_tracks.get(track_id)

        if track is None or not track.language:
            return None

        namesakes = [
            other
            for other in self.audio_tracks.values()
            if normalize(other.language) == normalize(track.language)
        ]

        return track.language if len(namesakes) == 1 else None

    @property
    def audio_track_playing(self) -> int | None:
        """Which track the sound is coming from, whatever was asked for.

        What was asked for can be a preference rather than a track, and
        then this is the only place the answer it came to is written down.
        """

        if self.video_driver is None or not self.is_video_initialized:
            return None

        return self.video_driver.cur_audio_track_id

    @property
    def audio_language_playing(self) -> str | None:
        """Which of the languages on offer the rung on screen was loaded for."""

        return self._audio_language_playing

    @property
    def preferred_audio_track_id(self) -> int | None:
        """The track this file would open with, were nothing picked by hand."""

        return pick_track(self.video_params.audio_languages, self.audio_tracks)

    def apply_audio_default(self):
        """Leave the sound to the video's own file, preference and all."""

        self.video_params.audio_selection = AudioDefault()

        self._apply_wanted_audio_track()

    def apply_audio_preference(self):
        """Follow the preferred languages again, whichever way this video dubs.

        A dubbed stream is served one language at a time, so going back to
        the preference means fetching it again rather than reaching for a
        track that was never handed over.
        """

        self.video_params.audio_selection = AudioPreferred()

        if self._language_variants.is_multilingual:
            self.set_audio_language(None)

        # a reload only happens where the language changed, so the tracks
        # in hand still have to be settled either way
        self._apply_wanted_audio_track()

    def _apply_wanted_audio_track(self):
        """Put the settings into effect on the video that is already playing."""

        if self.video_driver is None or not self.is_video_initialized:
            # part way through a reload, which will settle this on its own
            return

        track_id = self._wanted_audio_track_id()

        if track_id is None:
            if self.video_driver.cur_audio_track_id not in NO_TRACK:
                # something is playing already and nothing was asked for by
                # name, so there is nothing here worth moving off
                return

            # a "disable" is still in force and the preference has no
            # opinion, so any track at all beats going on in silence
            track_id = next(iter(self.audio_tracks), None)

        if track_id is None:
            return

        self.video_driver.set_audio_track(track_id)

    def _wanted_audio_track_id(self) -> int | None:
        """Which track this video's settings call for, its own files included.

        Only the block knows which track came out of which file, so a pick
        of one is answered here; everything else the video can answer for
        itself.
        """

        selection = self.video_params.audio_selection

        if isinstance(selection, AudioDefault):
            return self.default_audio_track_id

        if isinstance(selection, AudioExternal):
            if selection.file == self.attached_audio_file:
                picked = track_of_file(selection, self.external_audio_track_ids)

                if picked is not None:
                    return picked

        return wanted_audio_track_id(self.video_params, self.audio_tracks)

    @only_initialized
    def audio_languages_dialog(self):
        """Edit the languages this video would rather be heard in."""

        languages = QCustomTextInput.get_text(
            parent=self.parent(),
            title=translate(
                "Dialog - Set preferred audio languages",
                "Preferred audio languages",
                "Header",
            ),
            initial_value=self.video_params.audio_languages,
            placeholder=translate("Dialog - Set preferred audio languages", "en, ja"),
        )

        self.set_audio_languages(languages)

    def set_audio_languages(self, languages: str):
        if languages == self.video_params.audio_languages:
            return

        self.video_params.audio_languages = languages

        if not isinstance(self.video_params.audio_selection, AudioPreferred):
            return

        # the preference is what is being followed, so following it again
        # is the whole point of having changed it
        self.apply_audio_preference()

    def get_audio_languages(self) -> str:
        return self.video_params.audio_languages or translate("Audio Languages", "any")

    @property
    def discovered_audio_files(self) -> list[Path]:
        """Audio files named after this video that nobody has picked yet.

        Finding them is a directory listing and nothing else. A file here
        has not been opened and costs nothing until it is chosen, which is
        what makes it safe to look on every video in the grid.
        """

        if (
            not self.is_local_file
            or not self.video_params.is_external_audio_autodiscover
        ):
            return []

        attached = set(self.video_params.external_audio)

        return [
            found
            for found in discover_audio_files(self.video_params.uri)
            if found not in attached
        ]

    @property
    def external_audio_track_ids(self) -> tuple[int, ...]:
        """The tracks that came out of a file, as the player saw them arrive.

        More than one where the file holds more than one, which is theirs
        to tell apart: with a single file attached, every track past the
        video's own came out of it.
        """

        if self.video_driver is None or not self.is_video_initialized:
            return ()

        return self.video_driver.external_audio_ids

    @property
    def default_audio_track_id(self) -> int | None:
        """The track the video's own file puts forward.

        What libVLC opened on, as long as that was the video's own doing.
        A file attached at load takes the sound for itself as soon as its
        stream arrives, and what libVLC opened on is then that file -- no
        answer at all to what the video would have played alone. The first
        of its own tracks is as close as this gets to one.
        """

        if self.video_driver is None or not self.is_video_initialized:
            return None

        from_file = set(self.external_audio_track_ids)

        own_tracks = [
            track_id for track_id in self.audio_tracks if track_id not in from_file
        ]

        opened_on = self.video_driver.default_audio_track_id

        if opened_on in own_tracks:
            return opened_on

        return own_tracks[0] if own_tracks else None

    @property
    def attached_audio_file(self) -> Path | None:
        """The external audio libVLC was really handed, if any.

        Not the same question as which sound was chosen: libVLC never takes
        a file back, so one handed over is still there after the viewer
        switches to a track of the video's own, and its track is still in
        the list wearing its name. Only a fresh load changes this.

        One at a time, since libVLC never says which stream came from which
        file and two of them would leave the pair to be told apart by
        guesswork.
        """

        return self._attached_audio_file

    @property
    def _audio_file_to_attach(self) -> Path | None:
        """The file the next load is to open this video with.

        A file that is no longer where the playlist left it -- renamed, or
        on a drive nobody plugged in -- is no use to libVLC, though it
        keeps its place in the list in case whatever moved it moves it back.
        """

        selection = self.video_params.audio_selection

        if not isinstance(selection, AudioExternal):
            return None

        if not selection.file.is_absolute() or not selection.file.is_file():
            return None

        return selection.file

    @property
    def offered_audio_files(self) -> list[Path]:
        """Files this video can be played with, other than the one it is on."""

        attached = self.attached_audio_file

        known = [
            file_path
            for file_path in self.video_params.external_audio
            # one that is not there cannot be played, and a row that does
            # nothing is worse than no row
            if file_path != attached and file_path.is_file()
        ]

        return known + self.discovered_audio_files

    @property
    def external_audio_tracks(self) -> dict[int, Path]:
        """Which file each external track came out of, where there is one."""

        file_path = self.attached_audio_file

        if file_path is None:
            return {}

        return dict.fromkeys(self.external_audio_track_ids, file_path)

    @property
    def selected_audio_slave_uri(self) -> str | None:
        """The file the video is to be played with, for the player to find."""

        wanted = self._audio_file_to_attach

        return None if wanted is None else wanted.as_uri()

    @only_local_file
    def add_external_audio_dialog(self) -> None:
        """Pick audio files to play this video with."""

        file_names, _ = QFileDialog.getOpenFileNames(
            self.parent(),
            translate("Dialog - Add external audio", "Add External Audio", "Header"),
            str(self.video_params.uri.parent),
            _audio_files_filter(),
        )

        self.add_external_audio([Path(file_name) for file_name in file_names])

    def add_external_audio(self, file_paths) -> None:
        """Play these audio files with the video, starting on the first.

        One picked while the video is up goes on where it stands: VLC takes
        a file at any time, so nothing has to be loaded again for it.
        """

        new_files = [
            file_path
            for file_path in file_paths
            if file_path.is_absolute()
            and file_path not in self.video_params.external_audio
        ]

        if not new_files:
            return

        self._warn_about_awkward_audio(new_files)

        self.video_params.external_audio = [
            *self.video_params.external_audio,
            *new_files,
        ]

        # sound asked for by name outranks the languages asked for, the same
        # way picking a track by hand does
        self.video_params.audio_selection = AudioExternal(file=new_files[0])

        self._put_external_audio_into_effect()

    def _forget_audio_file_that_is_gone(self) -> None:
        """Let go of a pick whose file is not where the playlist left it.

        A choice naming nothing on the disk is one the menu cannot show as
        taken, and a video that looks as though nothing at all is chosen
        reads worse than one back on the sound it would otherwise open on.
        The file keeps its place in the list, in case whatever moved it
        moves it back.
        """

        selection = self.video_params.audio_selection

        if not isinstance(selection, AudioExternal):
            return

        if self._audio_file_to_attach is not None:
            return

        self._log.debug(f"{selection.file.name} is not there any more")

        self.video_params.audio_selection = default_audio_selection()

    def _put_external_audio_into_effect(self) -> None:
        """Play the file that was picked, the cheapest way that is certain.

        libVLC takes a file at any time but never gives one back, and it
        never says which stream came from which file. A video that has one
        already is therefore loaded again rather than handed a second,
        which costs a moment and leaves no room for a mix-up.
        """

        if not self.is_video_initialized:
            # part way through a load, which will open it with the video
            return

        if self._attached_audio_file is not None:
            self._log.debug("A file is on already, loading the video again")

            self.reload()
            return

        wanted = self._audio_file_to_attach

        if wanted is not None:
            self._attached_audio_file = wanted

            self.video_driver.add_audio_slave(wanted.as_uri())

    def _warn_about_awkward_audio(self, file_paths) -> None:
        """Say so where libVLC will not make a sound of what was picked.

        The files are taken anyway: this is what one build of VLC does with
        them, and being told beats a track that sits there silently.
        """

        unplayable = unplayable_as_audio_slave(file_paths)
        silenced = silenced_by_seeking(file_paths)

        warnings = []

        if unplayable:
            warnings.append(
                translate(
                    "Warning",
                    "VLC cannot play {FILES} alongside a video.",
                ).format(FILES=_file_names(unplayable))
            )

        if silenced:
            warnings.append(
                translate(
                    "Warning",
                    "{FILES} will fall silent once the video is seeked.",
                ).format(FILES=_file_names(silenced))
            )

        if not warnings:
            return

        warnings.append(
            translate("Warning", "Convert to MP3, M4A, FLAC or AC3 to play it.")
        )

        self._ctx.commands.warning("\n\n".join(warnings))

    def play_external_audio(self, file_name: str) -> None:
        """Hear this file, whether it has been attached yet or not."""

        file_path = Path(file_name)

        if file_path == self.attached_audio_file:
            # it is on already, and may only have been switched away from
            if self.external_audio_track_ids:
                self.set_audio_track(self.external_audio_track_ids[0])

            return

        if file_path not in self.video_params.external_audio:
            self.add_external_audio([file_path])
            return

        self.video_params.audio_selection = AudioExternal(file=file_path)

        self._put_external_audio_into_effect()

    def remove_external_audio(self) -> None:
        """Play the video on its own sound again.

        libVLC has no way to take back a file it has been handed, so the
        video is loaded once more, this time without them.
        """

        if not self.video_params.external_audio:
            return

        is_external_playing = isinstance(
            self.video_params.audio_selection, AudioExternal
        )

        self.video_params.external_audio = []

        if is_external_playing:
            # the track that was playing leaves with the file it came from,
            # so the video goes back to whatever it would have opened on
            self.video_params.audio_selection = default_audio_selection()

        self.reload()

    def set_external_audio_autodiscover(self, is_on: bool) -> None:
        """Whether to offer the audio files kept beside this video."""

        self.video_params.is_external_audio_autodiscover = is_on

    def tracks_changed(self) -> None:
        """Take note of a track that appeared after the video was loaded.

        What is playing is the player's business, not the choice's: writing
        it back here is what used to turn "go by my languages" into "play
        track three" behind the viewer's back.
        """

        self.is_audio_present_change.emit(bool(self.audio_tracks))

        if self._is_external_audio_short:
            # libVLC took the file and brought nothing back, which some
            # formats do when handed to a video that is already playing.
            # Opening them with the video is the way that always works.
            self._log.debug("External audio brought no track, loading it again")

            self.reload()

    @property
    def _is_external_audio_short(self) -> bool:
        """Whether the file that was handed over has no track to show for it."""

        return (
            self.attached_audio_file is not None and not self.external_audio_track_ids
        )

    def _adopt_audio_if_silent(self) -> None:
        """Give a video with no sound of its own the one file found beside it.

        A silent video next to an audio file named after it is the one case
        where doing nothing reads as a fault rather than as a choice. Where
        several were found, which of them to play is nobody's guess but the
        viewer's, and they are left in the menu to be picked from.
        """

        if self.audio_tracks or self.video_params.external_audio:
            return

        found = self.discovered_audio_files

        if len(found) != 1:
            return

        self._log.debug(f"Adopting {found[0].name} as the sound of a silent video")

        self.add_external_audio(found)

    @only_initialized
    def set_video_track(self, track_id):
        # only -1 says the sound was switched off; None says it has not been
        # read back, which is no reason to keep the picture
        if track_id == DISABLED_TRACK and isinstance(
            self.video_params.audio_selection, AudioDisabled
        ):
            self._ctx.commands.warning(
                translate("Warning", "Cannot disable both video & audio tracks")
            )
            return

        self.video_params.video_track_id = track_id
        self.video_driver.set_video_track(track_id)

    @only_initialized
    def set_audio_channel_mode(self, mode):
        if not self.audio_tracks:
            return

        self.video_params.audio_channel_mode = mode
        self.video_driver.set_audio_channel_mode(mode)

    @property
    def video_id(self) -> str:
        return str(self.video_params.id)

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, title):
        self._title = title
        self.label_change.emit(self._title)

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, color):
        self._color = color
        self.color_change.emit(color)

    @property
    def time(self):
        return self.video_params.current_position

    @time.setter
    @only_initialized
    def time(self, time):
        if not self.is_live:
            self.video_params.current_position = time

        self.time_change.emit(time, self.video_driver.length)

    @property
    def position(self):
        if not self.time or not self.video_driver.length:
            return 0

        return self.time / self.video_driver.length

    @property
    def loop_start(self):
        if self.video_params.loop_start is None:
            return 0

        return self.video_params.loop_start

    @property
    def loop_end(self):
        if self.video_params.loop_end is None:
            length = 0
            if self.video_driver is not None:
                length = self.video_driver.length
            # No margin before the actual end: VLC wraps the input around on
            # its own, and a finished pass is caught after the fact
            return length

        return self.video_params.loop_end

    @property
    def is_end_a_loop(self) -> bool:
        """Whether reaching the end here only starts the video over again.

        A segment is a loop whatever the end action says, and so is the end
        action that loops the file. Everything else leaves the video behind.
        """

        is_segment = (
            self.video_params.loop_start is not None
            or self.video_params.loop_end is not None
        )

        return is_segment or self.video_params.end_action == VideoEndAction.LOOP_FILE

    def set_drop_indicator(self, indicator: DropIndicator):
        self._drop_indicator = indicator
        opaque_drag = self._ctx.is_drag_ui and getattr(self.overlay, "is_opaque", False)
        # Unmap before clearing Shape; setMask on a mapped opaque window
        # flashes Window fill (default white) over the whole cell.
        if indicator == DropIndicator.NONE and opaque_drag:
            self.overlay.hide()
        self.overlay.set_drop_indicator(indicator)
        if self.is_stopped:
            self.update()
        if indicator != DropIndicator.NONE:
            self.overlay.show()
            self.overlay_hide_timer.stop()

    def set_drag_ui(self, is_drag_ui: bool):
        if is_drag_ui and getattr(self.overlay, "is_opaque", False):
            if self._drop_indicator == DropIndicator.NONE:
                self.overlay.hide()
        self.overlay.set_is_chrome_visible(not is_drag_ui)
        if self.is_stopped:
            self.update()
        if is_drag_ui:
            self.overlay_hide_timer.stop()
            return

        self.set_drop_indicator(DropIndicator.NONE)
        if self._ctx.is_disable_overlay:
            self.overlay_hide_timer.stop()
            self.overlay.hide()
            return
        if self._ctx.is_overlay_hide_on_timeout:
            self.overlay_hide_timer.stop()
            self.overlay.hide()
            return
        self.show_overlay()

    @property
    def is_stopped(self) -> bool:
        return bool(self.video_params and self.video_params.is_stopped)

    def _sync_cell_background(self) -> None:
        # HW vout is a native child. Filling this widget on expose paints
        # QPalette.Window (white) over the whole cell.
        fill = self.is_stopped
        self.setAttribute(Qt.WA_StyledBackground, fill)
        self.setAutoFillBackground(fill)

    @property
    def is_playable(self) -> bool:
        return self.is_video_initialized or self.is_stopped

    @property
    def is_loading(self) -> bool:
        return (
            not self.is_video_initialized and not self.is_stopped and not self._is_error
        )

    def show_overlay(self):
        if self._ctx.is_drag_ui or self._ctx.is_disable_overlay:
            return
        if self.is_loading or self._is_error:
            return
        # Floating overlays are independent windows; do not remap them while
        # this cell is hidden (single-mode background, minimized, etc.).
        if not self.isVisible():
            return
        if not self.is_overlay_fits:
            return

        self.overlay.show()
        if self._ctx.is_overlay_hide_on_timeout:
            self.overlay_hide_timer.start(1000 * self._ctx.overlay_timeout)

    def hide_overlay(self):
        if self._ctx.is_drag_ui:
            return

        if self._ctx.is_disable_overlay:
            self.overlay_hide_timer.stop()
            self.overlay.hide()
            return

        if not self._ctx.is_overlay_hide_on_timeout:
            return

        self.overlay.hide()

    @only_initialized
    def time_changed(self, new_time):
        is_wrapped = self._is_loop_wrapped(new_time)

        self.time = new_time

        if self.is_live:
            return

        if self.is_stopped:
            return

        if is_wrapped:
            self._loop_wrapped()
            return

        # 100ms headspace for slow callbacks
        if self.time < self.loop_start - 100:
            self.seek(self.loop_start)

        elif self.time > self.loop_end:
            self.loop_end_action()

    def _is_loop_wrapped(self, new_time) -> bool:
        """Has the video begun another pass since the last time update?"""

        if self._seek_settle_timer.isActive():
            return False

        last_time, self._last_time = self._last_time, new_time

        return is_loop_wrapped(last_time, new_time, self.video_driver.length)

    def _loop_wrapped(self):
        """The video wrapped around on its own, mind whatever is left to do."""

        is_plain_loop = (
            self.video_params.end_action == VideoEndAction.LOOP_FILE
            and self.video_params.loop_start is None
            and not self.video_params.is_start_random
        )

        # VLC has already looped it seamlessly, which is the whole point
        if is_plain_loop:
            return

        self.loop_end_action()

    def playback_status_changed(self, is_paused):
        self._is_state_change_in_progress = False
        self._in_progress_timer.stop()

        self._set_playback_state(
            VideoInitialState.PAUSED if is_paused else VideoInitialState.PLAYING
        )

    def loop_end_action(self):
        # A loop start without an end is still a segment: start → EOF.
        if (
            self.video_params.loop_end is not None
            or self.video_params.loop_start is not None
        ):
            self._loop_to_start()
            return

        end_action = self.video_params.end_action
        if end_action == VideoEndAction.LOOP_FILE:
            self._loop_to_start()
        elif end_action == VideoEndAction.NEXT_FILE:
            self.next_video()
        elif end_action == VideoEndAction.PREVIOUS_FILE:
            self.previous_video()
        elif end_action == VideoEndAction.SHUFFLE_FILE:
            self.shuffle_video()
        elif end_action == VideoEndAction.PAUSE:
            self._pause_at_start()
        elif end_action == VideoEndAction.STOP:
            self.stop_playback()
        elif end_action == VideoEndAction.CLOSE:
            QTimer.singleShot(0, self.close)

    def _loop_to_start(self):
        if self.video_params.is_start_random:
            self.seek_random()
        else:
            self.seek(self.loop_start)

    def _pause_at_start(self):
        self.seek(self.loop_start)
        self.set_pause(True)

    def stop_playback(self):
        if self.video_params is not None:
            self.video_params.current_position = 0
            self.video_params.loop_start = None
            self.video_params.loop_end = None
            self.loop_start_change.emit(0)
            self.loop_end_change.emit(100.0)

        self._set_playback_state(VideoInitialState.STOPPED)
        self._destroy_video_driver()
        self.video_status.hide()
        self.show_overlay()

    def _set_playback_state(self, state: VideoInitialState):
        if self.video_params is None:
            return
        if self.video_params.playback_state == state:
            # VLC's status may already match the model (the initial PLAYING
            # state comes from session defaults before any VLC callback, and
            # snapshots can overwrite the model before the callback lands).
            # Still sync the overlay so the play/pause button isn't stuck.
            self.is_paused_change.emit(self.video_params.is_paused)
            if state is VideoInitialState.STOPPED:
                self.is_stopped_change.emit(True)
                self.show_overlay()
            return

        self.video_params.playback_state = state
        self.is_paused_change.emit(self.video_params.is_paused)
        self.is_stopped_change.emit(self.is_stopped)
        was_filled = self.autoFillBackground()
        self._sync_cell_background()
        if self.is_stopped or was_filled:
            self.update()
        self.show_overlay()

    def apply_snapshot(self, snapshot: Video):
        if snapshot.uri != self.video_params.uri:
            return

        self.title = snapshot.title or self._default_title
        self.color = snapshot.color.as_hex()

        if snapshot.is_stopped:
            self.video_params = snapshot.model_copy()
            self._destroy_video_driver()
            self._present_stopped()
            return

        if not self.is_video_initialized:
            self.video_params = snapshot.model_copy()
            self._start_load()
            return

        self.set_video_track(snapshot.video_track_id)
        self.restore_audio_selection(snapshot.audio_selection)

        self.set_audio_channel_mode(snapshot.audio_channel_mode)

        self.set_aspect(snapshot.aspect_mode)
        self.set_muted(snapshot.is_muted)
        self.set_pause(snapshot.is_paused)
        self.set_scale(snapshot.scale, is_silent=True)
        self.set_crop(snapshot.crop, is_silent=True)
        self.set_volume(snapshot.volume)

        self.seek(snapshot.current_position)
        self.set_loop_start_time(snapshot.loop_start)
        self.set_loop_end_time(snapshot.loop_end)
        self.set_rate(snapshot.rate, is_silent=True)

        self.switch_stream_quality(snapshot.stream_quality)
        self.set_auto_reload_timer(snapshot.auto_reload_timer_min)

        self.video_params = snapshot.model_copy()

    def set_video(self, video_params: Video):
        is_first_video = self.video_params is None
        is_options_changed = get_vlc_options(self.video_params) != get_vlc_options(
            video_params
        )

        self.video_params = video_params

        # Shut down current video
        if not is_first_video or is_options_changed:
            self.reset()

        if self.video_params.is_stopped and not self.is_video_initialized:
            self._present_stopped()
            return

        self._start_load()

    def _present_stopped(self):
        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        if self.title is None:
            if self.video_params.title is None:
                self.title = self._default_title
            else:
                self.title = self.video_params.title

        self.color = self.video_params.color.as_hex()
        self.is_audio_present_change.emit(False)
        self.is_paused_change.emit(True)
        self.is_stopped_change.emit(True)
        self.video_status.hide()
        self._sync_cell_background()
        self.update()
        self.show_overlay()

    def _start_load(self):
        self.overlay_hide_timer.stop()
        self.overlay.hide()
        self._sync_cell_background()
        self._ensure_video_driver()

        self._forget_audio_file_that_is_gone()

        self._attached_audio_file = self._audio_file_to_attach
        if self.video_params.is_http_url:
            self.url_resolver.resolve(self.video_params.uri)
        else:
            self.load_video.emit(
                MediaInput(
                    uri=str(self.video_params.uri),
                    is_live=False,
                    is_audio_only=False,
                    size=self.size_tuple,
                    video=self.video_params,
                    selected_audio_slave=self.selected_audio_slave_uri,
                )
            )

    def _load_and_play(self):
        if self._is_error or self._is_state_change_in_progress:
            return

        self._is_state_change_in_progress = True
        self._in_progress_timer.start()
        self._set_playback_state(VideoInitialState.PLAYING)
        self.set_status("processing")
        self._start_load()

    def set_video_url(self, video: ResolvedVideo):
        self._default_title = video.title

        if self.video_params.title is None:
            self.title = video.title

        self.streams = video.streams
        self.is_live = video.is_live

        self.load_stream_quality(self.video_params.stream_quality)

    @property
    def _language_variants(self) -> Streams:
        """Where this video's languages live, out of the two places they can.

        A site either dubs a video by handing back the whole ladder once
        per language, or by offering one ladder and several audio tracks
        to pair with it. Either way it is a set of streams that differ in
        nothing but the language of their sound.
        """

        if not self.streams:
            return Streams()

        if self.streams.is_multilingual:
            return self.streams

        audio_tracks = next(
            (
                stream.audio_tracks
                for _, stream in self.streams.items()
                if stream.audio_tracks
            ),
            None,
        )

        return audio_tracks or Streams()

    @property
    def audio_language_options(self) -> tuple[str, ...]:
        """The languages this video is dubbed into, as the site offered them."""

        return self._language_variants.languages

    @property
    def audio_language(self) -> str | None:
        """Which language this video plays, out of the several it is dubbed into.

        Nothing to choose between leaves this empty, and so does a video
        whose sound names no language at all.
        """

        variants = self._language_variants

        if not variants.is_multilingual:
            return None

        selection = self.video_params.audio_selection

        if isinstance(selection, AudioLanguage) and selection.tag in variants.languages:
            return selection.tag

        return variants.language_for(self.video_params.audio_languages)

    @property
    def preferred_audio_language(self) -> str | None:
        """Which language the preference alone would settle on.

        What is playing may be a pick made by hand instead, so this is the
        only way to say what going back to the preference would give.
        """

        return self._language_variants.language_for(self.video_params.audio_languages)

    @property
    def stream_ladder(self) -> Streams:
        """The rungs this video may switch between, all in the one language."""

        return self.streams.for_language(self.audio_language)

    @only_streamable
    def set_audio_language(self, language: str | None):
        """Play the same video in another one of the languages it is dubbed into.

        The ladder is a different one per language, so the rung has to be
        found again; asking for the one playing now finds the same size.
        """

        self.video_params.audio_selection = (
            AudioPreferred() if language is None else AudioLanguage(tag=language)
        )

        self._log.debug(
            f"Set audio language {language},"
            f" resolved to {self.audio_language},"
            f" playing {self._audio_language_playing}"
        )

        if self.audio_language == self._audio_language_playing:
            # the rung on screen is already the one asked for, so there is
            # nothing to reload -- but the sound may have been switched off
            # since it was loaded, and picking a language means wanting it
            self._apply_wanted_audio_track()
            return

        # the pane is about to be reloaded anyway, and on a ladder that no
        # longer holds the rung the timer was comparing against
        self._quality_adapt_timer.stop()

        self.reset()

        self.load_stream_quality(self.video_params.stream_quality)

    @only_streamable
    def switch_stream_quality(self, quality: str):
        if quality == self.video_params.stream_quality:
            return

        # picking a rung by hand calls off whatever the pane was about to do
        self._quality_adapt_timer.stop()

        self.reset()

        self.load_stream_quality(quality)

    @property
    def stream_quality_playing(self) -> str | None:
        """Which rung of the ladder is on screen, as opposed to what was asked."""

        return self._stream_quality_playing

    def load_stream_quality(self, wanted_quality: str):
        is_auto = wanted_quality == STREAM_QUALITY_AUTO

        ladder = self.stream_ladder

        self._audio_language_playing = self.audio_language

        if is_auto:
            quality, stream = ladder.fit_to_height(self._pane_height_px)
        else:
            quality, stream = ladder.by_quality(wanted_quality)

        # a standing instruction outlives the rung it picked, where a rung
        # chosen by name is kept as the name it was chosen by
        self.video_params.stream_quality = (
            wanted_quality if wanted_quality in STANDING_QUALITIES else quality
        )
        self._stream_quality_playing = quality

        # switching quality resets the block, which leaves it without a driver
        self._ensure_video_driver()

        if stream.protocol == "direct":
            url = stream.url
        else:
            stream = self._with_audio_language(stream)
            url = self._ctx.commands.add_stream(self._with_origin(stream, quality))

        self.load_video.emit(
            MediaInput(
                uri=url,
                is_live=self.is_live,
                is_audio_only=stream.is_audio_only,
                video_codec=stream.video_codec,
                is_adaptive=stream.is_adaptive,
                size=self.size_tuple,
                video=self.video_params,
            )
        )

    @property
    def _network_retry_limit(self) -> int:
        """How many times this video may be reloaded, -1 for no limit."""

        if self.video_params is None:
            return 0

        mode = self.video_params.network_retry_mode

        if mode == NetworkRetryMode.INFINITE:
            return -1

        if mode == NetworkRetryMode.TIMES:
            return max(self.video_params.network_retry_times, 0)

        return 0

    @property
    def _quality_adapt_delay_ms(self) -> int:
        """How long a pane has to keep its new size before the stream follows.

        Dragging a window edge resizes every pane dozens of times on the way,
        and every switch costs a reload, so the size has to settle down first.
        """

        return max(self.video_params.quality_adapt_delay_sec, 1) * 1000

    @property
    def _pane_height_px(self) -> int:
        """How tall this pane is in the pixels a screen actually has.

        The widget measures itself in the logical pixels Qt scales, so on a
        200% display a pane reports half the detail it can really show.
        """

        return int(self.height() * self.devicePixelRatioF())

    def _schedule_quality_adapt(self):
        if self.video_params is None or not self.streams:
            return

        if self.video_params.stream_quality != STREAM_QUALITY_AUTO:
            return

        self._quality_adapt_timer.start(self._quality_adapt_delay_ms)

    def _adapt_stream_quality(self):
        """Fit the stream to the size the pane has settled on."""

        if self._is_closing or self.video_params is None or not self.streams:
            return

        if self.video_params.stream_quality != STREAM_QUALITY_AUTO:
            return

        if self._is_error:
            # a video that is already failing has the retry timer looking
            # after it, and reloading underneath that would only confuse it
            return

        if self._is_state_change_in_progress:
            self._quality_adapt_timer.start(self._quality_adapt_delay_ms)
            return

        quality, _ = self.stream_ladder.fit_to_height(self._pane_height_px)

        if quality == self._stream_quality_playing:
            return

        self._log.debug(
            f"Pane now fits {quality}, switching from {self._stream_quality_playing}"
        )

        self.reset()

        self.load_stream_quality(STREAM_QUALITY_AUTO)

    def _with_audio_language(self, stream):
        """Hand the proxy only the audio tracks in the language being played.

        VLC is served a playlist with one audio rendition in it, so which
        of them it is has to be settled here; the proxy is left to pick
        the best of whatever it is given.
        """

        if not stream.audio_tracks:
            return stream

        language = stream.audio_tracks.language_for(self.video_params.audio_languages)

        if language is None:
            return stream

        return dataclasses.replace(
            stream, audio_tracks=stream.audio_tracks.for_language(language)
        )

    def _with_origin(self, stream, quality: str):
        """Tell the proxy where this stream came from.

        Services sign the URLs they hand out and stop honouring them after a
        while, so the proxy has to be able to ask for them again rather than
        serve a video that dies partway through.
        """

        origin = StreamOrigin(url=str(self.video_params.uri), quality=quality)

        return dataclasses.replace(stream, origin=origin)

    def load_video_finish(self):
        # the video is playing, so whatever went wrong before is behind us
        self._network_retries = 0

        # a fresh player has no pass behind it to compare times against
        self._last_time = None

        # final verdict belongs to VLC
        self.is_live = self.video_driver.is_live

        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        if self.title is None:
            if self.video_params.title is None:
                self.title = self._default_title
            else:
                self.title = self.video_params.title

        self.color = self.video_params.color.as_hex()

        self.set_audio_channel_mode(self.video_params.audio_channel_mode)

        self.set_volume(self.video_params.volume)
        self.set_muted(self.video_params.is_muted)

        self.set_loop_start_time(self.video_params.loop_start)
        self.set_loop_end_time(self.video_params.loop_end)
        self.set_rate(self.video_params.rate, is_silent=True)

        self.set_auto_reload_timer(self.video_params.auto_reload_timer_min)

        self.video_params.video_track_id = self.video_driver.cur_video_track_id

        self.is_audio_present_change.emit(bool(self.audio_tracks))

        self._adopt_audio_if_silent()

        self.video_status.hide()
        self.video_driver.show()
        self.is_stopped_change.emit(self.is_stopped)
        self.time_change.emit(self.time, self.video_driver.length)
        self.show_overlay()

        self.video_driver.adjust_view()

    @only_with_video_tacks
    def set_aspect(self, aspect: VideoAspect):
        self.video_params.aspect_mode = aspect

        self.video_driver.set_aspect_ratio(self.video_params.aspect_mode)

    @only_with_video_tacks
    def set_transform(self, transform: VideoTransform):
        self.video_params.transform = transform

        self.reload()

    @only_seekable
    def toggle_loop_random(self):
        self.video_params.is_start_random = not self.video_params.is_start_random

    @only_seekable
    def set_loop_start(self):
        self.set_loop_start_time(self.time)

    @only_seekable
    def set_loop_start_time(self, new_time):
        if None not in {self.video_params.loop_end, new_time}:
            if new_time >= self.video_params.loop_end:
                return

        self.video_params.loop_start = new_time

        if new_time is None:
            self.loop_start_change.emit(0)
        else:
            self.loop_start_change.emit(new_time / self.video_driver.length)

    @only_seekable
    def set_loop_end(self):
        self.set_loop_end_time(self.time)

    @only_seekable
    def set_loop_end_time(self, new_time):
        if None not in {self.video_params.loop_start, new_time}:
            if new_time <= self.video_params.loop_start:
                return

        self.video_params.loop_end = new_time

        if new_time is None:
            self.loop_end_change.emit(100.0)
        else:
            self.loop_end_change.emit(new_time / self.video_driver.length)

    @only_seekable
    def reset_loop(self):
        self.set_loop_start_time(None)
        self.set_loop_end_time(None)

    @only_seekable
    def set_end_action(self, end_action: VideoEndAction):
        self.video_params.end_action = end_action

    @only_initialized
    @only_seekable
    def seek_shift_percent(self, shift_percent):
        seek_ms = int(shift_percent / 100 * self.video_driver.length)

        self.seek_shift_ms(seek_ms)

    @only_initialized
    @only_seekable
    def seek_shift_ms(self, seek_ms):
        seek_stretch = self.loop_end - self.loop_start

        if seek_ms > 0 and self.time + seek_ms > self.loop_end:
            # Seeking past the end is the end arriving early, and a video that
            # is meant to move on when it gets there should move on here too.
            # Only where the end just starts the video over does the seek
            # carry on into the next pass, which is what keeps wheeling
            # through a looping video continuous.
            if not self.is_end_a_loop:
                self.loop_end_action()
                return

            rest = self.loop_end - self.time
            seek_set = seek_ms - rest
            seek_set = seek_set - (seek_set // seek_stretch) * seek_stretch

            new_time = self.loop_start + seek_set

        elif seek_ms < 0 and self.time + seek_ms < self.loop_start:
            seek_ms *= -1

            rest = self.time - self.loop_start
            seek_set = seek_ms - rest
            seek_set = seek_set - (seek_set // seek_stretch) * seek_stretch

            new_time = self.loop_end - seek_set

        else:
            new_time = self.time + seek_ms

        self.seek(new_time)

    @only_initialized
    @only_seekable
    def seek_random(self):
        random_ms = random.randint(self.loop_start, self.loop_end)

        self.seek(random_ms)

    @only_initialized
    @only_seekable
    def seek_percent(self, percent):
        seek_ms = int(percent * self.video_driver.length)

        self.seek(seek_ms)

    @only_initialized
    @only_seekable
    def seek(self, seek_ms):
        if seek_ms < self.loop_start or seek_ms > self.loop_end:
            seek_ms = self.loop_start

        # Marked before the seek is made, not after: the single process
        # drivers call libVLC on this very thread, and it reports the new time
        # from inside that call. Marked afterwards, a seek that moves the time
        # backwards -- wheeling past the end lands back at the start -- reads
        # as a finished pass, and the end action then stops the player from
        # inside libVLC, which deadlocks against the seek it is still making.
        self._last_time = seek_ms
        self._seek_settle_timer.start()

        self.time = seek_ms
        self.video_driver.set_time(seek_ms)

    @only_with_video_tacks
    @only_seekable
    @only_initialized
    def next_frame(self):
        self.step_frame(1)

    @only_with_video_tacks
    @only_seekable
    @only_initialized
    def previous_frame(self):
        self.step_frame(-1)

    @only_with_video_tacks
    @only_seekable
    @only_initialized
    def step_frame(self, frames):
        if not self.video_params.is_paused:
            self.set_pause(True)
            return

        ms_per_frame = self.video_driver.get_ms_per_frame()

        # Counted from the frame the video is on rather than added to the
        # time it reports, so that steps rounded to whole milliseconds cannot
        # pile up their leftovers until a press lands back on the frame it
        # started from. The seek aims at the middle of the frame it wants,
        # since a whole millisecond lands on either side of a frame's edge.
        frame_no = int(self.time // ms_per_frame)
        new_time = round((frame_no + frames + 0.5) * ms_per_frame)

        self.seek_shift_ms(new_time - self.time)

    @only_with_video_tacks
    @only_initialized
    def scale_increase(self):
        self.video_params.scale += 0.1
        self.video_params.scale = min(round(self.video_params.scale, 1), MAX_SCALE)

        self.set_scale(self.video_params.scale)

    @only_with_video_tacks
    @only_initialized
    def scale_decrease(self):
        self.video_params.scale -= 0.1
        self.video_params.scale = max(round(self.video_params.scale, 1), MIN_SCALE)

        self.set_scale(self.video_params.scale)

    @only_with_video_tacks
    @only_initialized
    def scale_reset(self):
        self.set_scale(1.0)

    @only_with_video_tacks
    @only_initialized
    def set_scale(self, scale, is_silent=False):
        self.video_params.scale = scale

        self.video_driver.set_scale(scale)

        if not is_silent:
            self.info_change.emit(f"Zoom: {scale}")

    @only_with_video_tacks
    @only_initialized
    def crop(self, left, top, right, bottom, is_silent=False):
        crop = VideoCrop(
            self.video_params.crop.Left + left,
            self.video_params.crop.Top + top,
            self.video_params.crop.Right + right,
            self.video_params.crop.Bottom + bottom,
        )

        self.set_crop(crop, is_silent)

    @only_with_video_tacks
    @only_initialized
    def crop_reset(self, is_silent=False):
        self.set_crop(VideoCrop(0, 0, 0, 0), is_silent)

    @only_with_video_tacks
    @only_initialized
    def set_crop(self, crop: VideoCrop, is_silent=False):
        crop = VideoCrop(
            max(crop.Left, 0),
            max(crop.Top, 0),
            max(crop.Right, 0),
            max(crop.Bottom, 0),
        )

        if self.video_params.crop != crop:
            self.video_params.crop = crop
            self.video_driver.set_crop(self.video_params.crop)

        if not is_silent:
            self.info_change.emit(
                "Crop: L{} T{} R{} B{}".format(*self.video_params.crop)
            )

    @only_initialized
    @only_seekable
    def rate_increase(self):
        self.video_params.rate += 0.1
        self.video_params.rate = min(round(self.video_params.rate, 1), MAX_RATE)

        self.set_rate(self.video_params.rate)

    @only_initialized
    @only_seekable
    def rate_decrease(self):
        self.video_params.rate -= 0.1
        self.video_params.rate = max(round(self.video_params.rate, 1), MIN_RATE)

        self.set_rate(self.video_params.rate)

    @only_initialized
    @only_seekable
    def rate_reset(self):
        self.set_rate(1.0)

    @only_initialized
    @only_seekable
    def set_rate(self, rate, is_silent=False):
        self.video_params.rate = rate

        self.video_driver.set_playback_rate(rate)

        if not is_silent:
            self.info_change.emit(f"Speed: {rate}")

    def set_pause(self, paused):
        if self._is_state_change_in_progress:
            return

        if not self.is_video_initialized:
            if not paused:
                self._load_and_play()
            return

        if self.video_params.is_paused == paused:
            return

        self._is_state_change_in_progress = True
        self._in_progress_timer.start()

        self.video_driver.set_pause(paused)

    def mute_unmute(self):
        self.set_muted(not self.video_params.is_muted)

    @only_initialized
    def set_muted(self, muted):
        self.video_params.is_muted = muted

        self.video_driver.audio_set_mute(self.video_params.is_muted)

        self.is_muted_change.emit(self.video_params.is_muted)

    @only_initialized
    def set_volume(self, percent):
        self.video_params.volume = round(percent, 2)

        self.video_driver.audio_set_volume(self.video_params.volume)

        self.volume_change.emit(percent)

    @only_initialized
    def volume_increase(self):
        self.set_muted(False)

        self.video_params.volume += 0.05
        self.video_params.volume = min(round(self.video_params.volume, 2), 1.0)

        self.set_volume(self.video_params.volume)

    @only_initialized
    def volume_decrease(self):
        self.set_muted(False)

        self.video_params.volume -= 0.05
        self.video_params.volume = max(round(self.video_params.volume, 2), 0)

        self.set_volume(self.video_params.volume)

    def play_pause(self):
        self.set_pause(not self.video_params.is_paused)

    @only_local_file
    def previous_video(self):
        self.switch_video(previous_video_file(self.video_params.uri))

    @only_local_file
    def next_video(self):
        self.switch_video(next_video_file(self.video_params.uri))

    @only_local_file
    def shuffle_video(self):
        self.switch_video(next_video_file(self.video_params.uri, is_shuffle=True))

    @only_local_file
    def switch_video(self, new_video: Path):
        # If single file in the dir and was removed, highly unlikely but still
        if new_video is None:
            self.error()
            return

        if new_video == self.video_params.uri:
            if self.is_video_initialized:
                self.seek(self.loop_start)
                return
            self._load_and_play()
            return

        self.reset_loop()
        self.video_params.current_position = 0
        self.video_params.uri = new_video
        self.video_params.playback_state = VideoInitialState.PLAYING
        self._title = None
        self._default_title = None

        self.set_video(self.video_params)

    def rename(self):
        new_data = QVideoRenameDialog.get_edits(
            parent=self.parent(),
            title=translate("Dialog - Rename video", "Rename video", "Header"),
            orig_title=self._default_title,
            cur_title=self.title,
            cur_color=self.video_params.color.as_rgb_tuple(),
        )

        if new_data is None:
            return

        new_name, new_color = new_data

        self.video_params.color = Color(new_color)

        if new_name == self._default_title:
            self.video_params.title = None
        else:
            self.video_params.title = new_name

        self.title = new_name
        self.color = self.video_params.color.as_hex()
