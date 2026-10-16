from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from gridplayer.models.grid_state import GridState
from gridplayer.models.settings_draft import SetValue
from gridplayer.params.settings_bindings import (
    GRID_STATE_ATTR,
    PLAYLIST_ATTRS,
    VIDEO_DEFAULT_ATTRS,
)
from gridplayer.params.settings_pages import PLAYLIST_PAGE, VIDEO_PAGE
from gridplayer.playlist_settings import grid_values_from_state
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.widgets.settings_form import SettingsForm
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea


class PlaylistSettingsDialog(QDialog):
    def __init__(self, overrides: dict, grid_state: GridState, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("SettingsDialog", "Playlist Settings"))
        self.setModal(True)

        # a reset goes back to the global settings
        self._playlist_form = SettingsForm(PLAYLIST_PAGE, reset_to=Settings().get)
        self._video_form = SettingsForm(VIDEO_PAGE, reset_to=Settings().get)

        tabs = QTabWidget()
        tabs.addTab(
            self._wrap_scroll(self._playlist_form),
            translate("SettingsDialog", "Playlist"),
        )
        tabs.addTab(
            self._wrap_scroll(self._video_form),
            translate("SettingsDialog", "Video"),
        )

        reset_all = QPushButton(translate("SettingsDialog", "Reset all"))
        reset_all.clicked.connect(self._reset_all)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(reset_all)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 9)
        root.addWidget(tabs)
        root.addLayout(bottom)

        self._load(overrides, grid_state)
        self.setMinimumSize(550, 400)
        self.resize(550, 400)

    def _wrap_scroll(self, form: SettingsForm) -> PageScrollArea:
        form.layout().setContentsMargins(12, 12, 12, 12)
        scroll = PageScrollArea(self)
        scroll.setWidget(form)
        return scroll

    def _load(self, overrides: dict, grid_state: GridState):
        playlist_values = {
            key: overrides.get(key, Settings().get(key)) for key in PLAYLIST_ATTRS
        }
        playlist_values.update(grid_values_from_state(grid_state))
        video_values = {
            key: overrides.get(key, Settings().get(key)) for key in VIDEO_DEFAULT_ATTRS
        }

        playlist_over = {
            key
            for key in overrides
            if key.startswith("playlist/") and key in playlist_values
        }
        video_over = {key for key in overrides if key.startswith("video_defaults/")}

        self._playlist_form.set_values(playlist_values, playlist_over)
        self._video_form.set_values(video_values, video_over)

    def _reset_all(self):
        self._playlist_form.reset_all()
        self._video_form.reset_all()

    def result_overrides(self) -> dict:
        result = {}
        for form in (self._playlist_form, self._video_form):
            overridden = form.overridden_keys()
            for key, change in form.persistence_result().items():
                if key in GRID_STATE_ATTR and (
                    key not in overridden or not form.is_enabled(key)
                ):
                    continue
                if isinstance(change, SetValue):
                    result[key] = change.value
        return result

    def result_grid_state(self, current: GridState) -> GridState:
        values = self._playlist_form.values()
        update = {
            attr: values[key]
            for key, attr in GRID_STATE_ATTR.items()
            if self._playlist_form.is_enabled(key)
        }
        return current.model_copy(update=update)
