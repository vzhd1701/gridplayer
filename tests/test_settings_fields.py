"""What each setting is (settings_fields) and where it is shown
(settings_pages), and that the two agree with each other and with the
defaults in gridplayer.settings."""

import pytest

from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist, PlaylistVideoDefaults
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    FloatSpinField,
    Slot,
    SpinField,
    TextField,
    _Node,
)
from gridplayer.params.settings_fields.playlist import GRID_STATE_ATTR, PLAYLIST_FIELDS
from gridplayer.params.settings_fields.registry import ALL_FIELDS, FIELDS
from gridplayer.params.settings_fields.subtitles import SUBTITLE_STYLE_FIELDS
from gridplayer.params.settings_fields.video import VIDEO_FIELDS
from gridplayer.params.settings_pages import (
    PAGES,
    PLAYLIST_PAGE,
    SUBTITLE_STYLE_PAGE,
    VIDEO_PAGE,
)
from gridplayer.settings import _default_settings, default_value
from gridplayer.widgets.settings_form import SettingsForm
from tests.settings_layout import layout_keys

ALL_PAGES = [page for group in PAGES for page in group.pages]

SHARED_PAGES = pytest.mark.parametrize(
    ("fields", "page"),
    [
        (PLAYLIST_FIELDS, PLAYLIST_PAGE),
        (VIDEO_FIELDS, VIDEO_PAGE),
        (SUBTITLE_STYLE_FIELDS, SUBTITLE_STYLE_PAGE),
    ],
    ids=["playlist", "video", "subtitle_style"],
)

EVERY_PAGE = pytest.mark.parametrize("page", ALL_PAGES, ids=lambda p: p.id)


def _slots(items):
    for item in items:
        if isinstance(item, Slot):
            yield item.name
        elif isinstance(item, _Node):
            yield from _slots(item.items)


def test_no_setting_is_defined_twice():
    keys = [spec.settings_key for spec in ALL_FIELDS]

    assert len(keys) == len(set(keys))


def test_every_setting_is_shown_once():
    shown = [key for page in ALL_PAGES for key in layout_keys(page.items)]

    assert sorted(shown) == sorted(FIELDS)


def test_every_setting_has_a_default():
    assert set(FIELDS) <= set(_default_settings)


def test_every_page_has_an_id_of_its_own():
    ids = [page.id for page in ALL_PAGES]

    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    ("kind", "of_type"),
    [(CheckboxField, bool), (SpinField, int), (FloatSpinField, float)],
)
def test_a_field_edits_what_its_default_is(kind, of_type):
    # Settings.set refuses a value of another type than its default
    for spec in ALL_FIELDS:
        if type(spec) is kind:
            assert type(_default_settings[spec.settings_key]) is of_type, spec


def test_a_text_field_holds_text():
    for spec in ALL_FIELDS:
        if isinstance(spec, TextField):
            assert isinstance(_default_settings[spec.settings_key], str), spec


@SHARED_PAGES
def test_the_shared_pages_show_their_fields_in_order(fields, page):
    """The Playlist Settings dialog goes by the tuple, the Settings dialog
    by the page; they show the same thing."""

    assert list(layout_keys(page)) == [spec.settings_key for spec in fields]


@EVERY_PAGE
def test_what_enables_or_shows_a_field_is_on_its_page(page):
    # a form leaves a field alone when what it names isn't there
    keys = set(layout_keys(page.items))

    for key in keys:
        spec = FIELDS[key]
        for rule in (spec.enabled_when, spec.shown_when):
            if rule is not None:
                assert rule.key in keys, key
                assert rule.values, key


@EVERY_PAGE
def test_every_slot_is_one_the_dialog_fills(page):
    from gridplayer.dialogs.settings import SettingsDialog

    for name in _slots(page.items):
        assert hasattr(SettingsDialog, f"_slot_{name}"), name


@EVERY_PAGE
def test_out_of_the_box_nothing_is_marked_changed(page):
    """Every default is one its editor can show, as itself."""

    form = SettingsForm(
        page.items,
        reset_to=default_value,
        track_edits=False,
        slots={name: lambda: None for name in _slots(page.items)},
    )
    form.set_values({key: default_value(key) for key in form.keys()})

    assert [key for key in form.keys() if form.is_modified(key)] == []


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
