from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gridplayer.dialogs.crop import QCompactCropPicker
from gridplayer.params.defaults_fields import (
    CheckboxField,
    ColorField,
    ComboField,
    CropField,
    FloatSpinField,
    GridVisibility,
    SettingField,
    SpinField,
    TextField,
)
from gridplayer.params.static import GridMode
from gridplayer.utils.qt import translate
from gridplayer.widgets.color_palette import QCompactColorPicker
from gridplayer.widgets.combo_box import cap_popup_height


def _fill_combo(combo: QComboBox, values: dict) -> None:
    combo.clear()
    for value, name in values.items():
        combo.addItem(name, value)


def _set_combo(combo: QComboBox, value) -> None:
    idx = combo.findData(value)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


class _Editor:
    """The widgets a field is edited with, and how its value goes in and out."""

    def __init__(self, spec: SettingField):
        self.spec = spec
        self.widget = self._make_widget()
        self.widget.setObjectName(spec.settings_key)
        # what greys out and turns italic along with the field
        self.label = self._make_label()

    def _make_widget(self) -> QWidget:
        raise NotImplementedError

    def _make_label(self) -> QWidget:
        return QLabel(self.spec.label)

    @property
    def changed(self):
        raise NotImplementedError

    def add_to(self, lay: QHBoxLayout) -> None:
        lay.addWidget(self.label)
        lay.addWidget(self.widget)

    def set_value(self, value) -> None:
        raise NotImplementedError

    def value(self):
        raise NotImplementedError

    def set_enabled(self, enabled: bool) -> None:
        self.widget.setEnabled(enabled)
        self.label.setEnabled(enabled)


class _CheckboxEditor(_Editor):
    def _make_widget(self):
        return QCheckBox(self.spec.label)

    def _make_label(self):
        return self.widget

    @property
    def changed(self):
        return self.widget.stateChanged

    def add_to(self, lay):
        lay.addWidget(self.widget, alignment=Qt.AlignVCenter)

    def set_value(self, value):
        self.widget.setChecked(bool(value))

    def value(self):
        return self.widget.isChecked()


class _ComboEditor(_Editor):
    spec: ComboField

    def _make_widget(self):
        widget = QComboBox()
        choices = self.spec.choices()
        _fill_combo(widget, choices)
        cap_popup_height(widget, len(choices))
        return widget

    @property
    def changed(self):
        return self.widget.currentIndexChanged

    def set_value(self, value):
        _set_combo(self.widget, value)

    def value(self):
        return self.widget.currentData()


class _TextEditor(_Editor):
    spec: TextField

    def _make_widget(self):
        widget = QLineEdit()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if self.spec.placeholder:
            widget.setPlaceholderText(self.spec.placeholder)
        return widget

    @property
    def changed(self):
        return self.widget.textChanged

    def set_value(self, value):
        self.widget.setText(str(value or ""))

    def value(self):
        return self.widget.text()

    def set_enabled(self, enabled):
        super().set_enabled(enabled)

        if self.spec.placeholder:
            # greyed out, an example of what could go here is indistinguishable
            # from a greyed out value that somebody put here
            self.widget.setPlaceholderText(self.spec.placeholder if enabled else "")


class _SpinEditor(_Editor):
    spec: SpinField | FloatSpinField

    _spin_box = QSpinBox

    def _make_widget(self):
        widget = self._spin_box()
        widget.setRange(self.spec.minimum, self.spec.maximum)
        if self.spec.special_text is not None:
            widget.setSpecialValueText(self.spec.special_text)
        return widget

    @property
    def changed(self):
        return self.widget.valueChanged

    def add_to(self, lay):
        super().add_to(lay)
        if self.spec.suffix:
            lay.addWidget(QLabel(self.spec.suffix))

    def set_value(self, value):
        self.widget.setValue(int(value))

    def value(self):
        return self.widget.value()


