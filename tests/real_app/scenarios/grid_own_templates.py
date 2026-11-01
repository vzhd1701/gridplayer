"""Fixed Grid is a menu: Choose Size… first, the templates after it, then
those of one's own. A Fixed Grid with a big cell, saved as a template under
a name, is listed there, ticked while the grid is it, and made again from
an Auto grid; deleted, it is gone from the menu and the settings. Delete
All, there with more than one, deletes them all."""

from gridplayer.models.grid_templates import OwnGridTemplate, OwnGridTemplates
from gridplayer.params.menu import SECTIONS
from gridplayer.params.static import GridMode, GridTemplate
from gridplayer.settings import Settings

WIDTH, HEIGHT = 800, 600
STAGE = GridTemplate(4, 3, ((0, 0, 2, 2),))


def _submenu(items, name):
    for item in items:
        if isinstance(item, tuple):
            if item[0] == name:
                return item
            found = _submenu(item[1:], name)
            if found is not None:
                return found
    return None


def _shot_menu(d, name, shot):
    """The menu as it opens, its items made by the player's MenuManager."""

    from PyQt5.QtCore import QPoint

    from gridplayer.widgets.custom_menu import CustomMenu

    holder = CustomMenu(parent=d.player)
    d.player._managers_inst["menu"]._add_submenu(
        _submenu(SECTIONS["playlist"], name), holder
    )
    menu = holder.actions()[0].menu()
    menu.popup(d.player.mapToGlobal(QPoint(20, 20)))
    d.pump(0.3)
    d.shot(shot, menu)
    titles = [a.text() for a in menu.actions() if not a.isSeparator()]
    checked = [a.text() for a in menu.actions() if a.isChecked()]
    menu.close()
    holder.deleteLater()
    d.pump(0.1)
    return titles, checked


def _press(role):
    def press(box):
        from PyQt5.QtWidgets import QMessageBox

        next(
            b for b in box.buttons() if box.buttonRole(b) == getattr(QMessageBox, role)
        ).click()

    return press


def scenario(d):
    d.player.resize(WIDTH, HEIGHT)
    d.pump(0.3)

    folder = d.media.folder
    d.open(
        folder / "a.mp4",
        folder / "b.mp4",
        folder / "c.mp4",
        d.media.shapes / "square.mp4",
    )
    d.wait_until(lambda: len(d.cells) == 4, "four cells")
    d.wait_until(lambda: all(c.is_playable for c in d.cells), "all playing")
    first = d.cells[0]
    commands = d.ctx.commands
    actions = d.ctx.actions

    titles, checked = _shot_menu(d, "Grid", "1_grid_menu_auto")
    d.check("Fixed Grid not ticked in an Auto grid", "Fixed Grid" not in checked)

    def size(dialog):
        dialog.rows.setValue(3)
        dialog.cols.setValue(4)
        dialog.accept()

    d.through_modal(lambda: d.act(first, "Fixed Grid"), "2_choose_size", size)
    d.pump(0.3)
    d.check("a Fixed Grid", d.ctx.grid_state.mode == GridMode.FIXED)
    d.check("Choose Size… ticked", actions["Fixed Grid"].check_if())

    d.act(first, "Make Cell Bigger")
    d.pump(0.3)
    d.check("the first cell big", commands.grid_template_now() == STAGE)
    d.check("still none of the templates", actions["Fixed Grid"].check_if())
    d.check("can be saved", actions["Save Grid Template"].is_enabled)

    def name_it(dialog):
        d.check("named as the built-in ones", dialog.line_edit.text() == "1 + 8")
        dialog.line_edit.setText("Stage")
        dialog.accept()

    d.through_modal(lambda: d.act(first, "Save Grid Template"), "3_name", name_it)
    d.pump(0.3)

    saved = list(Settings().get("player/grid_templates"))
    d.check(
        "saved in the settings",
        [(t.name, t.template) for t in saved] == [("Stage", STAGE)],
        saved,
    )
    d.check(
        "listed after the templates",
        d.menu(first, "menu_generator_own_grid_templates") == ["Stage"],
    )
    d.check("Choose Size… not ticked now", not actions["Fixed Grid"].check_if())
    d.check("nothing to save now", not actions["Save Grid Template"].is_enabled)

    titles, checked = _shot_menu(d, "Fixed Grid", "4_fixed_grid_menu")
    d.check(
        "the Fixed Grid menu",
        titles[:2] == ["Choose Size…", "1 + 2"]
        and titles[-3:] == ["Stage", "Save as Template…", "Delete Template"],
        titles,
    )
    d.check("Stage ticked", checked == ["Stage"], checked)
    titles, checked = _shot_menu(d, "Grid", "5_grid_menu_fixed")
    d.check("Fixed Grid ticked in the Grid menu", "Fixed Grid" in checked, checked)

    # the grid had empty cells: asked whether to drop them
    d.through_modal(
        lambda: d.act(first, "Rows First"), "6_leave_fixed", _press("AcceptRole")
    )
    d.pump(0.3)
    d.check("an Auto grid again", d.ctx.grid_state.mode == GridMode.AUTO_ROWS)

    d.choose(first, "menu_generator_own_grid_templates", "Stage")
    d.pump(0.3)
    d.check("made again", commands.grid_template_now() == STAGE)
    d.check(
        "the first video in the big cell",
        first.geometry().size() == d.cells[1].geometry().size() * 2,
        (first.geometry(), d.cells[1].geometry()),
    )
    d.shot("7_stage_again")

    d.through_modal(
        lambda: d.choose(first, "menu_generator_delete_grid_template", "Stage"),
        "8_delete",
        _press("DestructiveRole"),
    )
    d.pump(0.3)
    d.check(
        "deleted", not list(Settings().get("player/grid_templates")), Settings().get
    )
    d.check(
        "gone from the menu", d.menu(first, "menu_generator_own_grid_templates") == []
    )
    d.check("Choose Size… ticked again", actions["Fixed Grid"].check_if())
    titles, _ = _shot_menu(d, "Fixed Grid", "9_fixed_grid_menu_empty")
    d.check("no Delete Template with none", "Delete Template" not in titles, titles)
    d.check(
        "the videos all still there, playing",
        len(d.cells) == 4 and all(c.is_playable for c in d.cells),
    )

    stored = OwnGridTemplates(
        (
            OwnGridTemplate(name="Stage", cols=4, rows=3, big=((0, 0, 2, 2),)),
            OwnGridTemplate(name="Wall", cols=3, rows=2),
        )
    )
    Settings().set("player/grid_templates", stored)
    titles = _shot_generated(d, "Delete Grid Template", "10_delete_menu")
    d.check("Delete All after them", titles == ["Stage", "Wall", "Delete All"], titles)
    d.through_modal(
        lambda: d.choose(first, "menu_generator_delete_grid_template", "Delete All"),
        "11_delete_all",
        _press("DestructiveRole"),
    )
    d.pump(0.3)
    d.check("all deleted", not list(Settings().get("player/grid_templates")))


def _shot_generated(d, action, shot):
    """A generated submenu as it opens."""

    from PyQt5.QtCore import QPoint

    from gridplayer.widgets.custom_menu import CustomMenu

    holder = CustomMenu(parent=d.player)
    holder.addAction(d.ctx.actions[action].to_menu_action(holder))
    menu = holder.actions()[0].menu()
    menu.popup(d.player.mapToGlobal(QPoint(20, 20)))
    d.pump(0.3)
    d.shot(shot, menu)
    titles = [a.text() for a in menu.actions() if not a.isSeparator()]
    menu.close()
    holder.deleteLater()
    d.pump(0.1)
    return titles
