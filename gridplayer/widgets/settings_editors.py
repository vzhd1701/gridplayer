"""The widgets a setting is edited with, one kind of field each."""

from pathlib import Path

from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
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
from gridplayer.params.languages import LANGUAGES, get_system_language
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
from gridplayer.params.theme import set_secondary
from gridplayer.utils.keymap import default_keymap, merge_keymap
from gridplayer.utils.qt import translate
from gridplayer.widgets.color_palette import QCompactColorPicker
from gridplayer.widgets.combo_box import cap_popup_height, combo_index
from gridplayer.widgets.keymap_tree_view import KeymapEditor
from gridplayer.widgets.language_list import LanguageList
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList
from gridplayer.widgets.settings_controls import (
    SegmentedChoice,
    Switch,
    ToggleLabel,
)

# the square of colour in front of a label that has one
SWATCH_PX = 12

# wide enough for a path or an address to be read
TEXT_MIN_WIDTH = 260

# the narrowest a list and a number are, so that the fields of a page are
# not each as wide as what they happen to say
COMBO_MIN_WIDTH = 200
SPIN_MIN_WIDTH = 100


def _fill_combo(combo: QComboBox, values: dict) -> None:
    combo.clear()
    for value, name in values.items():
        combo.addItem(name, value)


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

    # takes the width it is given
    grows = False
    # under its label rather than beside it, the width of the row
    stacked = False
    # takes the page: a list or a table, with no label and nothing beside it
    fills = False
    # An unedited fallback or rounding does not replace the stored value.
    preserve_original = True

    def __init__(self, spec: SettingField):
        self.spec = spec
        self.tooltip = spec.tooltip() if callable(spec.tooltip) else spec.tooltip
        self.widget = self._make_widget()
        self.widget.setObjectName(spec.settings_key)
        # what greys out along with the field
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

    def means_default(self) -> bool:
        """Shows something that is saved as the default, whatever that is."""

        return False

    def _all_widgets(self) -> list[QWidget]:
        return [w for w in (self.label, *self.parts()) if w is not None]

    def set_enabled(self, enabled: bool) -> None:
        for widget in self._all_widgets():
            widget.setEnabled(enabled)

    def set_tooltip(self, text: str) -> None:
        for widget in self._all_widgets():
            widget.setToolTip(text)


class _CheckboxEditor(Editor):
    def _make_widget(self):
        switch = Switch()
        switch.setAccessibleName(self.spec.label)
        return switch

    def _make_label(self):
        return ToggleLabel(self.spec.label, self.widget)

    @property
    def changed(self):
        return self.widget.stateChanged

    def set_value(self, value):
        self.widget.setChecked(bool(value))

    def value(self):
        return self.widget.isChecked()


class _ComboEditor(Editor):
    spec: ComboField

    def _make_widget(self):
        choices = self.spec.choices()

        if self.spec.buttons:
            widget = SegmentedChoice()
            _fill_combo(widget, choices)
            return widget

        widget = QComboBox()
        widget.setMinimumWidth(COMBO_MIN_WIDTH)
        _fill_combo(widget, choices)
        cap_popup_height(widget, len(choices))
        return widget

    @property
    def changed(self):
        return self.widget.currentIndexChanged

    def set_value(self, value):
        self.widget.setCurrentIndex(combo_index(self.widget, value))

    def value(self):
        return self.widget.currentData()


class _TextEditor(Editor):
    spec: TextField

    grows = True
    stacked = True

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

    def means_default(self):
        # a file name has to come from somewhere, and the like
        return self.spec.blank_is_default and not self.widget.text().strip()

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
        if self.suffix is not None:
            set_secondary(self.suffix)

    def _make_widget(self):
        widget = self._spin_box()
        widget.setMinimumWidth(SPIN_MIN_WIDTH)
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


class _LanguageEditor(Editor):
    fills = True
    # Retired languages follow the current system default on save.
    preserve_original = False

    def _make_widget(self):
        widget = LanguageList()
        for language in LANGUAGES:
            widget.add_language_row(language)
        return widget

    @property
    def changed(self):
        return self.widget.currentItemChanged

    def set_value(self, value):
        self.widget.setValue(self.normalize(value))

    def value(self):
        return self.widget.value()

    def normalize(self, value):
        # one dropped in a later version, as a combo shows its first choice
        if any(language.code == value for language in LANGUAGES):
            return value
        return get_system_language()


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
