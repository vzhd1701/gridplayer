from types import MappingProxyType

from gridplayer.params.settings_fields.advanced import ADVANCED_FIELDS
from gridplayer.params.settings_fields.general import GENERAL_FIELDS
from gridplayer.params.settings_fields.kinds import SettingField
from gridplayer.params.settings_fields.playlist import PLAYLIST_FIELDS
from gridplayer.params.settings_fields.streaming import (
    SPONSORBLOCK_FIELDS,
    STREAMING_FIELDS,
)
from gridplayer.params.settings_fields.subtitles import SUBTITLE_STYLE_FIELDS
from gridplayer.params.settings_fields.video import VIDEO_FIELDS

ALL_FIELDS: tuple[SettingField, ...] = (
    *GENERAL_FIELDS,
    *SUBTITLE_STYLE_FIELDS,
    *PLAYLIST_FIELDS,
    *VIDEO_FIELDS,
    *STREAMING_FIELDS,
    *SPONSORBLOCK_FIELDS,
    *ADVANCED_FIELDS,
)

# every setting the settings dialogs edit, by its key
FIELDS: MappingProxyType[str, SettingField] = MappingProxyType(
    {spec.settings_key: spec for spec in ALL_FIELDS}
)
