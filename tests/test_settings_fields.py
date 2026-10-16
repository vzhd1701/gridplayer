"""What each setting is (settings_fields) and where it is shown
(settings_pages), and that the two agree with each other and with the
defaults in gridplayer.settings."""

import pytest

from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist, PlaylistVideoDefaults
from gridplayer.models.settings_draft import SettingsMode
from gridplayer.params.settings_bindings import (
    GRID_STATE_ATTR,
    PLAYLIST_ATTRS,
    VIDEO_DEFAULT_ATTRS,
)
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    FloatSpinField,
    Slot,
    SpinField,
    TextField,
    _Node,
)
from gridplayer.params.settings_fields.playlist import PLAYLIST_FIELDS
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

INTERNAL_SETTINGS = {
    "last_playlist",
    "player/tray_note_shown",
    "recent_list_videos",
    "recent_list_playlists",
}

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


def test_fields_cover_every_editable_default():
    assert set(FIELDS) == set(_default_settings) - INTERNAL_SETTINGS


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
def test_the_shared_pages_show_exactly_their_fields(fields, page):
    """Both dialogs use the shared pages, which alone own display order."""

    assert sorted(layout_keys(page)) == sorted(spec.settings_key for spec in fields)


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
        mode=SettingsMode.DEFAULTS,
        slots={name: lambda: None for name in _slots(page.items)},
    )
    form.set_values({key: default_value(key) for key in form.keys()})

    assert [key for key in form.keys() if form.is_modified(key)] == []


def test_bindings_cover_the_shared_fields_and_target_model_attributes():
    assert not set(PLAYLIST_ATTRS) & set(GRID_STATE_ATTR)
    assert set(PLAYLIST_ATTRS) | set(GRID_STATE_ATTR) == {
        spec.settings_key for spec in PLAYLIST_FIELDS
    }
    assert set(VIDEO_DEFAULT_ATTRS) == {spec.settings_key for spec in VIDEO_FIELDS}

    for bindings, model in (
        (PLAYLIST_ATTRS, Playlist),
        (VIDEO_DEFAULT_ATTRS, PlaylistVideoDefaults),
        (GRID_STATE_ATTR, GridState),
    ):
        assert set(bindings.values()) <= set(model.model_fields)


def test_the_grid_state_names_are_the_grid_fields():
    assert GRID_STATE_ATTR == {
        "playlist/grid_mode": "mode",
        "playlist/grid_fit": "is_fit",
        "playlist/grid_size": "size",
        "playlist/grid_rows": "rows",
        "playlist/grid_cols": "cols",
        "playlist/grid_preallocate": "preallocate",
    }
