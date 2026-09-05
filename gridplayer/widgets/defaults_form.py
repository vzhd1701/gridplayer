from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params.defaults_fields import FieldKind, GridVisibility, SettingField
from gridplayer.params.static import GridMode
from gridplayer.utils.qt import translate


def _fill_combo(combo: QComboBox, values: dict) -> None:
    combo.clear()
    for value, name in values.items():
        combo.addItem(name, value)


def _set_combo(combo: QComboBox, value) -> None:
    idx = combo.findData(value)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


class DefaultsForm(QWidget):
    """Shared Playlist/Video defaults form. Optional per-row reset chrome."""

    values_changed = pyqtSignal()

    def __init__(
        self,
        fields: tuple[SettingField, ...],
        show_reset: bool = False,
        default_getter=None,
    ):
        super().__init__()
        self._fields = fields
        self._show_reset = show_reset
        self._default_getter = default_getter
        self._widgets: dict[str, QWidget] = {}
        self._labels: dict[str, QWidget] = {}
        self._rows: dict[str, QWidget] = {}
        self._reset_btns: dict[str, QPushButton] = {}
        self._overridden: set[str] = set()
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        current_section = None
        for spec in fields:
            if spec.section != current_section:
                current_section = spec.section
                if spec.section:
                    header = QLabel(spec.section)
                    font = header.font()
                    font.setBold(True)
                    header.setFont(font)
                    root.addWidget(header)
            root.addWidget(self._make_row(spec))

        root.addStretch(1)
        self._sync_enabled()
        self._sync_grid_visibility()

    def _make_row(self, spec: SettingField) -> QWidget:
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        if spec.kind is FieldKind.CHECKBOX:
            widget = QCheckBox(spec.label)
            widget.stateChanged.connect(self._on_edited)
            self._labels[spec.settings_key] = widget
            lay.addWidget(widget, alignment=Qt.AlignVCenter)
        elif spec.kind is FieldKind.COMBO:
            label = QLabel(spec.label)
            self._labels[spec.settings_key] = label
            lay.addWidget(label)
            widget = QComboBox()
            _fill_combo(widget, spec.combo_values())
            widget.currentIndexChanged.connect(self._on_edited)
            lay.addWidget(widget)
        elif spec.kind is FieldKind.SPIN:
            label = QLabel(spec.label)
            self._labels[spec.settings_key] = label
            lay.addWidget(label)
            widget = QSpinBox()
            widget.setRange(spec.spin_min, spec.spin_max)
            if spec.spin_special is not None:
                widget.setSpecialValueText(spec.spin_special)
            widget.valueChanged.connect(self._on_edited)
            lay.addWidget(widget)
            if spec.spin_suffix:
                lay.addWidget(QLabel(spec.spin_suffix))
        else:
            raise ValueError(f"Unknown field kind {spec.kind}")

        widget.setObjectName(spec.settings_key)
        self._widgets[spec.settings_key] = widget

        if spec.tooltip:
            holder.setToolTip(spec.tooltip)

        if self._show_reset:
            reset = QPushButton(translate("SettingsDialog", "Reset"))
            reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            reset.clicked.connect(
                lambda _=False, key=spec.settings_key: self._on_reset(key)
            )
            self._reset_btns[spec.settings_key] = reset
            lay.addWidget(reset, alignment=Qt.AlignVCenter)
            holder.setMinimumHeight(reset.sizeHint().height())
            reset.hide()

        lay.addStretch(1)
        self._rows[spec.settings_key] = holder
        return holder

    def _on_edited(self, *_args):
        if self._updating:
            return
        sender = self.sender()
        if sender is not None:
            self._overridden.add(sender.objectName())
        self._sync_enabled()
        self._sync_grid_visibility()
        self._sync_modified()
        self.values_changed.emit()

    def _spec_for_key(self, key: str) -> SettingField | None:
        for spec in self._fields:
            if spec.settings_key == key:
                return spec
        return None

    def _on_reset(self, key: str):
        spec = self._spec_for_key(key)
        self._overridden.discard(key)
        if self._default_getter is not None and spec is not None:
            self._updating = True
            try:
                self._set_widget(spec, self._default_getter(spec.settings_key))
            finally:
                self._updating = False
        self._sync_enabled()
        self._sync_grid_visibility()
        self._sync_modified()
        self.values_changed.emit()

    def set_values(self, values: dict, overridden: set[str] | None = None):
        self._updating = True
        try:
            for spec in self._fields:
                if spec.settings_key in values:
                    self._set_widget(spec, values[spec.settings_key])
            self._overridden = set(overridden or [])
        finally:
            self._updating = False
        self._sync_enabled()
        self._sync_grid_visibility()
        self._sync_modified()

    def values(self) -> dict:
        return {spec.settings_key: self._get_widget(spec) for spec in self._fields}

    def overridden_keys(self) -> set[str]:
        return set(self._overridden)

    def mark_all_overridden(self):
        self._overridden = {spec.settings_key for spec in self._fields}
        self._sync_modified()

    def clear_overridden(self):
        self._overridden = set()
        self._sync_modified()

    def apply_defaults(self, defaults: dict):
        self._updating = True
        try:
            for spec in self._fields:
                if (
                    spec.settings_key not in self._overridden
                    and spec.settings_key in defaults
                ):
                    self._set_widget(spec, defaults[spec.settings_key])
        finally:
            self._updating = False
        self._sync_enabled()
        self._sync_grid_visibility()

    def is_enabled(self, key: str) -> bool:
        widget = self._widgets.get(key)
        return widget is not None and widget.isEnabled()

    def _set_widget(self, spec: SettingField, value):
        widget = self._widgets[spec.settings_key]
        if spec.kind is FieldKind.CHECKBOX:
            widget.setChecked(bool(value))
        elif spec.kind is FieldKind.COMBO:
            _set_combo(widget, value)
        elif spec.kind is FieldKind.SPIN:
            widget.setValue(int(value))

    def _get_widget(self, spec: SettingField):
        widget = self._widgets[spec.settings_key]
        if spec.kind is FieldKind.CHECKBOX:
            return widget.isChecked()
        if spec.kind is FieldKind.COMBO:
            return widget.currentData()
        if spec.kind is FieldKind.SPIN:
            return widget.value()
        raise ValueError(spec.kind)

    def _sync_enabled(self):
        for spec in self._fields:
            if not spec.enabled_by:
                continue
            driver = self._widgets.get(spec.enabled_by)
            widget = self._widgets.get(spec.settings_key)
            if driver is None or widget is None:
                continue
            enabled = driver.isChecked()
            widget.setEnabled(enabled)
            label = self._labels.get(spec.settings_key)
            if label is not None:
                label.setEnabled(enabled)

    def _sync_grid_visibility(self):
        mode_widget = self._widgets.get("playlist/grid_mode")
        if mode_widget is None:
            return
        is_fixed = mode_widget.currentData() == GridMode.FIXED
        for spec in self._fields:
            if spec.grid_visibility is GridVisibility.ALWAYS:
                continue
            visible = (
                is_fixed
                if spec.grid_visibility is GridVisibility.FIXED_ONLY
                else not is_fixed
            )
            row = self._rows.get(spec.settings_key)
            if row is not None:
                row.setVisible(visible)
            if spec.enabled_by:
                # enabled_by owns enablement for such fields; keep them orthogonal.
                continue
            widget = self._widgets.get(spec.settings_key)
            if widget is not None:
                widget.setEnabled(visible)
            label = self._labels.get(spec.settings_key)
            if label is not None:
                label.setEnabled(visible)

    def _sync_modified(self):
        if not self._show_reset:
            return
        for spec in self._fields:
            is_over = spec.settings_key in self._overridden
            label = self._labels.get(spec.settings_key)
            if label is not None:
                font = label.font()
                font.setItalic(is_over)
                label.setFont(font)
            reset = self._reset_btns.get(spec.settings_key)
            if reset is not None:
                reset.setVisible(is_over)
