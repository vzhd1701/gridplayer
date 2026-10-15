"""What a settings layout shows, and under which heading, for the tests to
go by the layout rather than restate it."""

from collections.abc import Iterator

from gridplayer.params.settings_fields.kinds import Section, SettingField, _Node


def layout_sections(items, title: str | None = None) -> dict[str, str | None]:
    """The heading each setting of a layout is shown under, None for none."""

    sections = {}

    for item in items:
        if isinstance(item, Section):
            sections.update(layout_sections(item.items, item.title))
        elif isinstance(item, _Node):
            sections.update(layout_sections(item.items, title))
        else:
            sections.update(dict.fromkeys(layout_keys((item,)), title))

    return sections


def layout_keys(items) -> Iterator[str]:
    """The settings a layout shows, in the order it shows them."""

    for item in items:
        if isinstance(item, str):
            yield item
        elif isinstance(item, SettingField):
            yield item.settings_key
        elif isinstance(item, _Node):
            yield from layout_keys(item.items)
