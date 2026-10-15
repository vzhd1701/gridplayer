"""The widgets a setting is edited with, one kind of field each."""

from pathlib import Path

from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from gridplayer.dialogs.crop import QCompactCropPicker
from gridplayer.params.languages import LANGUAGES
from gridplayer.params.settings_fields.kinds import (
    CheckboxField,
    ColorField,
    ComboField,
    CropField,
    FloatSpinField,
    KeymapField,
    LanguageField,
    PathField,
    ResolverPatternsField,
    SettingField,
    SpinField,
    TextField,
)
from gridplayer.utils.keymap import default_keymap, merge_keymap
from gridplayer.utils.qt import translate
from gridplayer.widgets.color_palette import QCompactColorPicker
from gridplayer.widgets.combo_box import cap_popup_height
from gridplayer.widgets.keymap_tree_view import KeymapEditor
from gridplayer.widgets.language_list import LanguageList
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList

# the square of colour in front of a label that has one
SWATCH_PX = 12

# wide enough for a path or an address to be read
TEXT_MIN_WIDTH = 260


def _fill_combo(combo: QComboBox, values: dict) -> None:
    combo.clear()
    for value, name in values.items():
        combo.addItem(name, value)


def _combo_index(combo: QComboBox, value) -> int:
    idx = combo.findData(value)
    return idx if idx >= 0 else 0


def _swatch(color: str) -> QLabel:
    pixmap = QPixmap(SWATCH_PX, SWATCH_PX)
    pixmap.fill(QColor(color))

    # rimmed, or yellow on a light window is nowhere
    painter = QPainter(pixmap)
    painter.setPen(QColor(0, 0, 0, 90))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
    painter.end()

    swatch = QLabel()
    swatch.setPixmap(pixmap)
    return swatch


class Editor:
    """The widgets a field is edited with, and how its value goes in and out."""

    # in the label column, as its own label
    is_checkbox = False
    # takes the width it is given
    grows = False
    # takes the page: a list or a table, with no label and nothing beside it
    fills = False

    def __init__(self, spec: SettingField):
        self.spec = spec
        self.widget = self._make_widget()
        self.widget.setObjectName(spec.settings_key)
        # what greys out and turns italic along with the field
        self.marked = self._make_label()
        # what goes where the labels go, None for none
        self.label = self._label_holder()

    def _make_widget(self) -> QWidget:
        raise NotImplementedError

    def _make_label(self) -> QWidget | None:
        if not self.spec.label:
            return None
        return QLabel(self.spec.label)

    def _label_holder(self) -> QWidget | None:
        if self.marked is None or self.spec.swatch is None:
            return self.marked

        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_swatch(self.spec.swatch))
        lay.addWidget(self.marked, 1)
        return holder

    def parts(self) -> list[QWidget]:
        """The widgets after the label, in order."""

        return [self.widget]

    @property
    def changed(self):
        raise NotImplementedError

    def set_value(self, value) -> None:
        raise NotImplementedError

    def value(self):
        raise NotImplementedError

    def normalize(self, value):
        """The value as this editor would give it back."""

        return value

    def set_enabled(self, enabled: bool) -> None:
        for widget in (self.label, *self.parts()):
            if widget is not None:
                widget.setEnabled(enabled)


class _CheckboxEditor(Editor):
    is_checkbox = True

    def _make_widget(self):
        return QCheckBox(self.spec.label)

    def _make_label(self):
        return self.widget

    def _label_holder(self):
        return None

    @property
    def changed(self):
        return self.widget.stateChanged

    def set_value(self, value):
        self.widget.setChecked(bool(value))

    def value(self):
        return self.widget.isChecked()

    def normalize(self, value):
        return bool(value)


class _ComboEditor(Editor):
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
        self.widget.setCurrentIndex(_combo_index(self.widget, value))

    def value(self):
        return self.widget.currentData()

    def normalize(self, value):
        return self.widget.itemData(_combo_index(self.widget, value))


class _TextEditor(Editor):
    spec: TextField

    grows = True

    def _make_widget(self):
        widget = QLineEdit()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        widget.setMinimumWidth(TEXT_MIN_WIDTH)
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

    def normalize(self, value):
        return str(value or "")

    def set_enabled(self, enabled):
        super().set_enabled(enabled)

        if self.spec.placeholder:
            # greyed out, an example of what could go here is indistinguishable
            # from a greyed out value that somebody put here
            self.widget.setPlaceholderText(self.spec.placeholder if enabled else "")


