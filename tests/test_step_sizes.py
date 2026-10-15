"""How far a press seeks or zooms, set for the playlist rather than fixed.

Three seek steps, each the same forwards and back, and a zoom step that is
either a share of the whole picture or, zooming in proportion, a share of
what is on show.
"""

import math
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QLabel

from gridplayer.models.playlist import Playlist
from gridplayer.params.actions import ACTIONS
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    FloatSpinField,
    layout_sections,
)
from gridplayer.params.settings_fields.playlist import PLAYLIST_FIELDS
from gridplayer.params.settings_pages import PLAYLIST_PAGE
from gridplayer.params.static import MAX_SCALE, MIN_SCALE
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.playlist_settings import PlaylistSettings, overrides_from_playlist
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils.step_sizes import (
    seek_step_label,
    seek_step_ms,
    seek_step_txt,
    zoom_stepped,
)
from gridplayer.widgets.keymap_tree_view import _action_title
from gridplayer.widgets.settings_form import SettingsForm
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.video_block_view import ViewControl

STEP_KEYS = (
    "playlist/seek_step_short",
    "playlist/seek_step_medium",
    "playlist/seek_step_long",
    "playlist/zoom_step",
    "playlist/zoom_proportional",
)

SECTION_OF = layout_sections(PLAYLIST_PAGE)

# the actions that seek by a step: which step, and which way
SEEK_ACTIONS = {
    "+5s": ("short", 1),
    "+15s": ("medium", 1),
    "+30s": ("long", 1),
    "-5s": ("short", -1),
    "-15s": ("medium", -1),
    "-30s": ("long", -1),
}


@pytest.fixture(autouse=True)
def _settings_get(mocker):
    """Answer with the shipped defaults, never with this machine's settings."""

    mocker.patch.object(Settings(), "get", side_effect=_default_settings.__getitem__)


def _zoom(percent, is_proportional=False):
    PlaylistSettings().set("playlist/zoom_step", percent)
    PlaylistSettings().set("playlist/zoom_proportional", is_proportional)


def _pressed(scale, direction, times):
    scales = []

    for _ in range(times):
        scale = zoom_stepped(scale, direction)
        scales.append(scale)

    return scales


class TestTheDefaults:
    def test_they_are_what_was_fixed_before(self):
        assert [_default_settings[key] for key in STEP_KEYS] == [
            5.0,
            15.0,
            30.0,
            10,
            False,
        ]

    def test_they_are_kept_for_the_playlist(self):
        fields = {spec.settings_key: spec for spec in PLAYLIST_FIELDS}

        for key in STEP_KEYS:
            assert fields[key].attr == key.removeprefix("playlist/")

    def test_they_have_a_section_of_their_own(self):
        sections = {
            SECTION_OF[spec.settings_key]
            for spec in PLAYLIST_FIELDS
            if spec.settings_key in STEP_KEYS
        }

        assert sections == {"Step Sizes"}

    def test_the_section_comes_right_after_playback(self):
        sections = list(
            dict.fromkeys(SECTION_OF[spec.settings_key] for spec in PLAYLIST_FIELDS)
        )

        assert sections[sections.index("Playback") + 1] == "Step Sizes"

    def test_seek_steps_are_set_to_the_millisecond(self):
        fields = {spec.settings_key: spec for spec in PLAYLIST_FIELDS}

        for key in STEP_KEYS[:3]:
            assert isinstance(fields[key], FloatSpinField)
            assert fields[key].decimals == 3
            assert fields[key].minimum == 0.001

    def test_proportional_zoom_is_a_checkbox(self):
        fields = {spec.settings_key: spec for spec in PLAYLIST_FIELDS}

        assert isinstance(fields["playlist/zoom_proportional"], CheckboxField)


class TestTheForm:
    @pytest.fixture
    def form(self):
        form = SettingsForm(PLAYLIST_FIELDS)

        yield form

        form.deleteLater()

    def test_a_step_keeps_its_milliseconds(self, form):
        form.set_values({"playlist/seek_step_short": 1.001})

        assert form.values()["playlist/seek_step_short"] == 1.001

    def test_a_step_says_it_is_in_seconds(self, form):
        row = form._rows["playlist/seek_step_medium"]
        texts = [label.text() for label in row.findChildren(QLabel)]

        assert "(sec)" in texts


