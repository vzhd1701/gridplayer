from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class When:
    """Met while another field of the same form, named by key, has one of the
    values; by default, while that checkbox is ticked."""

    key: str
    values: tuple = (True,)


@dataclass(frozen=True, kw_only=True)
class SettingField:
    """What every field has; the subclasses say how it is edited."""

    settings_key: str
    label: str = ""
    enabled_when: When | None = None
    # hidden, it is off as well
    shown_when: When | None = None
    # while met, it shows forced_value, greyed out; its own value is kept
    # meanwhile, saved and reset as its own, and shown again once not met
    forced_when: When | None = None
    forced_value: object = True
    # or what works it out, called when the form is built; None for none
    tooltip: str | Callable[[], str | None] | None = None
    # a colour shown before the label, for what is known by its colour
    swatch: str | None = None
    # where the player can't use it at all: left out of sight, and never saved
    shown_if: Callable[[], bool] | None = None
    # why it can't be changed on this system, or None when it can: greyed out
    # with the reason for a tooltip (an empty one gives none), never saved
    unavailable: Callable[[], str | None] | None = None
    # what is shown for a stored value that can't be shown as it is;
    # the draft preserves the original until an edit or reset
    to_editor: Callable | None = None


@dataclass(frozen=True, kw_only=True)
class CheckboxField(SettingField):
    pass


@dataclass(frozen=True, kw_only=True)
class ComboField(SettingField):
    # value -> text, called when the form is built so the texts are translated
    choices: Callable[[], dict]
    # shown side by side as a row of buttons, for two to four short choices
    buttons: bool = False


@dataclass(frozen=True, kw_only=True)
class TextField(SettingField):
    placeholder: str | None = None
    # an empty one is saved as the default, for a value that can't be empty
    blank_is_default: bool = False


@dataclass(frozen=True, kw_only=True)
class PathField(TextField):
    """A folder, typed or picked."""

    browse_title: str
    # where picking starts for what is typed, by default what is typed
    start_dir: Callable[[str], Path] | None = None


@dataclass(frozen=True, kw_only=True)
class _NumberField(SettingField):
    # shown in place of the lowest value, for when that one means something else
    special_text: str | None = None
    suffix: str | None = None


@dataclass(frozen=True, kw_only=True)
class SpinField(_NumberField):
    minimum: int = 0
    maximum: int


@dataclass(frozen=True, kw_only=True)
class FloatSpinField(_NumberField):
    minimum: float = 0
    maximum: float
    decimals: int
    step: float = 0.1


@dataclass(frozen=True, kw_only=True)
class CropField(SettingField):
    pass


@dataclass(frozen=True, kw_only=True)
class ColorField(SettingField):
    pass


@dataclass(frozen=True, kw_only=True)
class LanguageField(SettingField):
    """The language list, the page to itself."""


@dataclass(frozen=True, kw_only=True)
class KeymapField(SettingField):
    """The shortcut editor, the page to itself."""


@dataclass(frozen=True, kw_only=True)
class ResolverPatternsField(SettingField):
    """The table of which resolver opens which links."""


# The layout. A layout is a tuple of items: a setting's key, a field, or one
# of these. Written the way gridplayer.params.menu writes a menu, so that
# reading it is reading the page.


class _Node:
    def __init__(self, *items):
        self.items = items

    def __repr__(self):
        return f"{type(self).__name__}{self.items!r}"


class Section(_Node):
    """Items under a heading."""

    def __init__(self, title: str, *items):
        super().__init__(*items)
        self.title = title


class Row(_Node):
    """Fields on one line: the first one's label (or checkbox) where the
    labels go, the rest after it."""


class Indented(_Node):
    """Items that belong to the one above them."""


class Note:
    """Something said on the page; links in it open."""

    def __init__(self, text: str):
        self.text = text


class Slot:
    """Whatever the dialog puts here: a button, a list, anything that isn't
    a setting. The dialog is handed the name and gives the widget."""

    def __init__(self, name: str, fills: bool = False, label: str | None = None):
        self.name = name
        # takes what the page has left, as a list or a table does
        self.fills = fills
        # where the labels go, as a field's: what the dialog gives goes on
        # the right then, with the fields
        self.label = label


class Page(_Node):
    """An entry in the settings index, and what it opens."""

    def __init__(
        self,
        page_id: str,
        title: str,
        *items,
        note: str | None = None,
        scroll: bool = True,
        icon: str | None = None,
    ):
        super().__init__(*items)
        self.id = page_id
        self.title = title
        # the theme's name for the icon beside the title, in the index too
        self.icon = icon
        # at the top, true of the whole page rather than of any one row
        self.note = note
        # a page that fills itself (a list, a table) has nothing to scroll
        self.scroll = scroll


class Group:
    """A heading in the settings index, and the pages under it."""

    def __init__(self, title: str, *pages: Page):
        self.title = title
        self.pages = pages
