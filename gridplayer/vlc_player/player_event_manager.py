import logging
from functools import partial
from typing import Callable, Dict, List

from gridplayer.vlc_player.libvlc import vlc


class EventManager(object):
    player_events = {
        "buffering": vlc.EventType.MediaPlayerBuffering,
        "encountered_error": vlc.EventType.MediaPlayerEncounteredError,
        "end_reached": vlc.EventType.MediaPlayerEndReached,
        "paused": vlc.EventType.MediaPlayerPaused,
        "snapshot_taken": vlc.EventType.MediaPlayerSnapshotTaken,
        "stopped": vlc.EventType.MediaPlayerStopped,
        "playing": vlc.EventType.MediaPlayerPlaying,
        "time_changed": vlc.EventType.MediaPlayerTimeChanged,
        "vout": vlc.EventType.MediaPlayerVout,
    }

    media_events = {
        "media_parsed_changed": vlc.EventType.MediaParsedChanged,
    }

    def __init__(self):
        self._log = logging.getLogger(self.__class__.__name__)

        self._subscriptions: Dict[str, List[Callable]] = {
            event: [] for event in self.event_types
        }

    @property
    def event_types(self):
        return {*self.player_events, *self.media_events}

    def attach_to_media_player(self, media_player):
        for event_name, event_type in self.player_events.items():
            media_player.event_manager().event_attach(
                event_type, partial(self._notify_subscribers, event_name)
            )

    def attach_to_media(self, media):
        for event_name, event_type in self.media_events.items():
            media.event_manager().event_attach(
                event_type, partial(self._notify_subscribers, event_name)
            )

    def subscribe(self, event_name, callback):
        if event_name not in self.event_types:
            raise ValueError(f"Unknown event name: {event_name}")

        self._subscriptions[event_name].append(callback)

    def _notify_subscribers(self, event_name, event):
        for callback in self._subscriptions[event_name]:
            callback(event)
