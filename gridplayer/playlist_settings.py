from contextlib import contextmanager

from pydantic import Field

from gridplayer.models.grid_state import GridState
from gridplayer.params.defaults_fields import (
    GRID_STATE_ATTR,
    PLAYLIST_FIELDS,
    VIDEO_FIELDS,
)
from gridplayer.settings import Settings

_INSTANCE = None


class _PlaylistSettings:
    def __init__(self):
        self._overrides: dict = {}
        self._suppress = False

    def get(self, key: str):
        if key in self._overrides:
            return self._overrides[key]
        return Settings().get(key)

    def is_overridden(self, key: str) -> bool:
        return key in self._overrides

    def set(self, key: str, value) -> None:
        if self._suppress:
            return
        self._overrides[key] = value

    def reset(self, key: str) -> None:
        self._overrides.pop(key, None)

    def replace(self, overrides: dict) -> None:
        self._overrides = dict(overrides)

    def clear(self) -> None:
        self._overrides = {}

    def as_dict(self) -> dict:
        return dict(self._overrides)

    @contextmanager
    def suppress_capture(self):
        prev = self._suppress
        self._suppress = True
        try:
            yield
        finally:
            self._suppress = prev

    def playlist_kwargs(self) -> dict:
        return playlist_kwargs_from_overrides(self._overrides)

    def applied_grid_state(self, live):
        """Live values for overridden grid keys, Settings for the rest."""
        update = {}
        for key, attr in GRID_STATE_ATTR.items():
            if self.is_overridden(key):
                update[attr] = getattr(live, attr)
            else:
                update[attr] = Settings().get(key)
        return live.model_copy(update=update)


def PlaylistSettings() -> _PlaylistSettings:
    global _INSTANCE

    if _INSTANCE is None:
        _INSTANCE = _PlaylistSettings()

    return _INSTANCE


def session_field(setting_name):
    return Field(default_factory=lambda: PlaylistSettings().get(setting_name))


def overrides_from_playlist(playlist) -> dict:
    result = {}
    for spec in PLAYLIST_FIELDS:
        if spec.is_grid or spec.playlist_attr is None:
            continue
        value = getattr(playlist, spec.playlist_attr)
        if value is not None:
            result[spec.settings_key] = value
    video = playlist.video_defaults
    for spec in VIDEO_FIELDS:
        if spec.video_attr is None:
            continue
        value = getattr(video, spec.video_attr)
        if value is not None:
            result[spec.settings_key] = value
    return result


def playlist_kwargs_from_overrides(overrides: dict) -> dict:
    kwargs = {}
    video_kwargs = {}
    for spec in PLAYLIST_FIELDS:
        if spec.is_grid or spec.playlist_attr is None:
            continue
        if spec.settings_key in overrides:
            kwargs[spec.playlist_attr] = overrides[spec.settings_key]
    for spec in VIDEO_FIELDS:
        if spec.video_attr is None:
            continue
        if spec.settings_key in overrides:
            video_kwargs[spec.video_attr] = overrides[spec.settings_key]
    if video_kwargs:
        # Plain dict: Playlist coerces it into PlaylistVideoDefaults, which
        # keeps this module importable without models.playlist (import cycle).
        kwargs["video_defaults"] = video_kwargs
    return kwargs


def grid_values_from_state(grid_state) -> dict:
    return {key: getattr(grid_state, attr) for key, attr in GRID_STATE_ATTR.items()}


def grid_defaults() -> dict:
    return {key: Settings().get(key) for key in GRID_STATE_ATTR}


def grid_overrides_from_state(grid_state) -> dict:
    """Keys the file actually stored, even when they match today's Settings."""
    live = grid_values_from_state(grid_state)
    explicit = grid_state.model_fields_set
    return {key: live[key] for key, attr in GRID_STATE_ATTR.items() if attr in explicit}


def grid_state_for_dump(live) -> GridState:
    """GridState for the #P: dump.

    Only session-overridden grid attrs are explicit; inherited attrs are left
    to defaults so the fields_set-based dump omits them. ``cells`` and
    ``video_order`` are always explicit (they are not settings).
    """
    session = PlaylistSettings()
    explicit = {
        attr: getattr(live, attr)
        for key, attr in GRID_STATE_ATTR.items()
        if session.is_overridden(key)
    }
    return GridState(
        **explicit,
        cells=list(live.cells),
        video_order=list(live.video_order),
    )
