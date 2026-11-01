from pydantic import BaseModel, RootModel

from gridplayer.params.static import GridTemplate


class OwnGridTemplate(BaseModel):
    """A Fixed Grid saved as a template, under the name it was given: its
    size and its big cells, as a GridTemplate has them."""

    name: str
    cols: int
    rows: int
    big: tuple[tuple[int, int, int, int], ...] = ()

    @property
    def template(self) -> GridTemplate:
        return GridTemplate(self.cols, self.rows, self.big)


class OwnGridTemplates(RootModel):
    """The templates of one's own, in the order they were saved in."""

    root: tuple[OwnGridTemplate, ...] = ()

    def __iter__(self):
        return iter(self.root)

    def __len__(self):
        return len(self.root)

    def __getitem__(self, index: int) -> OwnGridTemplate:
        return self.root[index]

    def added(self, template: OwnGridTemplate) -> "OwnGridTemplates":
        """With this one at the end, or in the place of one of its name."""

        names = [t.name for t in self.root]
        if template.name in names:
            index = names.index(template.name)
            return OwnGridTemplates(
                (*self.root[:index], template, *self.root[index + 1 :])
            )

        return OwnGridTemplates((*self.root, template))

    def removed(self, index: int) -> "OwnGridTemplates":
        return OwnGridTemplates(self.root[:index] + self.root[index + 1 :])