class _FloatSpinEditor(_SpinEditor):
    spec: FloatSpinField
    _spin_box = QDoubleSpinBox

    def _make_widget(self):
        widget = super()._make_widget()
        widget.setDecimals(self.spec.decimals)
        widget.setSingleStep(self.spec.step)
        return widget

    def set_value(self, value):
        self.widget.setValue(float(value))


class _CropEditor(_Editor):
    def _make_widget(self):
        return QCompactCropPicker()

    @property
    def changed(self):
        return self.widget.value_changed

    def set_value(self, value):
        self.widget.value = value

    def value(self):
        return self.widget.value


class _ColorEditor(_Editor):
    def _make_widget(self):
        return QCompactColorPicker()

    @property
    def changed(self):
        return self.widget.color_changed

    def set_value(self, value):
        self.widget.color = QColor(str(value)).getRgb()[:3]

    def value(self):
        return self.widget.color.name(QColor.HexRgb)


_EDITORS: dict[type[SettingField], type[_Editor]] = {
    CheckboxField: _CheckboxEditor,
    ComboField: _ComboEditor,
    TextField: _TextEditor,
    SpinField: _SpinEditor,
    FloatSpinField: _FloatSpinEditor,
    CropField: _CropEditor,
    ColorField: _ColorEditor,
}


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
        self._editors: dict[str, _Editor] = {}
        self._widgets: dict[str, QWidget] = {}
        self._rows: dict[str, QWidget] = {}
        self._reset_btns: dict[str, QToolButton] = {}
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

        editor = _EDITORS[type(spec)](spec)
        editor.changed.connect(self._on_edited)
        editor.add_to(lay)
        self._editors[spec.settings_key] = editor
        self._widgets[spec.settings_key] = editor.widget

        if spec.tooltip:
            holder.setToolTip(spec.tooltip)

        if self._show_reset:
            reset = QToolButton()
            reset.setIcon(QIcon.fromTheme("reset"))
            reset.setIconSize(QSize(14, 14))
            reset.setAutoRaise(True)
            reset.setToolTip(translate("SettingsDialog", "Reset"))
            reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            reset.clicked.connect(
                lambda _=False, key=spec.settings_key: self._on_reset(key)
            )
            self._reset_btns[spec.settings_key] = reset
            lay.addWidget(reset, alignment=Qt.AlignVCenter)
            # Keep the row as tall as with the reset button shown. The reset
            # button is still counted here, and taller fields (the color
            # swatch) set the height themselves.
            holder.setMinimumHeight(lay.minimumSize().height())
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

    def _on_reset(self, key: str):
        self._overridden.discard(key)
        if self._default_getter is not None and key in self._editors:
            self._updating = True
            try:
                self._editors[key].set_value(self._default_getter(key))
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
                    self._editors[spec.settings_key].set_value(
                        values[spec.settings_key]
                    )
            self._overridden = set(overridden or [])
        finally:
            self._updating = False
        self._sync_enabled()
        self._sync_grid_visibility()
        self._sync_modified()

    def values(self) -> dict:
        return {key: editor.value() for key, editor in self._editors.items()}

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
                    self._editors[spec.settings_key].set_value(
                        defaults[spec.settings_key]
                    )
        finally:
            self._updating = False
        self._sync_enabled()
        self._sync_grid_visibility()

    def is_enabled(self, key: str) -> bool:
        widget = self._widgets.get(key)
        return widget is not None and widget.isEnabled()

    def _sync_enabled(self):
        for spec in self._fields:
            if not spec.enabled_by:
                continue
            driver = self._editors.get(spec.enabled_by)
            if driver is None:
                continue

            enabled = driver.value() in spec.enabled_by_values
            self._editors[spec.settings_key].set_enabled(enabled)

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

            self._editors[spec.settings_key].set_enabled(visible)

    def _sync_modified(self):
        if not self._show_reset:
            return
        for key, editor in self._editors.items():
            is_over = key in self._overridden
            font = editor.label.font()
            font.setItalic(is_over)
            editor.label.setFont(font)
            reset = self._reset_btns.get(key)
            if reset is not None:
                reset.setVisible(is_over)
