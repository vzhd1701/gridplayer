"""How the settings form fields are laid out and tied together."""

import pytest

from gridplayer.params.defaults_fields import (
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