class _PathEditor(_TextEditor):
    spec: PathField

    def __init__(self, spec):
        super().__init__(spec)

        self.browse = QPushButton(translate("SettingsDialog", "Browse..."))
        self.browse.clicked.connect(self._browse)

    def parts(self):
        return [self.widget, self.browse]

    def _browse(self):
        typed = self.widget.text()

        if self.spec.start_dir is not None:
            start = self.spec.start_dir(typed)
        else:
            start = Path(typed) if typed else None

        folder = QFileDialog.getExistingDirectory(
            self.widget,
            self.spec.browse_title,
            str(start) if start is not None and start.is_dir() else "",
        )

        if folder:
            self.widget.setText(str(Path(folder)))


class _SpinEditor(Editor):
    spec: SpinField | FloatSpinField

    _spin_box = QSpinBox

    def __init__(self, spec):
        super().__init__(spec)

        self.suffix = QLabel(spec.suffix) if spec.suffix else None

    def _make_widget(self):
        widget = self._spin_box()
        widget.setRange(self.spec.minimum, self.spec.maximum)
        if self.spec.special_text is not None:
            widget.setSpecialValueText(self.spec.special_text)
        return widget

    def parts(self):
        return [self.widget, self.suffix] if self.suffix else [self.widget]

    @property
    def changed(self):
        return self.widget.valueChanged

    def set_value(self, value):
        self.widget.setValue(int(value))

    def value(self):
        return self.widget.value()

    def normalize(self, value):
        return max(self.spec.minimum, min(self.spec.maximum, int(value)))


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

    def normalize(self, value):
        value = max(self.spec.minimum, min(self.spec.maximum, float(value)))
        return round(value, self.spec.decimals)


class _CropEditor(Editor):
    def _make_widget(self):
        return QCompactCropPicker()

    @property
    def changed(self):
        return self.widget.value_changed

    def set_value(self, value):
        self.widget.value = value

    def value(self):
        return self.widget.value


class _ColorEditor(Editor):
    def _make_widget(self):
        return QCompactColorPicker()

    @property
    def changed(self):
        return self.widget.color_changed

    def set_value(self, value):
        self.widget.color = QColor(str(value)).getRgb()[:3]

    def value(self):
        return self.widget.color.name(QColor.HexRgb)

    def normalize(self, value):
        return QColor(str(value)).name(QColor.HexRgb)


class _LanguageEditor(Editor):
    fills = True

    def _make_widget(self):
        widget = LanguageList()
        for language in LANGUAGES:
            widget.add_language_row(language)
        return widget

    @property
    def changed(self):
        return self.widget.currentItemChanged

    def set_value(self, value):
        self.widget.setValue(value)

    def value(self):
        return self.widget.value()


class _KeymapEditor(Editor):
    fills = True

    def _make_widget(self):
        return KeymapEditor()

    @property
    def changed(self):
        return self.widget.bindings_changed

    def set_value(self, value):
        self.widget.set_bindings(merge_keymap(default_keymap(), value))

    def value(self):
        return self.widget.get_sparse_bindings()


class _ResolverPatternsEditor(Editor):
    fills = True

    def _make_widget(self):
        return ResolverPatternsList()

    @property
    def changed(self):
        return self.widget.changed

    def set_value(self, value):
        self.widget.set_rows(value)

    def value(self):
        return self.widget.rows_data()


EDITORS: dict[type[SettingField], type[Editor]] = {
    CheckboxField: _CheckboxEditor,
    ComboField: _ComboEditor,
    TextField: _TextEditor,
    PathField: _PathEditor,
    SpinField: _SpinEditor,
    FloatSpinField: _FloatSpinEditor,
    CropField: _CropEditor,
    ColorField: _ColorEditor,
    LanguageField: _LanguageEditor,
    KeymapField: _KeymapEditor,
    ResolverPatternsField: _ResolverPatternsEditor,
}


def make_editor(spec: SettingField) -> Editor:
    return EDITORS[type(spec)](spec)
