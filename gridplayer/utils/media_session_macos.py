"""The Now Playing center, macOS' way to the media keys.

Qt never sees a media key on macOS: they go to the app the system has as
Now Playing, and with none, the play key opens Music. An app is Now
Playing once it says what it plays and has a command center target to
take the keys.

MediaPlayer is loaded with pyobjc-core alone, not pyobjc-framework-MediaPlayer:
that one imports AVFoundation and so CoreMedia, whose pyobjc 13.0 build can't
load on macOS 15 (it looks for @rpath/libswiftCoreMedia.dylib in Python's own
folder).
"""

import functools
from types import SimpleNamespace

import objc
from Foundation import NSBundle
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

_FRAMEWORK = "/System/Library/Frameworks/MediaPlayer.framework"

# MediaPlayer's own values: MPNowPlayingInfoMediaType, MPNowPlayingPlaybackState,
# MPRemoteCommandHandlerStatus
_MEDIA_TYPE_VIDEO = 2
_STATE_PLAYING = 1
_STATE_PAUSED = 2
_STATE_STOPPED = 3
_HANDLED = 0


@functools.cache
def _media_player() -> SimpleNamespace:
    """MediaPlayer's two classes and the keys of what's playing."""

    bundle = NSBundle.bundleWithPath_(_FRAMEWORK)
    if bundle is None or not bundle.load():
        raise RuntimeError(f"Can't load {_FRAMEWORK}")

    keys = {}
    objc.loadBundleVariables(
        bundle,
        keys,
        [
            ("MPMediaItemPropertyTitle", b"@"),
            ("MPNowPlayingInfoPropertyMediaType", b"@"),
        ],
    )

    # the handler is a block taking the event and saying how it went
    objc.registerMetaDataForSelector(
        b"MPRemoteCommand",
        b"addTargetWithHandler:",
        {
            "arguments": {
                2: {
                    "callable": {
                        "retval": {"type": b"q"},
                        "arguments": {0: {"type": b"^v"}, 1: {"type": b"@"}},
                    }
                }
            }
        },
    )

    return SimpleNamespace(
        command_center=objc.lookUpClass("MPRemoteCommandCenter"),
        info_center=objc.lookUpClass("MPNowPlayingInfoCenter"),
        title_key=keys["MPMediaItemPropertyTitle"],
        media_type_key=keys["MPNowPlayingInfoPropertyMediaType"],
    )


_STATUS = {
    PlaybackStatus.PLAYING: _STATE_PLAYING,
    PlaybackStatus.PAUSED: _STATE_PAUSED,
    PlaybackStatus.STOPPED: _STATE_STOPPED,
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

        self._media_player = _media_player()
        center = self._media_player.command_center.sharedCommandCenter()

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
        media_player = self._media_player
        info_center = media_player.info_center.defaultCenter()

        keys = frozenset() if state is None else state.keys
        for key, command in self._commands.items():
            command.setEnabled_(key in keys)

        if state is None:
            info_center.setNowPlayingInfo_(None)
            info_center.setPlaybackState_(_STATE_STOPPED)
            return

        info_center.setNowPlayingInfo_(
            {
                media_player.title_key: state.title,
                media_player.media_type_key: _MEDIA_TYPE_VIDEO,
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
            return _HANDLED

        return handle
