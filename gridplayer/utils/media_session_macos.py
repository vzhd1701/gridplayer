"""The Now Playing center, macOS' way to the media keys.

Qt never sees a media key on macOS: they go to the app the system has as
Now Playing, and with none, the play key opens Music. An app is Now
Playing once it says what it plays and has a command center target to
take the keys.

Needs pyobjc-framework-MediaPlayer.
"""

from MediaPlayer import (
    MPMediaItemPropertyTitle,
    MPNowPlayingInfoCenter,
    MPNowPlayingInfoMediaTypeVideo,
    MPNowPlayingInfoPropertyMediaType,
    MPNowPlayingPlaybackStatePaused,
    MPNowPlayingPlaybackStatePlaying,
    MPNowPlayingPlaybackStateStopped,
    MPRemoteCommandCenter,
    MPRemoteCommandHandlerStatusSuccess,
)
from PyQt5.QtCore import QObject, pyqtSignal

from gridplayer.utils.media_session import (
    KEY_NEXT,
    KEY_PAUSE,
    KEY_PLAY,
    KEY_PLAY_PAUSE,
    KEY_PREVIOUS,
    KEY_STOP,
    MediaState,
    PlaybackStatus,
)

_STATUS = {
    PlaybackStatus.PLAYING: MPNowPlayingPlaybackStatePlaying,
    PlaybackStatus.PAUSED: MPNowPlayingPlaybackStatePaused,
    PlaybackStatus.STOPPED: MPNowPlayingPlaybackStateStopped,
}

# not offered: with no target and turned off, the system shows none of them
_UNUSED_COMMANDS = (
    "changePlaybackPositionCommand",
    "changePlaybackRateCommand",
    "seekForwardCommand",
    "seekBackwardCommand",
    "skipForwardCommand",
    "skipBackwardCommand",
    "changeRepeatModeCommand",
    "changeShuffleModeCommand",
)


class NowPlayingSession(QObject):
    command = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        center = MPRemoteCommandCenter.sharedCommandCenter()

        for name in _UNUSED_COMMANDS:
            getattr(center, name)().setEnabled_(False)

        commands = {
            KEY_PLAY_PAUSE: center.togglePlayPauseCommand(),
            KEY_PLAY: center.playCommand(),
            KEY_PAUSE: center.pauseCommand(),
            KEY_STOP: center.stopCommand(),
            KEY_NEXT: center.nextTrackCommand(),
            KEY_PREVIOUS: center.previousTrackCommand(),
        }

        self._commands = commands
        self._targets = {
            key: command.addTargetWithHandler_(self._handler(key))
            for key, command in commands.items()
        }

        self.update(None)

    def update(self, state: MediaState | None):
        info_center = MPNowPlayingInfoCenter.defaultCenter()

        keys = frozenset() if state is None else state.keys
        for key, command in self._commands.items():
            command.setEnabled_(key in keys)

        if state is None:
            info_center.setNowPlayingInfo_(None)
            info_center.setPlaybackState_(MPNowPlayingPlaybackStateStopped)
            return

        info_center.setNowPlayingInfo_(
            {
                MPMediaItemPropertyTitle: state.title,
                MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaTypeVideo,
            }
        )
        info_center.setPlaybackState_(_STATUS[state.status])

    def close(self):
        self.update(None)

        for key, target in self._targets.items():
            self._commands[key].removeTarget_(target)

        self._targets = {}

    def _handler(self, key):
        # called on the main thread, from Qt's own event loop
        def handle(_event):
            self.command.emit(key)
            return MPRemoteCommandHandlerStatusSuccess

        return handle
