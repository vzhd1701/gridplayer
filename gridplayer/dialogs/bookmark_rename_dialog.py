from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

from gridplayer.dialogs.input_dialog import TEXT_INPUT_MIN_WIDTH
from gridplayer.widgets.bookmark_colors import BookmarkColorPalette


class QBookmarkRenameDialog(QtWidgets.QDialog):
    """A bookmark's name, and its colour, picked from circles as the video's
    own is."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.name = QtWidgets.QLineEdit(self)
        self.name.setMinimumWidth(TEXT_INPUT_MIN_WIDTH)

        self.colors = BookmarkColorPalette(parent=self)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        layout.addWidget(self.name)
        layout.addWidget(self.colors)
        layout.addWidget(buttons)

    @classmethod
    def get_edits(
        cls,
        parent,
        title: str,
        name: str,
        placeholder: str,
        color: str | None,
    ) -> tuple[str, str | None] | None:
        """The name typed and the colour picked, None where it was given up."""

        dialog = cls(parent=parent)
        dialog.setWindowTitle(title)

        dialog.name.setText(name)
        dialog.name.selectAll()
        dialog.name.setPlaceholderText(placeholder)

        dialog.colors.color = color

        try:
            if dialog.exec():
                return dialog.name.text(), dialog.colors.color

            return None
        finally:
            # parented to the window, which would otherwise keep every one
            dialog.deleteLater()
