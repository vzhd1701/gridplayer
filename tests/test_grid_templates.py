"""Templates of one's own: a Fixed Grid saved under a name, its size and its
big cells, listed with the built-in ones and put back from the menu."""

from types import SimpleNamespace

import pytest
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QWidget

from gridplayer.dialogs.input_dialog import QCustomTextInput
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.grid_templates import OwnGridTemplate, OwnGridTemplates
from gridplayer.params.static import GRID_TEMPLATES, GridMode, GridTemplate
from gridplayer.player.managers.grid import GridManager
from gridplayer.player.managers.grid_templates import SETTING, GridTemplatesManager
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils.layout import GridLayout
from gridplayer.widgets.grid_template_icon import grid_template_icon, template_shapes


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def stored(mocker):
    """The settings as the shipped defaults, the templates kept here."""

    stored = {}

    def get(key):
        return stored.get(key, _default_settings[key])

    settings = Settings()
    mocker.patch.object(settings, "get", side_effect=get)
    mocker.patch.object(settings, "set", side_effect=stored.__setitem__)
    mocker.patch.object(
        settings, "reset", side_effect=lambda key: stored.pop(key, None)
    )

    return stored


class _Blocks:
    def __init__(self, ids):
        self.video_ids = list(ids)

    def __bool__(self):
        return bool(self.video_ids)

    def __iter__(self):
        return iter(())

    def blocks_for_ids(self, _video_ids):
        return []


@pytest.fixture
def managers():
    parent = QWidget()
    commands = SimpleNamespace(
        remove_video_blocks=lambda *_a, **_k: None, remember_closed=lambda *_a: None
    )
    ids = list("ABCDEFGHI")
    ctx = SimpleNamespace(
        video_blocks=_Blocks(ids),
        is_shuffle_on_load=False,
        is_single_mode=False,
        commands=commands,
    )
    grid = GridManager(context=ctx, parent=parent)
    grid._flow.ids = ids
    templates = GridTemplatesManager(context=ctx, parent=parent)
    for manager in (grid, templates):
        for name, command in manager.commands.items():
            setattr(commands, name, command)

    return SimpleNamespace(grid=grid, templates=templates, parent=parent)


def _fixed(grid, rows, cols, spans=()):
    grid._mode = GridMode.FIXED
    grid._grid_layout = GridLayout(max_rows=rows, max_cols=cols)
    # as many as there is room for, the big cells made
    room = rows * cols - sum(r * c - 1 for _, r, c in spans)
    grid._grid_layout.pack_flow(list("ABCDEFGHI")[:room])
    for video_id, rowspan, colspan in spans:
        assert grid._grid_layout.set_span(video_id, rowspan, colspan)


def _name_typed(mocker, name):
    return mocker.patch.object(QCustomTextInput, "get_name", return_value=name)


def _own(stored):
    return list(stored.get(SETTING, OwnGridTemplates()))


class TestFits:
    @pytest.mark.parametrize("name", list(GRID_TEMPLATES))
    def test_the_built_in_ones(self, name):
        assert GRID_TEMPLATES[name].fits()

    @pytest.mark.parametrize(
        "template",
        [
            GridTemplate(0, 3, ()),
            GridTemplate(3, 101, ()),
            GridTemplate(3, 3, ((2, 2, 2, 2),)),
            GridTemplate(3, 3, ((-1, 0, 2, 2),)),
            GridTemplate(3, 3, ((0, 0, 0, 1),)),
            GridTemplate(4, 4, ((0, 0, 2, 2), (1, 1, 2, 2))),
        ],
        ids=["no columns", "too many rows", "out", "before", "no span", "overlap"],
    )
    def test_not_one_there_can_be(self, template):
        assert not template.fits()


class TestOwnGridTemplates:
    def test_kept_in_the_settings_as_written(self):
        templates = OwnGridTemplates().added(
            OwnGridTemplate(name="Stage", cols=4, rows=3, big=((0, 1, 2, 2),))
        )

        again = OwnGridTemplates.model_validate_json(templates.model_dump_json())

        assert again == templates
        assert again[0].template == GridTemplate(4, 3, ((0, 1, 2, 2),))

    def test_one_of_a_name_there_is_takes_its_place(self):
        templates = (
            OwnGridTemplates()
            .added(OwnGridTemplate(name="A", cols=2, rows=2))
            .added(OwnGridTemplate(name="B", cols=3, rows=3))
            .added(OwnGridTemplate(name="A", cols=4, rows=4))
        )

        assert [(t.name, t.cols) for t in templates] == [("A", 4), ("B", 3)]

    def test_removed(self):
        templates = (
            OwnGridTemplates()
            .added(OwnGridTemplate(name="A", cols=2, rows=2))
            .added(OwnGridTemplate(name="B", cols=3, rows=3))
        )

        assert [t.name for t in templates.removed(0)] == ["B"]


