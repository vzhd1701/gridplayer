"""The templates of one's own: Fixed Grids saved from the menu under a name,
their size and their big cells, kept in the settings for every playlist and
listed in the Fixed Grid menu after the built-in ones."""

from gridplayer.dialogs.input_dialog import QCustomTextInput
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.models.grid_templates import OwnGridTemplate
from gridplayer.params.static import GRID_TEMPLATES, GridTemplate
from gridplayer.player.managers.base import ManagerBase
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.widgets.grid_template_icon import grid_template_icon

SETTING = "player/grid_templates"


class GridTemplatesManager(ManagerBase):
    @property
    def commands(self):
        return {
            "is_grid_fixed_custom": self.is_grid_fixed_custom,
            "set_own_grid_template": self.cmd_set_own,
            "is_own_grid_template": self.is_own,
            "save_grid_template": self.cmd_save,
            "can_save_grid_template": self.can_save,
            "delete_grid_template": self.cmd_delete,
            "delete_all_grid_templates": self.cmd_delete_all,
            "menu_generator_own_grid_templates": self.menu_generator_own,
            "menu_generator_delete_grid_template": self.menu_generator_delete,
        }

    def _own(self) -> list[tuple[int, OwnGridTemplate]]:
        # those there can be: one written into the settings by hand may not
        return [
            (index, own)
            for index, own in enumerate(Settings().get(SETTING))
            if own.template.fits()
        ]

    def _shaped_as_any(self) -> bool:
        is_shaped_as = self._ctx.commands.is_grid_shaped_as
        return any(map(is_shaped_as, GRID_TEMPLATES.values())) or any(
            is_shaped_as(own.template) for _, own in self._own()
        )

    def is_grid_fixed_custom(self) -> bool:
        """A Fixed Grid that is none of the templates."""

        return self._ctx.commands.is_grid_fixed() and not self._shaped_as_any()

    def is_own(self, index: int) -> bool:
        own = _at(index)
        return own is not None and self._ctx.commands.is_grid_shaped_as(own.template)

    def cmd_set_own(self, index: int):
        own = _at(index)
        if own is not None and own.template.fits():
            self._ctx.commands.apply_grid_template(own.template)

    def can_save(self) -> bool:
        """A Fixed Grid there is no template of yet."""

        return self.is_grid_fixed_custom()

    def cmd_save(self):
        template = self._ctx.commands.grid_template_now()
        if template is None:
            return

        name = QCustomTextInput.get_name(
            parent=self.parent(),
            title=translate("Dialog - Grid Template", "Save as Template", "Header"),
            initial_value=self._new_name(template),
        )
        if name is None:
            return

        templates = Settings().get(SETTING)
        if name in (own.name for own in templates) and not self._confirm_replace(name):
            return

        Settings().set(
            SETTING,
            templates.added(
                OwnGridTemplate(
                    name=name,
                    cols=template.cols,
                    rows=template.rows,
                    big=template.big,
                )
            ),
        )

    def cmd_delete(self, index: int):
        own = _at(index)
        if own is None:
            return

        is_deleted = QCustomMessageBox.confirm(
            self.parent(),
            translate("Dialog - Grid Template", "Delete Template", "Header"),
            translate("Dialog - Grid Template", "Delete the template “{NAME}”?").format(
                NAME=own.name
            ),
            translate("Dialog - Grid Template", "Delete"),
            is_destructive=True,
        )
        if not is_deleted:
            return

        templates = Settings().get(SETTING).removed(index)
        if templates:
            Settings().set(SETTING, templates)
        else:
            Settings().reset(SETTING)

    def menu_generator_own(self):
        return [
            {
                "title": own.name,
                "icon": grid_template_icon(own.template),
                "func": ("set_own_grid_template", index),
                "check_if": ("is_own_grid_template", index),
                "is_choice": True,
            }
            for index, own in self._own()
        ]

    def cmd_delete_all(self):
        count = len(self._own())
        if not count:
            return

        is_deleted = QCustomMessageBox.confirm(
            self.parent(),
            translate("Dialog - Grid Template", "Delete Templates", "Header"),
            translate(
                "Dialog - Grid Template", "Delete all {COUNT} of your templates?"
            ).format(COUNT=count),
            translate("Dialog - Grid Template", "Delete All"),
            info=translate("Dialog - Grid Template", "The built-in ones stay."),
            is_destructive=True,
        )
        if is_deleted:
            Settings().reset(SETTING)

    def menu_generator_delete(self):
        own = self._own()
        items = [
            {
                "title": template.name,
                "icon": grid_template_icon(template.template),
                "func": ("delete_grid_template", index),
            }
            for index, template in own
        ]

        # with one, deleting it is deleting all
        if len(own) > 1:
            items += [
                "---",
                {
                    "title": translate("Actions", "Delete All"),
                    "icon": "trash",
                    "func": "delete_all_grid_templates",
                },
            ]

        return items

    def _confirm_replace(self, name: str) -> bool:
        return QCustomMessageBox.confirm(
            self.parent(),
            translate("Dialog - Grid Template", "Save as Template", "Header"),
            translate(
                "Dialog - Grid Template", "There is a template “{NAME}” already."
            ).format(NAME=name),
            translate("Dialog - Grid Template", "Replace"),
            info=translate("Dialog - Grid Template", "Replace it with this grid?"),
        )

    def _new_name(self, template: GridTemplate) -> str:
        """As the built-in ones are named: its big cells and its small ones,
        or its size with no big cells; with a number after it where there
        is a template of that name."""

        if template.big:
            big = len(template.big)
            name = f"{big} + {len(template.places()) - big}"
        else:
            name = f"{template.cols}x{template.rows}"

        taken = {*GRID_TEMPLATES, *(own.name for own in Settings().get(SETTING))}

        number = 2
        unique = name
        while unique in taken:
            unique = f"{name} ({number})"
            number += 1

        return unique


def _at(index: int) -> OwnGridTemplate | None:
    templates = Settings().get(SETTING)
    return templates[index] if 0 <= index < len(templates) else None
