"""How the settings form fields are laid out and tied together."""

import pytest

from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist, PlaylistVideoDefaults
from gridplayer.params.defaults_fields import (
    GRID_STATE_ATTR,
    PLAYLIST_FIELDS,
    SUBTITLE_STYLE_FIELDS,
    VIDEO_FIELDS,
)

FIELD_LISTS = pytest.mark.parametrize(
    "fields",
    [PLAYLIST_FIELDS, VIDEO_FIELDS, SUBTITLE_STYLE_FIELDS],
    ids=["playlist", "video", "subtitle_style"],
)


@FIELD_LISTS
def test_each_section_is_shown_under_one_heading(fields):
    # the form starts a heading whenever the section changes, so a section
    # split in two would get two headings
    sections = [spec.section for spec in fields]
    in_order = [s for i, s in enumerate(sections) if i == 0 or s != sections[i - 1]]

    assert len(in_order) == len(set(in_order)), in_order


def test_a_playlist_keeps_each_field_where_the_field_says():
    for spec in PLAYLIST_FIELDS:
        if spec.grid_attr:
            assert spec.attr is None, spec.settings_key
            assert spec.grid_attr in GridState.model_fields, spec.settings_key
        else:
            assert spec.attr in Playlist.model_fields, spec.settings_key

    for spec in VIDEO_FIELDS:
        assert spec.grid_attr is None, spec.settings_key
        assert spec.attr in PlaylistVideoDefaults.model_fields, spec.settings_key


def test_the_grid_state_names_are_the_grid_fields():
    assert GRID_STATE_ATTR == {
        "playlist/grid_mode": "mode",
        "playlist/grid_fit": "is_fit",
        "playlist/grid_size": "size",
        "playlist/grid_rows": "rows",
        "playlist/grid_cols": "cols",
        "playlist/grid_preallocate": "preallocate",
    }
