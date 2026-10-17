from contextlib import contextmanager

from pydantic import Field

from gridplayer.models.grid_state import GridState
from gridplayer.params.settings_bindings import (
    GRID_STATE_ATTR,
    PLAYLIST_ATTRS,
    VIDEO_DEFAULT_ATTRS,
)
from gridplayer.settings import Settings

_INSTANCE = None

SAVE_ALL_KEY = "playlist/save_all_settings"


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

    def is_keeping_all(self) -> bool:
        """Whether the playlist keeps every setting, not only its own."""

        return bool(self.get(SAVE_ALL_KEY))

    def kept(self) -> dict:
        """What a playlist saved now keeps: the values it has of its own,
        or every value, while it keeps all its settings."""

        if not self.is_keeping_all():
            return dict(self._overrides)

        return {key: self.get(key) for key in (*PLAYLIST_ATTRS, *VIDEO_DEFAULT_ATTRS)}

    def keep_all(self, live) -> None:
        """Every value the playlist's own, as it is now, the grid's as the
        grid is: what it saved, so that a change of a default reaches it no
        more than it reaches the file."""

        self._overrides = {
            **self.kept(),
            **grid_values_from_state(live),
            **self._overrides,
        }

    def playlist_kwargs(self) -> dict:
        return playlist_kwargs_from_overrides(self.kept())

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


def session_field(setting_name, validate=False):
    return Field(
        default_factory=lambda: PlaylistSettings().get(setting_name),
        validate_default=validate,
    )


def overrides_from_playlist(playlist) -> dict:
    result = {}
    for key, attr in PLAYLIST_ATTRS.items():
        value = getattr(playlist, attr)
        if value is not None:
            result[key] = value
    video = playlist.video_defaults
    for key, attr in VIDEO_DEFAULT_ATTRS.items():
        value = getattr(video, attr)
        if value is not None:
            result[key] = value
    return result


def playlist_kwargs_from_overrides(overrides: dict) -> dict:
    kwargs = {
        attr: overrides[key] for key, attr in PLAYLIST_ATTRS.items() if key in overrides
    }
    video_kwargs = {
        attr: overrides[key]
        for key, attr in VIDEO_DEFAULT_ATTRS.items()
        if key in overrides
    }
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
    """GridState for the playlist file dump.

    Only session-overridden grid attrs are explicit; inherited attrs are left
    to defaults so the fields_set-based dump omits them. ``cells`` and
    ``video_order`` are always explicit (they are not settings).
    """
    session = PlaylistSettings()
    is_all = session.is_keeping_all()
    explicit = {
        attr: getattr(live, attr)
        for key, attr in GRID_STATE_ATTR.items()
        if is_all or session.is_overridden(key)
    }
    return GridState(
        **explicit,
        cells=list(live.cells),
        video_order=list(live.video_order),
    )