class TestTheGridAsATemplate:
    def test_none_but_a_fixed_grid(self, managers):
        assert managers.grid.grid_template_now() is None

    def test_a_template_made_is_that_template(self, managers, mocker):
        mocker.patch.object(managers.grid, "_confirm_overflow", return_value=True)

        managers.grid.cmd_set_grid_template("2 + 8")

        assert managers.grid.grid_template_now() == GRID_TEMPLATES["2 + 8"]

    def test_big_cells_row_by_row(self, managers):
        _fixed(managers.grid, 4, 4, [("D", 2, 1), ("A", 2, 2)])

        assert managers.grid.grid_template_now().big == (
            (0, 0, 2, 2),
            (0, 3, 2, 1),
        )


class TestSave:
    def test_saved_under_the_name_typed(self, managers, stored, mocker):
        _fixed(managers.grid, 3, 4, [("B", 2, 2)])
        _name_typed(mocker, "Stage")

        assert managers.templates.can_save()
        managers.templates.cmd_save()

        assert _own(stored) == [
            OwnGridTemplate(name="Stage", cols=4, rows=3, big=((0, 1, 2, 2),))
        ]
        assert managers.templates.is_own(0)
        assert not managers.templates.is_grid_fixed_custom()
        assert not managers.templates.can_save()

    def test_cancelled_saves_nothing(self, managers, stored, mocker):
        _fixed(managers.grid, 3, 4)
        _name_typed(mocker, None)

        managers.templates.cmd_save()

        assert SETTING not in stored

    def test_not_but_a_fixed_grid(self, managers, mocker):
        asked = _name_typed(mocker, "Stage")

        assert not managers.templates.can_save()
        managers.templates.cmd_save()

        asked.assert_not_called()

    def test_not_a_built_in_one(self, managers, mocker):
        mocker.patch.object(managers.grid, "_confirm_overflow", return_value=True)
        managers.grid.cmd_set_grid_template("1 + 5")

        assert not managers.templates.can_save()
        assert not managers.templates.is_grid_fixed_custom()

    @pytest.mark.parametrize(
        ("rows", "cols", "spans", "name"),
        [
            (3, 4, [("B", 2, 2)], "1 + 8"),
            (3, 3, [("E", 2, 2)], "1 + 5 (2)"),
            (2, 3, [], "3x2"),
        ],
        ids=["big cells", "a built-in name", "no big cells"],
    )
    def test_named_as_the_built_in_ones_are(
        self, managers, mocker, rows, cols, spans, name
    ):
        _fixed(managers.grid, rows, cols, spans)
        asked = _name_typed(mocker, None)

        managers.templates.cmd_save()

        assert asked.call_args.kwargs["initial_value"] == name

    def test_a_name_there_is_replaced_once_asked(self, managers, stored, mocker):
        _fixed(managers.grid, 2, 2)
        _name_typed(mocker, "Wall")
        managers.templates.cmd_save()
        _fixed(managers.grid, 3, 3)
        replace = mocker.patch.object(QCustomMessageBox, "confirm", return_value=True)

        managers.templates.cmd_save()

        replace.assert_called_once()
        assert [(t.name, t.cols) for t in _own(stored)] == [("Wall", 3)]

    def test_a_name_there_is_kept_when_not_replaced(self, managers, stored, mocker):
        _fixed(managers.grid, 2, 2)
        _name_typed(mocker, "Wall")
        managers.templates.cmd_save()
        _fixed(managers.grid, 3, 3)
        mocker.patch.object(QCustomMessageBox, "confirm", return_value=False)

        managers.templates.cmd_save()

        assert [(t.name, t.cols) for t in _own(stored)] == [("Wall", 2)]

    def test_numbered_after_one_of_ones_own(self, managers, stored, mocker):
        _fixed(managers.grid, 2, 3)
        _name_typed(mocker, "3x2")
        managers.templates.cmd_save()
        asked = _name_typed(mocker, None)

        managers.templates.cmd_save()

        assert asked.call_args.kwargs["initial_value"] == "3x2 (2)"


class TestPutBack:
    def test_from_an_auto_grid(self, managers, stored, mocker):
        stored[SETTING] = OwnGridTemplates().added(
            OwnGridTemplate(name="Stage", cols=4, rows=3, big=((0, 1, 2, 2),))
        )
        mocker.patch.object(managers.grid, "_confirm_overflow", return_value=True)

        managers.templates.cmd_set_own(0)

        assert managers.grid._mode is GridMode.FIXED
        assert managers.grid._grid_layout.id_at(0, 1) == "A"
        assert managers.grid.grid_template_now() == GridTemplate(4, 3, ((0, 1, 2, 2),))
        assert managers.templates.is_own(0)

    def test_listed_ticked_with_its_icon(self, managers, stored):
        stored[SETTING] = OwnGridTemplates().added(
            OwnGridTemplate(name="Stage", cols=4, rows=3, big=((0, 1, 2, 2),))
        )

        (item,) = managers.templates.menu_generator_own()

        assert item["title"] == "Stage"
        assert item["func"] == ("set_own_grid_template", 0)
        assert item["check_if"] == ("is_own_grid_template", 0)
        assert item["is_choice"]
        assert not item["icon"].isNull()

    def test_one_there_cannot_be_is_left_out(self, managers, stored):
        stored[SETTING] = (
            OwnGridTemplates()
            .added(OwnGridTemplate(name="Out", cols=2, rows=2, big=((1, 1, 2, 2),)))
            .added(OwnGridTemplate(name="Stage", cols=4, rows=3))
        )

        titles = [i["title"] for i in managers.templates.menu_generator_own()]
        funcs = [i["func"] for i in managers.templates.menu_generator_delete()]

        assert titles == ["Stage"]
        assert funcs == [("delete_grid_template", 1)]

    def test_none_of_ones_own_leaves_the_lists_empty(self, managers):
        assert managers.templates.menu_generator_own() == []
        assert managers.templates.menu_generator_delete() == []


