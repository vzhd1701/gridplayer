from pydantic import RootModel


class KeymapOverrides(RootModel):
    """Sparse user overrides: action_id -> list of shortcut strings.

    Kept apart from utils/keymap.py, which needs the actions table: settings
    import this before the app has a translator, and the actions table
    translates its titles the moment it is imported.
    """

    root: dict[str, list[str]] = {}

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def get(self, key, default=None):
        return self.root.get(key, default)

    def items(self):
        return self.root.items()

    def __bool__(self):
        return bool(self.root)
