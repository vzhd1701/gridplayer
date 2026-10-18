import logging
import random
import secrets
from functools import partial
from operator import attrgetter
from pathlib import Path

from pydantic_extra_types.color import Color
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QStackedLayout, QWidget

from gridplayer.dialogs.input_dialog import (
    QCustomSpinboxTimeInput,
)
from gridplayer.dialogs.rename_dialog import QVideoRenameDialog
from gridplayer.exceptions import PlayerException
from gridplayer.models.audio_selection import (
    AudioDisabled,
)
from gridplayer.models.bookmark import Bookmark
from gridplayer.models.media_list import (
    ListItem,
    MediaList,
)
from gridplayer.models.seek_mark import SeekMark, SeekMarkKind
from gridplayer.models.stream import (
    Streams,
)
from gridplayer.models.video import (
    Video,
    VideoBlockMime,
)
from gridplayer.params import env
from gridplayer.params.static import (
    CHROME_MIN_SIZE,
    MAX_RATE,
    MIN_RATE,
    OVERLAY_ACTIVITY_EVENT,
    PLAYER_ID_LENGTH,
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoEndAction,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.settings import Settings
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.utils.libvlc_options_parser import (
    get_vlc_options,
    is_deinterlace_reload_needed,
    is_reopen_needed,
)
from gridplayer.utils.qt import MILLISECONDS, qt_connect, translate
from gridplayer.utils.sponsorblock import (
    segment_mark,
)
from gridplayer.utils.step_sizes import seek_step_ms
from gridplayer.utils.url_resolve.static import ResolvedVideo
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolver
from gridplayer.vlc_player.static import (
    DISABLED_TRACK,
    SEEK_ARRIVAL_MS,
    MediaInput,
    SeekLanding,
    arriving_time,
    is_loop_wrapped,
    seek_landing,
)
from gridplayer.widgets.cell_chrome import (
    chrome_color_on_cell,
    paint_idle_disc,
    paint_solid_outline,
)
from gridplayer.widgets.stacked_layout_floating import QStackedLayoutFloating
from gridplayer.widgets.video_block_audio import AudioControl
from gridplayer.widgets.video_block_bookmarker import Bookmarker
from gridplayer.widgets.video_block_chapters import ChapterControl
from gridplayer.widgets.video_block_guards import (
    only_initialized,
    only_seekable,
    only_with_video_tacks,
)
from gridplayer.widgets.video_block_loop import LoopControl
from gridplayer.widgets.video_block_navigation import NavigationControl
from gridplayer.widgets.video_block_recovery import RecoveryControl
from gridplayer.widgets.video_block_screenshot import ScreenshotControl
from gridplayer.widgets.video_block_sponsorblock import SponsorBlockControl
from gridplayer.widgets.video_block_status import StatusControl
from gridplayer.widgets.video_block_stream import StreamControl
from gridplayer.widgets.video_block_subtitles import SubtitleControl
from gridplayer.widgets.video_block_view import ViewControl
from gridplayer.widgets.video_frame_vlc_base import VideoFrameVLC
from gridplayer.widgets.video_overlay import (
    OverlayBlock,
    OverlayBlockChild,
    OverlayBlockFloating,
    OverlayFakeInvisible,
    is_layered_child_supported,
)
from gridplayer.widgets.video_status import (
    LoadStage,
    VideoStatus,
)

IN_PROGRESS_THRESHOLD_MS = 500

# A seek sends the time backwards the same way the end of a pass does, and the
# player takes a few time updates to settle on the new position. Loop detection
# stays off for this long after one, so an update sent before the seek landed
# is not mistaken for the video wrapping around.
SEEK_SETTLE_MS = 500

# VLC's adaptive demuxer turns a seek down while it is still restarting its
# streams for the one before -- "not seekable" in its own log, and nothing
# else to say so -- and plays on from where that one took it. Made again once
# the time shows up where the seek could never have landed, it takes.
SEEK_RETRIES = 2

# the end actions that take the video out of its cell: closed, or another
# file put in its place
LEAVING_END_ACTIONS = frozenset(
    {
        VideoEndAction.NEXT_FILE,
        VideoEndAction.PREVIOUS_FILE,
        VideoEndAction.SHUFFLE_FILE,
        VideoEndAction.CLOSE,
    }
)


class VideoBlock(QWidget):
    load_video = pyqtSignal(MediaInput)

    about_to_close = pyqtSignal(str)

    sync_percent_single = pyqtSignal(float)
    sync_time_single = pyqtSignal(MILLISECONDS)
    sync_percent = pyqtSignal(float)
    sync_time = pyqtSignal(MILLISECONDS)
    # the others paused for a step to the next or the previous frame
    sync_paused = pyqtSignal(bool)
    # what the viewer had this one do, for the others to follow where that
    # is synced: played or paused, zoomed or moved (a SyncedView), the speed
    sync_pause = pyqtSignal(bool)
    sync_view = pyqtSignal(object)
    sync_rate = pyqtSignal(float)
    # the view, for the others to follow this once
    sync_view_single = pyqtSignal(object)

    time_change = pyqtSignal(MILLISECONDS, MILLISECONDS)
    volume_change = pyqtSignal(float)
    label_change = pyqtSignal(str)
    # the cell is closing, for a window open on it to close with it
    closing = pyqtSignal()
    # which item of its list it plays, "3/12", empty for a cell with no list
    list_place_change = pyqtSignal(str)
    color_change = pyqtSignal(str)
    loop_start_change = pyqtSignal(float)
    loop_end_change = pyqtSignal(float)
    seek_marks_change = pyqtSignal(tuple)
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

        # how long the site a URL resolved on says the video is, to know its
        # chapters and SponsorBlock's segments by; and the ID SponsorBlock
        # knows a YouTube video by
        self._site_length_ms = 0
        self._youtube_id: str | None = None

        # what the seek bar was last told to mark
        self._seek_marks: tuple[SeekMark, ...] = ()

        # the picture switched off while the player is in the tray, to be
        # switched back on as it comes back; see set_video_decoding_stopped
        self._is_video_stopped_in_tray = False

        # shared with other cells, the bookmarks may change in any of them
        self._ctx.bookmarks.changed.connect(self.update_seek_marks)

        # Components
        self.overlay_hide_timer = QTimer(self)
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self.hide_overlay)

        self._in_progress_timer = QTimer(self)
        self._in_progress_timer.setSingleShot(True)
        self._in_progress_timer.setInterval(IN_PROGRESS_THRESHOLD_MS)
        self._in_progress_timer.timeout.connect(self.is_in_progress_change)

        self._seek_settle_timer = QTimer(self)
        self._seek_settle_timer.setSingleShot(True)
        self._seek_settle_timer.setInterval(SEEK_SETTLE_MS)

        # where the last seek was aimed, until the video is seen to get there;
        # the first time reported short of it; and how many more times it may
        # be made again. See _follow_seek
        self._seek_target: int | None = None
        self._seek_landed_at: int | None = None
        self._seek_retries = 0

        # the seek before the last, when the last was made before it landed
        self._seek_behind: int | None = None

        self.video_driver: VideoFrameVLC | None = None

        # before the resolver, which is wired to them as it is made
        self.status = StatusControl(self)
        self.bookmarker = Bookmarker(self)
        self.view = ViewControl(self)
        self.chapters = ChapterControl(self)
        self.sponsorblock = SponsorBlockControl(self)
        self.subtitles = SubtitleControl(self)
        self.audio = AudioControl(self)
        self.loop = LoopControl(self)
        self.screenshot = ScreenshotControl(self)
        self.recovery = RecoveryControl(self)
        self.stream = StreamControl(self)
        self.navigation = NavigationControl(self)

        self.url_resolver = self.init_url_resolver()

        # the item playing has played since it was put in the cell: a
        # reload may yet bring it back, whatever it failed with
        self._has_item_played = False

        self._ctx.lists.waiting_progress.connect(self.status.on_waiting_progress)

        self.overlay = self.init_overlay()

        self.ui_setup()

        self.video_status.show()
        self.overlay.hide()

    def _driver_has_native_surface(self) -> bool:
        cls = self.video_driver_cls
        if isinstance(cls, partial):
            cls = cls.func
        return bool(getattr(cls, "is_native_surface", False))

    def init_video_driver(self) -> VideoFrameVLC:
        vlc_options = get_vlc_options(self.video_params)
        self._log.debug(f"vlc_options: {vlc_options}")

        video_driver = self.video_driver_cls(vlc_options=vlc_options, parent=self)

        qt_connect(
            (video_driver.video_ready, self.load_video_finish),
            (video_driver.picture_shown, self._picture_shown),
            (video_driver.view_followed, self.view.remember_followed),
            (video_driver.tracks_changed, self.audio.tracks_changed),
            (video_driver.chapters_changed, self.chapters.update),
            (video_driver.time_changed, self.time_changed),
            (video_driver.playback_status_changed, self.playback_status_changed),
            (video_driver.error, self.video_driver_error),
            (video_driver.crash, self.crash),
            (video_driver.update_status, self.status.on_driver_status),
            # Left connected when the driver is let go: a frame asked for
            # before a reload is still the one that was wanted, and a PNG
            # nobody receives would be left behind in the temp folder.
            (video_driver.screenshot_taken, self.screenshot.taken),
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

        # the frame's native window is made after the overlay's, and a child
        # overlay only shows over the video stacked above it
        if isinstance(self.overlay, OverlayBlockChild):
            self.overlay.raise_()

        self._hide_video_driver()
        return self.video_driver

    def _hide_video_driver(self):
        if self.video_driver is None:
            return

        # Don't hide VLC HW frame widget, otherwise first frame comes out glitchy and takes time to normalize
        # Happens only on Windows
        # Possibly related issue - short ~100-300ms "freeze-frame" lag before video starts actually playing
        # especially noticeable on streaming vids, also happens on Linux
        if env.IS_WINDOWS and self._driver_has_native_surface():
            return

        self.video_driver.hide()

    def _destroy_video_driver(self):
        self._is_state_change_in_progress = False
        self._in_progress_timer.stop()

        # what SponsorBlock found is only marked again once something is
        # playing
        self.sponsorblock.forget_shown()

        # a seek made on it has nothing left to land on
        self._seek_target = None
        self._seek_behind = None

        self._release_video_driver()

        # whatever opens next brings chapters of its own, or none; and the
        # bookmarks are only marked once there is a length to mark them on
        self.chapters.clear()

    def _release_video_driver(self):
        if self.video_driver is None:
            return

        self.status.is_kept_for_picture = False

        self.load_video.disconnect()
        self.video_driver.video_ready.disconnect()
        self.video_driver.picture_shown.disconnect()
        self.video_driver.view_followed.disconnect()
        self.video_driver.time_changed.disconnect()
        self.video_driver.playback_status_changed.disconnect()
        self.video_driver.error.disconnect()
        self.video_driver.crash.disconnect()
        self.video_driver.update_status.disconnect()

        old_driver = self.video_driver
        self.video_driver = None
        self.layout_main.removeWidget(old_driver)
        old_driver.hide()

        # painted without it before its player is waited on: a hardware
        # video's window, gone, shows what was painted under it before its
        # picture came, the loading status, until the cell is painted again
        if self.isVisible():
            self.repaint()

        old_driver.cleanup()
        old_driver.deleteLater()

    def init_url_resolver(self):
        url_resolver = VideoURLResolver(parent=self)
        url_resolver.error.connect(self.network_error)
        url_resolver.url_resolved.connect(self.set_video_url)
        url_resolver.list_resolved.connect(self.navigation.link_was_a_list)
        url_resolver.resolving.connect(self.status.on_resolving)
        url_resolver.reading.connect(self.status.on_link_list_reading)
        url_resolver.failed.connect(self.status.resolve_failed)

        return url_resolver

    def reset_url_resolver(self):
        self.url_resolver.error.disconnect()
        self.url_resolver.url_resolved.disconnect()
        self.url_resolver.list_resolved.disconnect()

        self.url_resolver.cleanup()

        self.url_resolver = self.init_url_resolver()

    def reset(self, is_link_kept=False):
        """Ready the cell for a load begun afresh, its old player let go.

        is_link_kept: the link already resolved, its stream opened again.
        """

        self._is_error = False

        # shown while the old player is let go: where the load to come
        # starts, not how far the one before it got; a list read for it
        # is where it started already
        if self.status.load_stage is not LoadStage.LIST:
            if is_link_kept:
                self.status.show_opening()
            else:
                self.status.show_load_start()

        self.status.show("processing")

        self._destroy_video_driver()
        self.reset_url_resolver()

    def init_overlay(self):
        if not self._driver_has_native_surface():
            overlay = OverlayBlock(self)
        elif is_layered_child_supported():
            overlay = OverlayBlockChild(self)
        elif Settings().get("internal/fake_overlay_invisibility"):
            overlay = OverlayFakeInvisible(self)
        else:
            overlay = OverlayBlockFloating(self)

        if isinstance(overlay, OverlayBlockFloating):
            self.installEventFilter(overlay)

        qt_connect(
            (overlay.set_vid_pos, partial(self.manual_seek, "seek_percent")),
            (overlay.set_volume, self.audio.set_volume),
            (overlay.exit_clicked, self.close),
            (overlay.play_pause_clicked, self.play_pause),
            (overlay.mute_unmute_clicked, self.audio.mute_unmute),
            (overlay.bookmark_clicked, self.bookmarker.jump_to_marker),
            (overlay.bookmark_menu_requested, self.bookmarker.show_marker_menu),
            (overlay.list_place_clicked, self.navigation.show_list_window),
            (overlay.stop_clicked, self.stop_playback),
            (overlay.retry_clicked, self.reload),
            (overlay.next_clicked, self.recovery.skip_now),
            (overlay.details_clicked, self.status.show_error_details),
            (self.time_change, overlay.set_position),
            (self.volume_change, overlay.set_volume_position),
            (self.label_change, overlay.set_label),
            (self.list_place_change, overlay.set_list_place),
            (self.color_change, overlay.set_color),
            (self.loop_start_change, overlay.set_loop_start),
            (self.loop_end_change, overlay.set_loop_end),
            (self.seek_marks_change, overlay.set_seek_marks),
            (self.is_paused_change, overlay.set_is_paused),
            # what it shows is the cell's to say, stopped or not
            (self.is_stopped_change, self.status.sync_overlay_mode),
            (self.is_in_progress_change, overlay.set_is_in_progress),
            (self.is_muted_change, overlay.set_is_muted),
            (self.info_change, overlay.set_info_label),
            (self.is_active_change, overlay.set_is_active),
            (self.is_audio_present_change, overlay.set_volume_button_visible),
        )

        return overlay

    def ui_setup(self):
        self.setMouseTracking(True)

        if isinstance(self.overlay, OverlayBlockFloating):
            self.layout_main = QStackedLayoutFloating(self)
        else:
            self.layout_main = QStackedLayout(self)

        self.layout_main.setSpacing(0)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setStackingMode(QStackedLayout.StackAll)

        self.video_status = VideoStatus(parent=self, is_framed=True)
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
        self.stream.stop_adapting()
        self.recovery.stop()

        self._log.debug(f"{self.id}: cleaning up resolver")
        self.url_resolver.cleanup()

        self.sponsorblock.stop_listening()

        self.navigation.close()

        self._log.debug(f"{self.id}: cleaning up driver ")
        self._destroy_video_driver()

        self._log.debug(f"{self.id}: cleaning up done")

    def video_driver_error(self, error: str, vlc_lines: tuple[str, ...] = ()):
        # marked for translation where the player process says it, which
        # has no translator of its own
        message = translate("Video Error", error)

        self.status.last_error = self.status.player_error(message, vlc_lines)
        self.status.set_text(message)

        if not self.video_params.is_local_file:
            return self.network_error()

        return self.error()

    def error(self):
        self._is_error = True
        self._is_state_change_in_progress = False
        self.status.show("error")
        self.cleanup()
        self.recovery.schedule_skip()
        self.status.show_error_card()

    def network_error(self):
        if not self.recovery.is_reload_futile and self.recovery.schedule_retry():
            return

        tries = self.recovery.retries
        self.recovery.drop_retries()

        self._is_error = True
        self._is_state_change_in_progress = False
        self.status.show("network-error")
        self.cleanup()
        self.recovery.schedule_skip()
        self.status.show_error_card(tries)

    def reload(self):
        self.recovery.stop_retry_countdown()
        self.stream.stop_adapting()

        self.is_live = False
        self._is_error = False
        self.streams = Streams()
        self._title = None
        self._default_title = None

        self.reset()

        video_params = self.video_params
        self.video_params = None

        self.set_video(video_params)

    def show_reloading(self):
        """Say it loads again, over the video, as a cell opening it afresh
        does at first, its player about to be let go for all of them to be
        opened again (VideoBlocksManager.reload_videos)."""

        if self.video_driver is None:
            return

        self._is_error = False
        self.status.show_load_start()
        self.status.show("processing")

    def release_player(self):
        """Let its player go, waiting until it has."""

        self._destroy_video_driver()

    def close_silently(self):
        self.close(notify=False)

    def close(self, notify=True):
        if self._is_closing:
            return

        self._is_closing = True

        self.bookmarker.close_manager()

        self.closing.emit()

        # what the cell looked like, for the bookmarks it leaves behind, if
        # each cell keeps its own, to be told apart by; and the list it
        # waited for no longer read for it
        if self.video_params is not None:
            self._ctx.lists.stop_waiting(self.video_params.id)
            self._ctx.bookmarks.remember_cell(
                self.video_params.id,
                self.title or self.video_params.uri_name,
                self.video_params.color.as_hex(),
            )

        self._log.debug(f"Closing video block {self.id}")

        if notify:
            self.about_to_close.emit(self.id)

        # off screen, and the window painted without it, before its player is
        # waited on (closeEvent): a hardware video's cell, once its player
        # lets go, shows what was painted there before its picture came, the
        # loading status, until the window is painted again
        if self.isVisible():
            self.hide()

            if self.parentWidget() is not None:
                self.parentWidget().repaint()

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
        # The overlay of a hardware video is a window of its own, floating
        # or a child one, so hiding this cell does not hide it as far as Qt
        # knows. Always unmap it here — hide_overlay() is chrome-timeout
        # policy and is a no-op when overlays stay visible.
        self.overlay_hide_timer.stop()
        self.overlay.hide()

    def paintEvent(self, event):
        super().paintEvent(event)
        self._paint_stopped_chrome()

    def _paint_stopped_chrome(self):
        if not self.is_stopped:
            return
        paint_solid_outline(self, is_active=self.is_active_shown)
        if self._drop_indicator == DropIndicator.NONE:
            paint_idle_disc(self)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_overlay_size_policy()
        self.stream.schedule_adapt()

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
        # one that went nowhere leaves the others nothing to follow
        if attrgetter(command)(self)(*args) is False:
            return

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

    def is_under_cursor(self):
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, is_active):
        self._is_active = is_active

        self._update_chrome()

        if is_active and not self._ctx.is_show_overlay_border:
            return

        self.is_active_change.emit(is_active)

    def refresh_overlay_border(self):
        self.is_active_change.emit(self.is_active_shown)
        self._update_chrome()

    @property
    def is_active_shown(self) -> bool:
        """Whether the cell is marked as the active one: by the overlay's
        border over a video, by the frame over a cell with no picture."""

        return self._is_active and self._ctx.is_show_overlay_border

    def _update_chrome(self):
        """The frame painted again, of a cell with no picture."""

        if self.is_stopped:
            self.update()

        self.video_status.set_is_active(self.is_active_shown)

    @property
    def drag_data(self):
        """What a cell dragged says of itself; the list it plays from goes
        apart from it, see files.cell_mime_data."""

        return VideoBlockMime(
            id=self.id,
            video=self.video_params,
            bookmarks=list(self.bookmarks),
        )

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
    def media_list(self) -> MediaList | None:
        """The list the cell plays from, None where it has none."""

        if self.video_params is None:
            return None

        return self._ctx.lists.get(self.video_params.list_id)

    @property
    def list_item(self) -> ListItem | None:
        """The item of its list the video playing is, None where it is not
        on it, or there is no list."""

        place = self.navigation.place()

        if place is None or not place.is_found:
            return None

        return self.media_list.items[place.index]

    @property
    def is_error(self) -> bool:
        """Failed, and showing why, rather than playing or loading."""

        return self._is_error

    @property
    def is_closing(self) -> bool:
        return self._is_closing

    @property
    def _item_headers(self) -> dict[str, str]:
        """What a channel list says to fetch the item playing with."""

        item = self.list_item
        headers = self.video_params.http_headers if item is None else item.http_headers

        return {} if headers is None else headers.as_dict()

    @property
    def is_navigable(self) -> bool:
        return self.media_list is not None or self.is_local_file

    @property
    def _custom_title(self) -> str | None:
        """What the viewer named the video, if anything: the cell's own name,
        or for a cell that plays a list, the item's on the list."""

        if self.media_list is not None:
            item = self.list_item
            return None if item is None else item.title

        return self.video_params.title

    @property
    def youtube_id(self) -> str | None:
        """The YouTube video this URL turned out to be, once resolved."""

        return self._youtube_id

    @property
    def site_length_ms(self) -> int:
        """How long the site this URL resolved on says the video is, 0 for
        one it did not say of, or a file."""

        return self._site_length_ms

    @property
    def video_tracks(self):
        if self.video_driver is None or not self.is_video_initialized:
            return {}
        return self.video_driver.video_tracks

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

    def set_video_decoding_stopped(self, is_stopped: bool) -> None:
        """Switch the picture off while the player is in the tray, and back on.

        The sound plays on, the picture is not decoded. Only the player is
        told: the video's own track stays as picked, and is what is saved.
        A paused video decodes nothing anyway and is left alone, as is one
        with no sound to play instead.
        """

        if not self.is_video_initialized or not self.video_tracks:
            self._is_video_stopped_in_tray = False
            return

        if is_stopped:
            if self._is_video_stopped_in_tray or self.video_params.is_paused:
                return

            if not self.audio.tracks or isinstance(
                self.video_params.audio_selection, AudioDisabled
            ):
                return

            if self.video_params.video_track_id == DISABLED_TRACK:
                return

            self._is_video_stopped_in_tray = True
            self.video_driver.set_video_track(DISABLED_TRACK)
            return

        if not self._is_video_stopped_in_tray:
            return

        self._is_video_stopped_in_tray = False

        track_id = self.video_params.video_track_id
        if track_id is None:
            track_id = min(self.video_tracks)

        self.video_driver.set_video_track(track_id)

        # Switched back on, the picture is decoded from wherever the stream
        # is, between key frames, and D3D11 hardware decoding of 10-bit HEVC
        # mostly never recovers from that ("hardware acceleration picture
        # allocation failed", black from then on). The same spot asked for
        # again starts it at a key frame. Paused while away, a video gets
        # the picture it has no other way to show that way too.
        if not self.is_live and self.time:
            self.video_driver.set_time(self.time)

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
        self._sync_drop_chrome(indicator)
        self.overlay.set_drop_indicator(indicator)
        if self.is_stopped:
            self.update()
        if indicator != DropIndicator.NONE:
            self.overlay.show()
            self.overlay_hide_timer.stop()

    def _sync_drop_chrome(self, indicator: DropIndicator):
        """Over a cell with no picture, the drop target is the cell's own
        disc, as the stopped and the empty cells draw theirs, in place of
        what the cell says."""

        self.overlay.drop_indicator.set_chrome_colors(
            chrome_color_on_cell(self), self.palette().color(self.backgroundRole())
        )
        self.video_status.set_is_content_shown(indicator == DropIndicator.NONE)

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

    @property
    def is_stoppable(self) -> bool:
        """Playing, or on its way to: loading, reconnecting, or failed and
        about to go on to the next item of its list."""

        return self.video_params is not None and not self.is_stopped

    def show_overlay(self):
        # shown while loading too, and once it failed: for what it shows.
        # Kept in step even while it stays hidden: dragging shows it, and
        # its drop disc is solid over a cell with no picture, see-through
        # over a playing one
        self.status.sync_overlay_mode()
        if self._ctx.is_drag_ui or self._ctx.is_disable_overlay:
            return
        # Hardware overlays are windows of their own; do not remap them while
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

        # it shows a selection to zoom to, or how to make one
        if self.view.is_zoom_ui():
            return

        if self._ctx.is_disable_overlay:
            self.overlay_hide_timer.stop()
            self.overlay.hide()
            return

        # the List window plays in it: it stays in sight, marked
        if self.navigation.is_list_window_shown:
            return

        if not self._ctx.is_overlay_hide_on_timeout:
            return

        self.overlay.hide()

    @only_initialized
    def time_changed(self, new_time):
        is_wrapped = self._is_loop_wrapped(new_time)

        self.time = new_time

        is_seek_on_its_way = self._follow_seek(new_time)

        if self.is_live:
            return

        if self.is_stopped:
            return

        # Where a seek has not got to yet says nothing about the loop. On a
        # stream it lands seconds short, as far back as a short video's wrap
        # would go, and short of a loop's start, from where it would be sent
        # back to land short again, over and over.
        if is_seek_on_its_way:
            return

        if is_wrapped:
            self._loop_wrapped()
            return

        # 100ms headspace for slow callbacks
        if self.time < self.loop_start - 100:
            self._seek_loop_start()

        elif self.time > self.loop_end:
            self.loop_end_action()

        else:
            self.sponsorblock.skip_if_played_into()

    def _is_loop_wrapped(self, new_time) -> bool:
        """Has the video begun another pass since the last time update?"""

        if self._seek_settle_timer.isActive():
            return False

        last_time, self._last_time = self._last_time, new_time

        return is_loop_wrapped(last_time, new_time, self.video_driver.length)

    def _follow_seek(self, new_time) -> bool:
        """Keep up with the last seek, True while the time is its doing.

        That is while it lands, and while it is made again after the stream
        turned it down, the time then being where the one before it went.
        """

        target = self._seek_target

        if target is None:
            return False

        rate = self.video_params.rate

        if self._seek_behind is not None and new_time != target:
            behind, self._seek_behind = self._seek_behind, None

            # the one before it repeated back, which says nothing yet
            if new_time == behind:
                self._seek_behind = behind
                return True

            # The first word since, and it is the one before landing. How far
            # that is from this one's aim cannot tell them apart on a short
            # video: every time there is near enough to be this one landing.
            is_behinds = seek_landing(new_time, behind, None, rate) is not (
                SeekLanding.ASTRAY
            )
            is_this_ones = seek_landing(new_time, target, None, rate) is (
                SeekLanding.ARRIVED
            )

            if is_behinds and not is_this_ones:
                return self._seek_again(new_time)

        landing = seek_landing(new_time, target, self._seek_landed_at, rate)

        if landing is SeekLanding.LANDING:
            if new_time != target and self._seek_landed_at is None:
                self._seek_landed_at = new_time
            return True

        if landing is SeekLanding.ASTRAY and self._seek_retries > 0:
            return self._seek_again(new_time)

        self._seek_target = None
        return False

    def _seek_again(self, new_time) -> bool:
        """Make the last seek again, the stream having turned it down."""

        self._seek_retries -= 1
        self._seek_landed_at = None

        self._log.debug(
            f"Seek to {self._seek_target} did not take, at {new_time} instead"
        )

        # not from in here: the driver would report the time from inside the
        # call, back into this one before it is done
        QTimer.singleShot(0, self._retry_seek)

        return True

    def _retry_seek(self):
        if self._seek_target is None or not self.is_video_initialized:
            return

        self._last_time = self._seek_target
        self._seek_settle_timer.start()

        self.video_driver.set_time(self._seek_target)

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

        if self._hold_end_for_bookmarks():
            return

        if self._step_at_end(end_action):
            return

        if end_action == VideoEndAction.LOOP_FILE:
            self._loop_to_start()
        elif end_action == VideoEndAction.PAUSE:
            self._pause_at_start()
        elif end_action == VideoEndAction.STOP:
            self.stop_playback()
        elif end_action == VideoEndAction.CLOSE:
            QTimer.singleShot(0, self.close)

    def _step_at_end(self, end_action: VideoEndAction) -> bool:
        """On to another file, or item of the list, if that is what the
        video does at its end; whether it went."""

        step = {
            VideoEndAction.NEXT_FILE: self.navigation.next,
            VideoEndAction.PREVIOUS_FILE: self.navigation.previous,
            VideoEndAction.SHUFFLE_FILE: self.navigation.shuffle,
        }.get(end_action)

        if step is None:
            return False

        step(is_end=True)

        return True

    def _loop_to_start(self):
        if self.video_params.is_start_random:
            self.seek_random(is_viewers=False)
        else:
            self._seek_loop_start()

    def _seek_loop_start(self):
        """Back to where a pass starts.

        Where a loop starts is the viewer's choice, a sponsor or not. Where
        the video starts is nobody's, and an intro there is skipped on every
        pass as it was on the first.
        """

        self.seek(self.loop_start, is_viewers=self.video_params.loop_start is not None)

    def _pause_at_start(self):
        self._seek_loop_start()
        self.set_pause(True)

    def _hold_end_for_bookmarks(self) -> bool:
        """Pause at the start in place of an end action that would take the
        video out of its cell, while its bookmarks are being edited, and say
        whether it did.

        The bookmarks manager, or a bookmark's name being typed or its
        colour picked, holds the video in its cell: closed, or another file
        put in its place, it would take the bookmarks being edited away with
        it. The end action is the same again on the next pass.
        """

        end_action = self.video_params.end_action

        if not self.bookmarker.is_editing or end_action not in LEAVING_END_ACTIONS:
            return False

        self._pause_at_start()

        self.bookmarker.tell_end_held(end_action)

        return True

    def stop_playback(self):
        # stopped from the menu as from its own Stop, nothing left to start
        # it again by itself: a reconnect counting down, a link still being
        # resolved, a list being read, the next item of its list (below)
        self.recovery.drop_retries()
        self.navigation.is_waiting_for_list_read = False

        if self.url_resolver is not None and self.url_resolver.is_busy:
            self.reset_url_resolver()

        self.navigation.cancel_steps()

        # one that failed, stopped, is a stopped one like any other: played
        # from there, not left on Try Again with its reason gone
        self._is_error = False

        # nor as far as it got loading: played again, its steps start afresh
        self.status.load_stage = None

        if self.video_params is not None:
            self._ctx.lists.stop_waiting(self.video_params.id)

            self.video_params.current_position = 0
            self.video_params.loop_start = None
            self.video_params.loop_end = None
            self.loop_start_change.emit(0)
            self.loop_end_change.emit(100.0)

        self._set_playback_state(VideoInitialState.STOPPED)

        # gone before the cell is painted as its player is let go
        self.video_status.hide()
        self._destroy_video_driver()
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
            self._apply_snapshot_of_another_file(snapshot)
            return

        # the snapshot's view is the one to show
        self.view.forget_view_to_follow()

        self.color = snapshot.color.as_hex()

        if snapshot.is_stopped:
            self._take_snapshot_params(snapshot)
            self._destroy_video_driver()
            self._present_stopped()
            return

        if not self.is_video_initialized:
            self._take_snapshot_params(snapshot)
            self._start_load()
            return

        if self.video_tracks and is_deinterlace_reload_needed(
            self.video_params, snapshot.deinterlace, snapshot.deinterlace_mode
        ):
            self._take_snapshot_params(snapshot)
            self.reload()
            return

        self.set_video_track(snapshot.video_track_id)
        self.audio.restore_selection(snapshot.audio_selection)

        self.audio.set_channel_mode(snapshot.audio_channel_mode)
        self.audio.set_delay(snapshot.audio_delay_ms, is_silent=True)

        self.subtitles.restore_selection(snapshot.subtitle_selection)
        self.subtitles.set_delay(snapshot.subtitle_delay_ms, is_silent=True)

        self.view.set_cell_view_mode(snapshot.cell_view_mode)
        self.view.set_aspect_ratio(snapshot.aspect_ratio, is_silent=True)
        self.set_deinterlace_params(snapshot.deinterlace, snapshot.deinterlace_mode)
        self.audio.set_muted(snapshot.is_muted)
        self.set_pause(snapshot.is_paused)
        self.view.set_scale(snapshot.scale, is_silent=True)
        self.view.set_zoom_to_cursor(snapshot.is_zoom_to_cursor)
        self.view.set_crop(snapshot.crop, is_silent=True)
        self.view.set_anchor(snapshot.anchor)
        self.view.set_shift_past_edges(snapshot.is_shift_past_edges)
        self.view.set_shift(snapshot.shift, is_silent=True)
        self.audio.set_volume(snapshot.volume)

        self.seek(snapshot.current_position)
        self.loop.set_start_time(snapshot.loop_start)
        self.loop.set_end_time(snapshot.loop_end)
        self.set_rate(snapshot.rate, is_silent=True)

        self.stream.switch_quality(snapshot.stream_quality)
        self.stream.set_reload_timer(snapshot.auto_reload_timer_min)

        self._take_snapshot_params(snapshot)

    def adopt_defaults(self, update: dict):
        """Settings changed for new videos made this one's too, as asked in
        the Playlist window: by the field of its video, the values, checked.

        What shows is changed as it plays; what is only read when the video
        is opened has it opened again; the rest is read when next needed.
        """

        params = self.video_params
        new = params.model_copy(update=update)

        if "color" in update:
            self.color = new.color.as_hex()

        if not self.is_video_initialized:
            self.video_params = new
            return

        if (
            is_reopen_needed(params, new)
            or new.transform != params.transform
            or (
                self.video_tracks
                and is_deinterlace_reload_needed(
                    params, new.deinterlace, new.deinterlace_mode
                )
            )
        ):
            self.video_params = new
            self.reload()
            return

        live = {
            "cell_view_mode": self.view.set_cell_view_mode,
            "aspect_ratio": lambda ratio: self.view.set_aspect_ratio(
                ratio, is_silent=True
            ),
            "is_muted": self.audio.set_muted,
            "volume": self.audio.set_volume,
            "audio_channel_mode": self.audio.set_channel_mode,
            "audio_selection": self.audio.restore_selection,
            "subtitle_selection": self.subtitles.restore_selection,
            "scale": lambda scale: self.view.set_scale(scale, is_silent=True),
            "is_zoom_to_cursor": self.view.set_zoom_to_cursor,
            "crop": lambda crop: self.view.set_crop(crop, is_silent=True),
            "anchor": self.view.set_anchor,
            "is_shift_past_edges": self.view.set_shift_past_edges,
            "rate": lambda rate: self.set_rate(rate, is_silent=True),
            "stream_quality": self.stream.switch_quality,
            "auto_reload_timer_min": self.stream.set_reload_timer,
        }

        if {"deinterlace", "deinterlace_mode"} & update.keys():
            self.set_deinterlace_params(new.deinterlace, new.deinterlace_mode)

        for field in update:
            if field in live:
                live[field](getattr(new, field))

            # what a setter turned away, as one with no tracks to set it on
            setattr(self.video_params, field, getattr(new, field))

    def _take_snapshot_params(self, snapshot: Video):
        """The snapshot's video in place of the cell's, and named as it
        was then."""

        self.video_params = snapshot.model_copy()

        self.title = self._custom_title or self._default_title

    def _apply_snapshot_of_another_file(self, snapshot: Video):
        """Put the file the snapshot was taken of back in the cell, as the
        snapshot has it: the cell went on to another file since, the next
        on its list or in its folder."""

        self.bookmarker.close_manager()
        self.navigation.cancel_steps()

        self.view.forget_view_to_follow()
        self.navigation.held_item = None
        self._title = None
        self._default_title = None

        self.set_video(snapshot.model_copy())

    def set_video(self, video_params: Video):
        is_first_video = self.video_params is None
        is_reopen = is_reopen_needed(self.video_params, video_params)

        # another video in place of one waiting for its list: not read for it
        if not is_first_video and self.video_params.id != video_params.id:
            self._ctx.lists.stop_waiting(self.video_params.id)

        # a list the playlist does not have, as one edited by hand would
        if self._ctx.lists.get(video_params.list_id) is None:
            video_params.list_id = None
            video_params.list_index = None

        self.video_params = video_params

        if video_params.list_id is not None:
            self._ctx.lists.take_up(video_params.list_id)

        self.navigation.show_list_place()

        # known by its item from now on, the list read again at the latest
        # as the playlist opens
        self.navigation.held_item = self.list_item

        # a file's bookmarks left from when they were shared, if this is the
        # first cell to open it since
        self._ctx.bookmarks.claim(self.video_params.uri, self.video_params.id)

        # another video in the cell's place, or this one given to it again:
        # a reload of the one before still to come is not for it, and it
        # may be reloaded as many times as any; one that is reloaded comes
        # back here as the cell's first
        if not is_first_video:
            self.recovery.drop_retries()
            self._has_item_played = False

        # Shut down current video
        if not is_first_video or is_reopen:
            self.reset()

        if self.video_params.is_stopped and not self.is_video_initialized:
            self._present_stopped()
            return

        self._start_load()

    def _present_waiting(self):
        """The cell there at once, saying so while the list it is to play
        is read: a channel list from a provider can take a minute."""

        self._present_unloaded("processing", translate("Lists", "Reading the list…"))

        self.status.load_steps = (LoadStage.LIST, LoadStage.VIDEO)
        self.status.show_stage(LoadStage.LIST, translate("Lists", "Reading the list…"))

    def _present_gone_file(self):
        """The file the cell is on gone, and its list not read again to go
        on along: the cell says so."""

        self._is_error = True
        self._present_unloaded("error", translate("Lists", "File not found"))

    def _present_unloaded(self, status: str, text: str):
        self.status.show(status)
        self.status.set_text(text)

        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        self.title = self._custom_title or self._default_title
        self.color = self.video_params.color.as_hex()

    def _present_stopped(self):
        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        if self.title is None:
            self.title = self._custom_title or self._default_title

        self.color = self.video_params.color.as_hex()
        self.is_audio_present_change.emit(False)
        self.is_paused_change.emit(True)
        self.is_stopped_change.emit(True)
        self.video_status.hide()
        self._sync_cell_background()
        self.update()
        self.show_overlay()

    def _start_load(self):
        # what went wrong before is behind it, but while it is tried again
        if self.recovery.retries == 0:
            self.status.last_error = None

        self.recovery.stop_skip_note()

        # named from the start, on the overlay shown while it loads: a link
        # by its file name until its page gives it a title
        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        if self.title is None:
            self.title = self._custom_title or self._default_title

        # a list still being read for it: nothing to load until it is
        if self._ctx.lists.is_waiting(self.video_params.id):
            self._present_waiting()
            return

        # saved with the playlist as it waited: read again
        if self.video_params.read_as_list:
            self._ctx.commands.read_for_cell(self.video_params)
            self._present_waiting()
            return

        self.navigation.is_waiting_for_list_read = False

        if self.navigation.is_list_file_gone:
            self.navigation.go_on_from_gone_file()
            return

        self._sync_cell_background()
        self._ensure_video_driver()

        # the list read for it, if it was, then the link, then the video
        was_listed = self.status.load_stage is LoadStage.LIST
        self.status.load_steps = (
            *((LoadStage.LIST,) if was_listed else ()),
            *((LoadStage.LINK,) if self.video_params.is_http_url else ()),
            LoadStage.VIDEO,
        )

        self.audio.take_file_for_load()
        self.subtitles.take_files_for_load()

        # the video may not be the one that was here, whatever else stays;
        # a URL is resolved again and brings the site's list back with it
        self.chapters.set_site_chapters(())
        self._site_length_ms = 0

        # and SponsorBlock is asked about it again, if it is one to ask about
        self._youtube_id = None
        self.sponsorblock.forget()

        # a file is never adaptive; a URL says so once its stream is picked
        self.stream.is_adaptive = False

        if self.video_params.is_http_url:
            self.status.show_resolving_link()
            self.url_resolver.resolve(self.video_params.uri, self._item_headers)
        else:
            self.status.show_opening()
            self.load_video.emit(
                MediaInput(
                    uri=str(self.video_params.uri),
                    is_live=False,
                    is_audio_only=False,
                    size=self.size_tuple,
                    video=self.video_params,
                    selected_audio_slave=self.audio.selected_slave_uri,
                    selected_subtitle_slaves=self.subtitles.selected_slave_uris,
                )
            )

    def _load_and_play(self):
        if self._is_error or self._is_state_change_in_progress:
            return

        self._is_state_change_in_progress = True
        self._in_progress_timer.start()
        self._set_playback_state(VideoInitialState.PLAYING)
        self.status.show("processing")
        self._start_load()

    def set_video_url(self, video: ResolvedVideo):
        self._default_title = video.title

        if self._custom_title is None:
            self.title = video.title

        self.streams = video.streams
        self.is_live = video.is_live

        # kept, like the streams, through a switch of quality or of dub
        self.chapters.set_site_chapters(video.chapters)
        self._site_length_ms = video.duration_ms

        self._youtube_id = video.youtube_id
        self.sponsorblock.look_up()

        self.navigation.learn_item_details(video.details)

        self.stream.load_quality(self.video_params.stream_quality)

    def load_video_finish(self):
        # the video is playing, so whatever went wrong before is behind us
        self.recovery.note_played()
        self.status.last_error = None

        # a fresh player has no pass behind it to compare times against
        self._last_time = None

        # final verdict belongs to VLC
        self.is_live = self.video_driver.is_live

        if self._default_title is None:
            self._default_title = self.video_params.uri_name

        if self.title is None:
            self.title = self._custom_title or self._default_title

        self.color = self.video_params.color.as_hex()

        self._has_item_played = True

        self.navigation.learn_item_length()

        self.audio.set_channel_mode(self.video_params.audio_channel_mode)
        self.audio.set_delay(self.video_params.audio_delay_ms, is_silent=True)

        self.audio.set_volume(self.video_params.volume)
        self.audio.set_muted(self.video_params.is_muted)

        self.loop.set_start_time(self.video_params.loop_start)
        self.loop.set_end_time(self.video_params.loop_end)
        self.set_rate(self.video_params.rate, is_silent=True)

        self.stream.set_reload_timer(self.video_params.auto_reload_timer_min)

        self.video_params.video_track_id = self.video_driver.cur_video_track_id

        # a fresh player shows the picture, loaded in the tray it is not to
        self._is_video_stopped_in_tray = False
        if getattr(self._ctx, "is_video_decoding_stopped", False):
            self.set_video_decoding_stopped(True)

        self.chapters.update()
        self.sponsorblock.update()

        self.is_audio_present_change.emit(bool(self.audio.tracks))

        self.audio.adopt_if_silent()

        # over the video until there is a picture of it to show instead
        self.status.is_kept_for_picture = self.video_driver.is_picture_pending
        if not self.status.is_kept_for_picture:
            self.video_status.hide()

        self.view.follow_synced()

        self.video_driver.show()
        self.is_stopped_change.emit(self.is_stopped)
        self.time_change.emit(self.time, self.video_driver.length)
        self.show_overlay()

        notice = self.navigation.take_notice()

        if notice is not None:
            self.info_change.emit(notice)

        self.video_driver.adjust_view()

    def _picture_shown(self):
        """Take the loading status off the video, now there is a picture.

        On Windows the status is a native window over the frame's, as made
        (seen in the window tree), so it keeps VLC's windows and their black
        out of sight until then. Unless it has been given something else to
        show since.

        The overlay is held back until then too: shown on the load, it sat
        over a loading status still counting, for up to as long as the
        picture takes (see FIRST_PICTURE_TIMEOUT_MS), a stream's longest.
        """
        if not self.status.is_kept_for_picture:
            return

        self.status.is_kept_for_picture = False

        self.video_status.hide()
        self.show_overlay()

    @only_with_video_tacks
    def set_transform(self, transform: VideoTransform):
        self.video_params.transform = transform

        self.reload()

    @only_with_video_tacks
    def set_deinterlace(self, deinterlace: VideoDeinterlace):
        self.set_deinterlace_params(deinterlace, self.video_params.deinterlace_mode)

    @only_with_video_tacks
    def set_deinterlace_mode(self, mode: VideoDeinterlaceMode):
        # picking a mode is asking for it, as it is in VLC's own menu
        deinterlace = self.video_params.deinterlace
        if deinterlace == VideoDeinterlace.OFF:
            deinterlace = VideoDeinterlace.ON

        self.set_deinterlace_params(deinterlace, mode)

    @only_with_video_tacks
    def set_deinterlace_params(
        self, deinterlace: VideoDeinterlace, mode: VideoDeinterlaceMode
    ):
        is_reload_needed = is_deinterlace_reload_needed(
            self.video_params, deinterlace, mode
        )

        self.video_params.deinterlace = deinterlace
        self.video_params.deinterlace_mode = mode

        if is_reload_needed:
            self.reload()
        else:
            self.video_driver.set_deinterlace(deinterlace, mode)

    @property
    def seek_marks(self) -> tuple[SeekMark, ...]:
        """What the seek bar marks, as last told by seek_marks_change."""

        return self._seek_marks

    def update_seek_marks(self):
        """Tell the seek bar what to mark: chapters, SponsorBlock's, and the
        viewer's bookmarks."""

        chapters = (
            SeekMark(
                time_ms=chapter.start_ms,
                label=self.chapters.name(index),
                kind=SeekMarkKind.CHAPTER,
            )
            for index, chapter in enumerate(self.chapters.all)
        )

        segments = (
            segment_mark(segment) for segment in self.sponsorblock.shown_segments
        )

        bookmarks = ()
        if self.is_video_initialized and not self.is_live:
            bookmarks = self.bookmarker.marks(self.video_driver.length)

        marks = (*chapters, *segments, *bookmarks)

        if marks == self._seek_marks:
            return

        self._seek_marks = marks

        self.seek_marks_change.emit(marks)

    # the viewer's bookmarks; what is done with them is the Bookmarker's

    @property
    def bookmarks(self) -> tuple[Bookmark, ...]:
        if self.video_params is None:
            return ()

        return self._ctx.bookmarks.get(self.video_params.uri, self.video_params.id)

    @only_seekable
    def set_end_action(self, end_action: VideoEndAction):
        self.navigation.cancel_steps()

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
    def seek_step(self, slot, direction):
        """Seek by one of the playlist's steps, "short", "medium" or "long",
        forwards (direction 1) or back (-1)."""

        self.seek_shift_ms(direction * seek_step_ms(slot))

    @only_initialized
    @only_seekable
    def seek_random(self, is_viewers=True):
        random_ms = random.randint(self.loop_start, self.loop_end)

        self.seek(random_ms, is_viewers=is_viewers)

    @only_initialized
    @only_seekable
    def seek_percent(self, percent):
        seek_ms = int(percent * self.video_driver.length)

        self.seek(seek_ms)

    @only_initialized
    @only_seekable
    def seek(self, seek_ms, is_viewers=True):
        """Go to a time, for the viewer or for the player itself.

        A stretch to be skipped that a seek of the viewer's lands in is left
        to play, the viewer having gone there. One the player lands in, going
        round to the start or past another, is skipped as it would be if it
        were played into.
        """

        if seek_ms < self.loop_start or seek_ms > self.loop_end:
            seek_ms = self.loop_start

        # the viewer going back into the video stays in it, whatever file
        # its end was looking for
        if is_viewers:
            self.navigation.cancel_steps()

        # Marked before the seek is made, not after: the single process
        # drivers call libVLC on this very thread, and it reports the new time
        # from inside that call. Marked afterwards, a seek that moves the time
        # backwards -- wheeling past the end lands back at the start -- reads
        # as a finished pass, and the end action then stops the player from
        # inside libVLC, which deadlocks against the seek it is still making.
        self._last_time = seek_ms
        self._seek_settle_timer.start()

        # made before the one before it has landed, while the stream is still
        # restarting for that one, it is likely to be turned down
        is_behind = self._seek_target is not None and self._seek_landed_at is None
        behind = self._seek_target

        self._seek_target = seek_ms
        self._seek_landed_at = None

        # one that close to the end can run into it before it is seen to
        # arrive, which is no sign of it having been turned down
        is_near_end = self.video_driver.length - seek_ms <= SEEK_ARRIVAL_MS
        self._seek_retries = (
            SEEK_RETRIES if self.stream.is_adaptive and not is_near_end else 0
        )
        self._seek_behind = behind if is_behind and self._seek_retries else None

        self.sponsorblock.note_seek(seek_ms, is_viewers)

        self.time = seek_ms
        self.video_driver.set_time(seek_ms)

    @property
    def arriving_time(self) -> int:
        """Where the video is, a seek still on its way counting as there already.

        Read off the time alone, a seek on a stream sits short of where it
        was aimed for a second or so: a jump to a chapter reads as still in
        the one before, so a press of next jumps to the same one again.
        """

        return arriving_time(self.time, self._seek_target)

    @property
    def is_seek_on_its_way(self) -> bool:
        """Whether the last seek has yet to be seen to land."""

        return self._seek_target is not None

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

    def manual_view(self, command, *args):
        """Zoom or move the picture as the viewer asked, for the others to
        follow where their views are synced (see VideoBlocksManager).

        The view as it then is, even where the command left it as it was:
        the others come to show what this one does, from wherever they are.
        What the command gives back goes back (see ViewControl.pan_by).
        """

        result = attrgetter(command)(self)(*args)

        synced = self.view.synced()

        if synced is not None:
            self.sync_view.emit(synced)

        return result

    def manual_rate(self, command):
        """Change the speed as the viewer asked, for the others to follow
        where speeds are synced (see VideoBlocksManager)."""

        attrgetter(command)(self)()

        if self.is_video_initialized and not self.is_live:
            self.sync_rate.emit(self.video_params.rate)

    def follow_rate(self, rate: float):
        """Play at another video's speed, quietly. One that is not playing
        yet plays at it once it is."""

        if self.is_live:
            return

        self.video_params.rate = rate

        self.set_rate(rate, is_silent=True)

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

    def play_pause(self):
        """Play or pause as the viewer asked, the others following where
        playing and pausing is synced (see VideoBlocksManager)."""

        if self._is_state_change_in_progress:
            return

        is_paused = not self.video_params.is_paused

        self.set_pause(is_paused)

        self.sync_pause.emit(is_paused)

    def rename(self):
        cur_title = self.title

        new_data = QVideoRenameDialog.get_edits(
            parent=self.parent(),
            title=translate("Dialog - Rename video", "Rename video", "Header"),
            orig_title=self._default_title,
            cur_title=cur_title,
            cur_color=self.video_params.color.as_rgb_tuple(),
        )

        if new_data is None:
            return

        new_name, new_color = new_data

        self.video_params.color = Color(new_color)

        custom_title = None if new_name == self._default_title else new_name

        item = self.list_item

        # on a list, the item is what is named, for every cell playing it;
        # its name left be where only the color was changed, the name
        # the list gave it the list's still
        if self.media_list is not None and item is not None:
            if new_name != cur_title:
                self._ctx.lists.rename_item(
                    self.video_params.list_id, item.key, custom_title
                )
        else:
            self.video_params.title = custom_title

        self.title = new_name
        self.color = self.video_params.color.as_hex()