class TestThePlaylistFile:
    def test_steps_of_its_own_come_back_when_it_is_opened(self):
        playlist = Playlist(
            videos=[], seek_step_short=1.25, zoom_step=25, zoom_proportional=True
        )

        overrides = overrides_from_playlist(Playlist.parse(playlist.dumps()))

        assert overrides["playlist/seek_step_short"] == 1.25
        assert overrides["playlist/zoom_step"] == 25
        assert overrides["playlist/zoom_proportional"] is True

    def test_steps_left_as_they_are_are_not_written(self):
        txt = Playlist(videos=[]).dumps()

        for key in STEP_KEYS:
            assert key.removeprefix("playlist/") not in txt

    def test_the_session_saves_what_was_changed(self):
        PlaylistSettings().set("playlist/seek_step_long", 60.0)

        playlist = Playlist(videos=[], **PlaylistSettings().playlist_kwargs())

        assert playlist.seek_step_long == 60.0
        assert playlist.seek_step_short is None


class TestSeekSteps:
    def test_they_follow_the_settings(self):
        assert seek_step_ms("short") == 5000
        assert seek_step_ms("medium") == 15000
        assert seek_step_ms("long") == 30000

    def test_the_playlist_has_the_last_word(self):
        PlaylistSettings().set("playlist/seek_step_medium", 90.0)

        assert seek_step_ms("medium") == 90000
        assert seek_step_label("medium") == "1m 30s"

    @pytest.mark.parametrize(
        ("seconds", "step_ms"),
        [(0.001, 1), (0.04, 40), (1.001, 1001), (2.675, 2675), (3599.999, 3599999)],
    )
    def test_they_go_to_the_millisecond(self, seconds, step_ms):
        PlaylistSettings().set("playlist/seek_step_short", seconds)

        assert seek_step_ms("short") == step_ms

    @pytest.mark.parametrize(
        ("step_ms", "txt"),
        [
            (1000, "1s"),
            (5000, "5s"),
            (59000, "59s"),
            (60000, "1m"),
            (90000, "1m 30s"),
            (600000, "10m"),
            (3600000, "1h"),
            (3661000, "1h 1m 1s"),
            (0, "0s"),
        ],
    )
    def test_the_menu_names_them_in_the_largest_units(self, step_ms, txt):
        assert seek_step_txt(step_ms) == txt

    @pytest.mark.parametrize(
        ("step_ms", "txt"),
        [
            (1, "1ms"),
            (40, "40ms"),
            (999, "999ms"),
            (1500, "1.5s"),
            (1250, "1.25s"),
            (1001, "1.001s"),
            (10500, "10.5s"),
            (90250, "1m 30.25s"),
            (60001, "1m 0.001s"),
            (3600500, "1h 0.5s"),
        ],
    )
    def test_parts_of_a_second_show_as_far_as_they_go(self, step_ms, txt):
        assert seek_step_txt(step_ms) == txt

    def test_a_video_seeks_by_the_step(self):
        PlaylistSettings().set("playlist/seek_step_short", 0.25)

        block = Mock(spec=VideoBlock)
        block.is_video_initialized = True
        block.is_live = False

        VideoBlock.seek_step(block, "short", -1)

        block.seek_shift_ms.assert_called_once_with(-250)

    def test_every_video_seeks_by_the_step(self):
        PlaylistSettings().set("playlist/seek_step_long", 45.5)

        manager = Mock()
        VideoBlocksManager.cmd_seek_step(manager, "long", 1)

        manager.all_seek_shift_ms.emit.assert_called_once_with(45500)


class TestTheSeekActions:
    @pytest.mark.parametrize(("name", "step"), SEEK_ACTIONS.items())
    def test_one_seeks_the_active_video_by_its_step(self, name, step):
        action = ACTIONS[name]

        assert action["func"] == ("active", "manual_seek", "seek_step", *step)
        assert action["value_getter"] == ("seek_step_label", step[0])

    @pytest.mark.parametrize(("name", "step"), SEEK_ACTIONS.items())
    def test_one_for_all_seeks_every_video_by_its_step(self, name, step):
        action = ACTIONS[f"{name} [ALL]"]

        assert action["func"] == ("all_seek_step", *step)
        assert action["value_getter"] == ("seek_step_label", step[0])

    @pytest.mark.parametrize("name", SEEK_ACTIONS)
    def test_the_menu_puts_the_step_in_the_title(self, name):
        assert ACTIONS[name]["title"] == f"{name[0]}%v"

    @pytest.mark.parametrize("name", SEEK_ACTIONS)
    def test_the_shortcuts_list_names_them_by_what_they_do(self, name):
        title = _action_title(ACTIONS[name])

        assert "%v" not in title
        assert title == _action_title(ACTIONS[f"{name} [ALL]"])

    def test_the_manager_has_what_they_call(self):
        commands = VideoBlocksManager.commands.fget(Mock())

        assert "all_seek_step" in commands
        assert commands["seek_step_label"] is seek_step_label


