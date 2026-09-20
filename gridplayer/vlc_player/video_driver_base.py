import logging
from abc import abstractmethod

from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.utils.qt import MILLISECONDS, QABC
from gridplayer.vlc_player.static import Media, MediaInput


class VLCVideoDriver(QObject, metaclass=QABC):
    time_changed = pyqtSignal(MILLISECONDS)
    playback_status_changed = pyqtSignal(int)
    load_finished = pyqtSignal(Media)
    tracks_changed = pyqtSignal(Media)
    snapshot_taken = pyqtSignal(str)
    video_dimensions_changed = pyqtSignal(int, int)

    error = pyqtSignal(str)
    crash = pyqtSignal(str)
    update_status = pyqtSignal(str, int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._log = logging.getLogger(self.__class__.__name__)

    def cleanup(self) -> None:
        """Release the player and wait until it is gone."""
        self.cleanup_start()
        self.cleanup_wait()

    def cleanup_start(self) -> None:
        """Ask the player to release itself, without waiting for it.

        Releasing a hardware video output takes a noticeable moment, and
        cleanup() blocks for it. Closing a grid one pane at a time then reads
        as a cascade of videos going dark, so callers that close several
        players at once start all of them here and only then wait; see
        VideoBlocksManager.close_all.
        """

    def cleanup_wait(self) -> None:
        """Block until the release started by cleanup_start has finished.

        Called once per cleanup_start, and safe to call again after that.
        """

    def time_changed_emit(self, new_time):
        self.time_changed.emit(new_time)

    def playback_status_changed_emit(self, status):
        self.playback_status_changed.emit(status)

    @abstractmethod
    def load_video(self, media_input: MediaInput): ...

    def load_video_done(self, media_track: Media):
        self.load_finished.emit(media_track)

    def tracks_changed_emit(self, media_track: Media):
        self.tracks_changed.emit(media_track)

    @abstractmethod
    def snapshot(self): ...

    def snapshot_taken_emit(self, snapshot_path):
        self.snapshot_taken.emit(snapshot_path)

    def set_video_dimensions(self, width, height):
        self.video_dimensions_changed.emit(width, height)

    @abstractmethod
    def play(self): ...

    @abstractmethod
    def set_pause(self, is_paused): ...

    @abstractmethod
    def set_time(self, seek_ms): ...

    @abstractmethod
    def set_playback_rate(self, rate): ...

    @abstractmethod
    def audio_set_mute(self, is_muted): ...

    @abstractmethod
    def audio_set_volume(self, volume): ...

    @abstractmethod
    def set_audio_track(self, track_id): ...

    @abstractmethod
    def add_audio_slave(self, uri): ...

    @abstractmethod
    def set_video_track(self, track_id): ...

    @abstractmethod
    def set_audio_channel_mode(self, mode): ...

    @abstractmethod
    def set_audio_delay(self, delay_ms): ...

    def error_state(self, error):
        self.error.emit(error)

    def update_status_emit(self, status, percent):
        self.update_status.emit(status, percent)
