from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from gridplayer.models.grid_state import GridState
from gridplayer.params.defaults_fields import (
    GRID_STATE_ATTR,
    PLAYLIST_FIELDS,
    VIDEO_FIELDS,
)
from gridplayer.playlist_settings import grid_values_from_state
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.widgets.defaults_form import DefaultsForm
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea


class PlaylistSettingsDialog(QDialog):
    def __init__(self, overrides: dict, grid_state: GridState, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("SettingsDialog", "Playlist Settings"))
        self.setModal(True)

        self._playlist_form = DefaultsForm(
            PLAYLIST_FIELDS, show_reset=True, default_getter=Settings().get
        )
        self._video_form = DefaultsForm(
            VIDEO_FIELDS, show_reset=True, default_getter=Settings().get
        )

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
        self.setMinimumSize(500, 400)
        self.resize(500, 400)

    def _wrap_scroll(self, form: DefaultsForm) -> PageScrollArea:
        form.layout().setContentsMargins(12, 12, 12, 12)
        scroll = PageScrollArea(self)
        scroll.setWidget(form)
        return scroll

    def _load(self, overrides: dict, grid_state: GridState):
        playlist_values = {}
        video_values = {}
        for spec in PLAYLIST_FIELDS:
            if spec.is_grid:
                continue
            playlist_values[spec.settings_key] = overrides.get(
                spec.settings_key, Settings().get(spec.settings_key)
            )
        playlist_values.update(grid_values_from_state(grid_state))
        for spec in VIDEO_FIELDS:
            video_values[spec.settings_key] = overrides.get(
                spec.settings_key, Settings().get(spec.settings_key)
            )

        playlist_over = {
            key
            for key in overrides
            if key.startswith("playlist/") and key in playlist_values
        }
        video_over = {key for key in overrides if key.startswith("video_defaults/")}

        self._playlist_form.set_values(playlist_values, playlist_over)
        self._video_form.set_values(video_values, video_over)

    def _reset_all(self):
        self._playlist_form.clear_overridden()
        self._video_form.clear_overridden()
        self._playlist_form.apply_defaults(
            {
                spec.settings_key: Settings().get(spec.settings_key)
                for spec in PLAYLIST_FIELDS
            }
        )
        self._video_form.apply_defaults(
            {
                spec.settings_key: Settings().get(spec.settings_key)
                for spec in VIDEO_FIELDS
            }
        )

    def result_overrides(self) -> dict:
        result = {}
        playlist_values = self._playlist_form.values()
        video_values = self._video_form.values()
        playlist_over = self._playlist_form.overridden_keys()
        video_over = self._video_form.overridden_keys()

        for spec in PLAYLIST_FIELDS:
            key = spec.settings_key
            value = playlist_values[key]
            if spec.is_grid:
                if key in playlist_over and self._playlist_form.is_enabled(key):
                    result[key] = value
                continue
            if spec.playlist_attr is None:
                continue
            if key in playlist_over or value != Settings().get(key):
                result[key] = value

        for spec in VIDEO_FIELDS:
            key = spec.settings_key
            value = video_values[key]
            if key in video_over or value != Settings().get(key):
                result[key] = value

        return result

    def result_grid_state(self, current: GridState) -> GridState:
        values = self._playlist_form.values()
        update = {
            attr: values[key]
            for key, attr in GRID_STATE_ATTR.items()
            if self._playlist_form.is_enabled(key)
        }
        return current.model_copy(update=update)