class TestDelete:
    @pytest.fixture(autouse=True)
    def two(self, stored):
        stored[SETTING] = (
            OwnGridTemplates()
            .added(OwnGridTemplate(name="A", cols=2, rows=2))
            .added(OwnGridTemplate(name="B", cols=3, rows=3))
        )

    def test_once_asked(self, managers, stored, mocker):
        mocker.patch.object(QCustomMessageBox, "confirm", return_value=True)

        managers.templates.cmd_delete(0)

        assert [t.name for t in _own(stored)] == ["B"]

    def test_kept_when_not(self, managers, stored, mocker):
        mocker.patch.object(QCustomMessageBox, "confirm", return_value=False)

        managers.templates.cmd_delete(0)

        assert [t.name for t in _own(stored)] == ["A", "B"]

    def test_all_once_asked(self, managers, stored, mocker):
        asked = mocker.patch.object(QCustomMessageBox, "confirm", return_value=True)

        managers.templates.cmd_delete_all()

        assert "2" in asked.call_args.args[2]
        assert SETTING not in stored

    def test_all_kept_when_not(self, managers, stored, mocker):
        mocker.patch.object(QCustomMessageBox, "confirm", return_value=False)

        managers.templates.cmd_delete_all()

        assert [t.name for t in _own(stored)] == ["A", "B"]

    def test_delete_all_after_them_in_the_menu(self, managers):
        items = managers.templates.menu_generator_delete()

        assert [i if i == "---" else i["func"] for i in items] == [
            ("delete_grid_template", 0),
            ("delete_grid_template", 1),
            "---",
            "delete_all_grid_templates",
        ]

    def test_no_delete_all_for_one(self, managers, stored):
        stored[SETTING] = stored[SETTING].removed(1)

        items = managers.templates.menu_generator_delete()

        assert [i["func"] for i in items] == [("delete_grid_template", 0)]

    def test_the_last_leaves_the_setting_at_its_default(self, managers, stored, mocker):
        mocker.patch.object(QCustomMessageBox, "confirm", return_value=True)

        managers.templates.cmd_delete(1)
        managers.templates.cmd_delete(0)

        assert SETTING not in stored


class TestChooseSize:
    def test_ticked_for_a_fixed_grid_of_no_template(self, managers, mocker):
        assert not managers.templates.is_grid_fixed_custom()

        _fixed(managers.grid, 3, 4)
        assert managers.templates.is_grid_fixed_custom()

        mocker.patch.object(managers.grid, "_confirm_overflow", return_value=True)
        managers.grid.cmd_set_grid_template("1 + 3")
        assert not managers.templates.is_grid_fixed_custom()


class TestIcon:
    def test_drawn_where_the_built_in_one_has_its_cells(self):
        # resources/icons/custom/grid template 1-5.svg, 19 in from its edge
        shapes = template_shapes(GRID_TEMPLATES["1 + 5"])

        cells = [
            (r.x() - 19, r.y() - 19, r.width(), r.height(), big) for r, big in shapes
        ]

        assert cells == [
            (0, 0, 362.5, 362.5, True),
            (400, 0, 162.5, 162.5, False),
            (400, 200, 162.5, 162.5, False),
            (0, 400, 162.5, 162.5, False),
            (200, 400, 162.5, 162.5, False),
            (400, 400, 162.5, 162.5, False),
        ]

    def test_a_wide_one_in_the_middle(self):
        # grid template 1-2.svg
        big, *_ = template_shapes(GRID_TEMPLATES["1 + 2"])

        assert (big[0].y() - 19, big[0].height()) == (100, 362.5)

    def test_a_big_grid_keeps_gaps_between_its_cells(self):
        shapes = template_shapes(GridTemplate(10, 10, ()))

        first, second = shapes[0][0], shapes[1][0]

        assert second.x() - first.right() > 10

    def test_painted(self):
        image = grid_template_icon(GRID_TEMPLATES["2 + 8"]).pixmap(32).toImage()
        disabled = (
            grid_template_icon(GRID_TEMPLATES["2 + 8"])
            .pixmap(32, QIcon.Disabled)
            .toImage()
        )

        painted = [image.pixelColor(x, y).alpha() for x in range(32) for y in range(32)]
        assert max(painted) == 255
        assert painted.count(0) > 100
        assert disabled != image
