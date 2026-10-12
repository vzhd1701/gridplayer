"""The System Media Transport Controls, Windows' way to the media keys.

Windows sends the media keys to the window in focus first, and what it
leaves alone to the player whose media controls it last saw playing: the
player itself in the background, or another, as the one played last.
The controls are a MediaPlayer's, with its own handling of them turned
off: the window's own are only to be had through a COM call pywinrt does
not offer.
"""

from PyQt5.QtCore import QObject, pyqtSignal
from winrt.windows.media import (
    MediaPlaybackStatus,
    MediaPlaybackType,
    SystemMediaTransportControlsButton,
)
from winrt.windows.media.playback import MediaPlayer

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
from gridplayer.utils.win32_com import keep_mta_alive

# Windows has no play / pause button: it sends the play / pause key as Play
# or Pause, by what it was last told
_BUTTON_KEYS = {
    SystemMediaTransportControlsButton.PLAY: KEY_PLAY,
    SystemMediaTransportControlsButton.PAUSE: KEY_PAUSE,
    SystemMediaTransportControlsButton.STOP: KEY_STOP,
    SystemMediaTransportControlsButton.NEXT: KEY_NEXT,
    SystemMediaTransportControlsButton.PREVIOUS: KEY_PREVIOUS,
}

_STATUS = {
    PlaybackStatus.PLAYING: MediaPlaybackStatus.PLAYING,
    PlaybackStatus.PAUSED: MediaPlaybackStatus.PAUSED,
    PlaybackStatus.STOPPED: MediaPlaybackStatus.STOPPED,
}


class SmtcSession(QObject):
    # sent from a thread of Windows' own, and so queued to the player's
    command = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # the buttons come on threads of the multithreaded apartment, which
        # must not go down under them, see keep_mta_alive
        keep_mta_alive()

        self._player = MediaPlayer()
        self._player.command_manager.is_enabled = False

        self._controls = self._player.system_media_transport_controls
        self._controls.is_enabled = False

        self._button_token = self._controls.add_button_pressed(self._on_button)

    def update(self, state: MediaState | None):
        controls = self._controls
        display = controls.display_updater

        if state is None:
            display.clear_all()
            display.update()

            controls.playback_status = MediaPlaybackStatus.CLOSED
            controls.is_enabled = False
            return

        controls.is_play_enabled = bool(state.keys & {KEY_PLAY, KEY_PLAY_PAUSE})
        controls.is_pause_enabled = bool(state.keys & {KEY_PAUSE, KEY_PLAY_PAUSE})
        controls.is_stop_enabled = KEY_STOP in state.keys
        controls.is_next_enabled = KEY_NEXT in state.keys
        controls.is_previous_enabled = KEY_PREVIOUS in state.keys

        controls.playback_status = _STATUS[state.status]
        controls.is_enabled = True

        display.type = MediaPlaybackType.VIDEO
        display.video_properties.title = state.title
        display.update()

    def close(self):
        self.update(None)

        self._controls.remove_button_pressed(self._button_token)
        self._player.close()

    def _on_button(self, _controls, event):
        key = _BUTTON_KEYS.get(event.button)

        if key is not None:
            self.command.emit(key)