class TestZoomStepsOfAShare:
    def test_by_default_they_go_as_they_did(self):
        _zoom(10)

        for tenths in range(10, 101):
            scale = tenths / 10

            assert zoom_stepped(scale, 1) == min(round(scale + 0.1, 1), MAX_SCALE)
            assert zoom_stepped(scale, -1) == max(round(scale - 0.1, 1), MIN_SCALE)

    def test_bigger_steps(self):
        _zoom(25)

        assert _pressed(1.0, 1, 4) == [1.25, 1.5, 1.75, 2.0]
        assert _pressed(2.0, -1, 4) == [1.75, 1.5, 1.25, 1.0]

    def test_off_the_steps_it_goes_from_the_nearest_one(self):
        _zoom(25)

        # zoomed to a selection
        assert zoom_stepped(2.37, 1) == 2.5
        assert zoom_stepped(2.37, -1) == 2.0

    def test_it_stops_at_either_end(self):
        _zoom(30)

        assert _pressed(9.0, 1, 2) == [9.3, 9.6]
        assert zoom_stepped(9.9, 1) == MAX_SCALE
        assert zoom_stepped(MAX_SCALE, 1) == MAX_SCALE
        assert zoom_stepped(1.2, -1) == MIN_SCALE
        assert zoom_stepped(MIN_SCALE, -1) == MIN_SCALE

    def test_out_from_the_most_there_is_lands_on_the_step_below_it(self):
        _zoom(30)

        assert zoom_stepped(9.9, 1) == MAX_SCALE
        assert zoom_stepped(MAX_SCALE, -1) == 9.9


class TestZoomStepsInProportion:
    def test_each_is_a_share_of_what_is_on_show(self):
        _zoom(10, is_proportional=True)

        assert _pressed(1.0, 1, 4) == [1.1, 1.21, 1.33, 1.46]

    def test_back_out_lands_on_the_whole_picture(self):
        _zoom(10, is_proportional=True)

        scale = _pressed(1.0, 1, 20)[-1]

        assert _pressed(scale, -1, 20)[-1] == 1.0

    def test_in_and_out_comes_back_where_it_was(self):
        _zoom(10, is_proportional=True)

        for scale in _pressed(1.0, 1, 24):
            assert zoom_stepped(zoom_stepped(scale, 1), -1) == scale

    def test_off_the_steps_it_goes_from_the_nearest_one(self):
        _zoom(10, is_proportional=True)

        # 2.37 is nearest 1.1 ** 9, 2.36
        assert zoom_stepped(2.37, 1) == round(1.1**10, 2)
        assert zoom_stepped(2.37, -1) == round(1.1**8, 2)

    def test_the_top_step_stops_at_the_most_there_is(self):
        _zoom(100, is_proportional=True)

        assert _pressed(1.0, 1, 5) == [2.0, 4.0, 8.0, MAX_SCALE, MAX_SCALE]

    def test_out_from_the_most_there_is_lands_on_the_step_below_it(self):
        _zoom(10, is_proportional=True)

        steps_below = math.floor(math.log(MAX_SCALE) / math.log(1.1))

        assert zoom_stepped(MAX_SCALE, -1) == round(1.1**steps_below, 2)

    @pytest.mark.parametrize("percent", [1, 2, 3])
    def test_the_smallest_steps_still_move_every_press(self, percent):
        _zoom(percent, is_proportional=True)

        scales = _pressed(1.0, 1, 2000)
        scales = scales[: scales.index(MAX_SCALE) + 1]

        assert all(b > a for a, b in zip([1.0, *scales], scales, strict=False))

        back = _pressed(MAX_SCALE, -1, 2000)
        back = back[: back.index(MIN_SCALE) + 1]

        assert all(b < a for a, b in zip([MAX_SCALE, *back], back, strict=False))


class TestTheBlock:
    def _block(self, scale):
        block = Mock(spec=VideoBlock)
        block.video_params = Mock(scale=scale)
        block.video_tracks = [0]
        block.is_video_initialized = True
        block.view = ViewControl(block)
        block.view._zoom_to = Mock()
        return block

    def test_zoom_in_goes_by_the_playlist_step(self):
        _zoom(50)
        block = self._block(1.0)

        block.view.scale_increase()

        block.view._zoom_to.assert_called_once_with(1.5)

    def test_zoom_out_goes_by_the_playlist_step(self):
        _zoom(20, is_proportional=True)
        block = self._block(1.44)

        block.view.scale_decrease()

        block.view._zoom_to.assert_called_once_with(1.2)
