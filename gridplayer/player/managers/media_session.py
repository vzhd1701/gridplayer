from PyQt5.QtCore import QTimer

from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.media_session import (
    KEY_PAUSE,
    KEY_PLAY,
    KEY_PLAY_PAUSE,
    MEDIA_KEYS,
    MediaState,
    PlaybackStatus,
    make_media_session,
)
from gridplayer.utils.qt import count_txt, translate

# what the system is told is caught up with this often as well, for what
# changes with no signal to say so: a video's name, a video done loading
REFRESH_MS = 1000


class MediaSessionManager(ManagerBase):
    """Media keys and the system's media panel in the background.

    The player is the system's media player while it has videos, and lets
    the keys go to other players when it has none. A button pressed comes
    back as the media key it stands for and runs what the keymap binds
    that key to, as the key pressed in the window does.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._session = None
        self._state = None

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_MS)
        self._refresh_timer.timeout.connect(self.refresh)

    def init(self):
        self.set_enabled(Settings().get("player/media_keys_background"))

    def set_enabled(self, is_enabled):
        if is_enabled == (self._session is not None):
            return

        if not is_enabled:
            self.cleanup()
            return

        self._session = make_media_session(self)
        if self._session is None:
            return

        self._session.command.connect(self.run_media_key)

        raise_requested = getattr(self._session, "raise_requested", None)
        if raise_requested is not None:
            raise_requested.connect(self.raise_window)

        self._refresh_timer.start()
        self.refresh()

    def cleanup(self):
        self._refresh_timer.stop()

        if self._session is not None:
            self._session.close()
            self._session.deleteLater()
            self._session = None

        self._state = None

    def refresh(self, *_):
        if self._session is None:
            return

        state = self._media_state()
        if state == self._state:
            return

        self._state = state
        self._session.update(state)

    def run_media_key(self, key):
        action_id = self._action_for(key)
        if action_id is None or self._is_done_already(key, action_id):
            return

        self._log.debug(f"Media key {key}: {action_id}")

        self._ctx.actions_manager.trigger(action_id)

        # played or paused while away, minimized or in the tray, the videos
        # stay as left on return
        if self._ctx.commands.is_window_away():
            self._ctx.commands.forget_minimize_pause()

        self.refresh()

    def raise_window(self):
        # minimized or in the tray, it comes back as well
        self._ctx.commands.activate_window()

    def _action_for(self, key):
        actions = self._ctx.actions_manager

        action_id = actions.action_for_key(key)
        if action_id is not None:
            return action_id

        # Windows sends the play / pause key as Play or Pause, by what it
        # was told is playing, and headsets may send either: what the key
        # itself does, where they are not set
        if key in {KEY_PLAY, KEY_PAUSE}:
            return actions.action_for_key(KEY_PLAY_PAUSE)

        if key == KEY_PLAY_PAUSE:
            is_playing = bool(self._ctx.video_blocks.unpaused)
            return actions.action_for_key(KEY_PAUSE if is_playing else KEY_PLAY)

        return None

    def _is_done_already(self, key, action_id):
        """Play asked for while playing, or Pause while paused, of the
        play / pause action: the play / pause key comes as Play on most
        keyboards and so is bound to it, but a Play from the system is to
        play and a Pause to pause."""

        if key not in {KEY_PLAY, KEY_PAUSE}:
            return False

        if action_id != self._ctx.actions_manager.action_for_key(KEY_PLAY_PAUSE):
            return False

        is_playing = bool(self._ctx.video_blocks.unpaused)
        return is_playing == (key == KEY_PLAY)

    def _media_state(self) -> MediaState | None:
        video_blocks = self._ctx.video_blocks

        if not len(video_blocks):
            return None

        if video_blocks.unpaused:
            status = PlaybackStatus.PLAYING
        else:
            status = PlaybackStatus.PAUSED

        actions = self._ctx.actions_manager
        keys = frozenset(
            key
            for key in MEDIA_KEYS
            if (action_id := self._action_for(key)) is not None
            and actions.is_action_available(action_id)
        )

        return MediaState(status=status, title=self._title(), keys=keys)

    def _title(self) -> str:
        video_blocks = list(self._ctx.video_blocks)

        if self._ctx.is_single_mode:
            video_blocks = [vb for vb in video_blocks if vb.isVisible()]

        if len(video_blocks) == 1:
            vb = video_blocks[0]
            return vb.title or vb.video_params.uri_name

        playlist_path = self._ctx.commands.saved_playlist_path()
        if playlist_path is not None:
            return playlist_path.stem

        return translate("Media Keys", "Videos: {}").format(
            count_txt(len(video_blocks))
        )
