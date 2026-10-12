"""The player as the system's media player, for media keys in the background.

Each system sends media keys, headset buttons and the buttons of its own
media panel to the player it thinks is playing: Windows through its media
controls (SMTC), Linux desktops through MPRIS, macOS through its Now
Playing center. The player tells it what is playing and gets the buttons
back as the media keys they stand for, to run whatever the keymap binds
them to.
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto

from gridplayer.params import env

# the media keys as the keymap writes them
KEY_PLAY_PAUSE = "Toggle Media Play/Pause"
KEY_PLAY = "Media Play"
KEY_PAUSE = "Media Pause"
KEY_STOP = "Media Stop"
KEY_NEXT = "Media Next"
KEY_PREVIOUS = "Media Previous"

MEDIA_KEYS = (KEY_PLAY_PAUSE, KEY_PLAY, KEY_PAUSE, KEY_STOP, KEY_NEXT, KEY_PREVIOUS)

_log = logging.getLogger(__name__)


class PlaybackStatus(Enum):
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()


@dataclass(frozen=True)
class MediaState:
    """What the system is told; equal states are not told twice."""

    status: PlaybackStatus
    title: str
    # which of the media keys have something to do
    keys: frozenset[str]


def make_media_session(parent):
    """This system's media session, None where there is none to be had.

    It has a ``command`` signal with the media key a button stands for,
    ``update(MediaState | None)``, None letting the system's media keys go
    to other players, and ``close()``. Where the system can bring the
    player's window up, a ``raise_requested`` signal too.
    """

    try:
        if env.IS_LINUX:
            from gridplayer.utils.media_session_linux import MprisSession

            return MprisSession(parent)

        if env.IS_WINDOWS:
            from gridplayer.utils.media_session_windows import SmtcSession

            return SmtcSession(parent)

        if env.IS_MACOS:
            from gridplayer.utils.media_session_macos import NowPlayingSession

            return NowPlayingSession(parent)
    except Exception as e:
        # no D-Bus session, a Windows too old for the media controls
        _log.warning(f"Media keys in the background are not available: {e}")
        _log.debug("Media session failed", exc_info=True)

    return None
