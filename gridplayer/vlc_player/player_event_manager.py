import inspect
import logging
from collections.abc import Callable
from functools import partial

from gridplayer.vlc_player.libvlc import vlc


class EventManager:
    player_events = {
        "buffering": vlc.EventType.MediaPlayerBuffering,
        "encountered_error": vlc.EventType.MediaPlayerEncounteredError,
        "end_reached": vlc.EventType.MediaPlayerEndReached,
        "opening": vlc.EventType.MediaPlayerOpening,
        "paused": vlc.EventType.MediaPlayerPaused,
        "snapshot_taken": vlc.EventType.MediaPlayerSnapshotTaken,
        "stopped": vlc.EventType.MediaPlayerStopped,
        "playing": vlc.EventType.MediaPlayerPlaying,
        "time_changed": vlc.EventType.MediaPlayerTimeChanged,
        "title_changed": vlc.EventType.MediaPlayerTitleChanged,
        "vout": vlc.EventType.MediaPlayerVout,
    }

    media_events = {
        "media_parsed_changed": vlc.EventType.MediaParsedChanged,
    }

    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)

        self._subscriptions: dict[str, list[Callable]] = {
            event: [] for event in self.event_types
        }

        # what event_manager() was asked of, to be forgotten; see forget()
        self._attached = []

    @property
    def event_types(self):
        return {*self.player_events, *self.media_events}

    def attach_to_media_player(self, media_player):
        self._attached.append(media_player)

        for event_name, event_type in self.player_events.items():
            media_player.event_manager().event_attach(
                event_type, partial(self._notify_subscribers, event_name)
            )

    def attach_to_media(self, media):
        self._attached.append(media)

        for event_name, event_type in self.media_events.items():
            media.event_manager().event_attach(
                event_type, partial(self._notify_subscribers, event_name)
            )

    def forget(self):
        """Let go of what was attached to, once libVLC has released it.

        vlc.py keeps the event manager of every object it was asked for in a
        dict of the object's class, for good: with it the object, every
        callback attached and, through them, the player and all it holds.
        """

        for vlc_object in self._attached:
            cached = inspect.getattr_static(type(vlc_object), "event_manager")
            cached._cache.pop(vlc_object, None)

        self._attached.clear()

    def subscribe(self, event_name, callback):
        if event_name not in self.event_types:
            raise ValueError(f"Unknown event name: {event_name}")

        self._subscriptions[event_name].append(callback)

    def _notify_subscribers(self, event_name, event):
        for callback in self._subscriptions[event_name]:
            callback(event)
