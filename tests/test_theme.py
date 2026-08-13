from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication

from gridplayer.params.theme import (
    THEME_DARK,
    THEME_LIGHT,
    combo_popup_stylesheet,
    current_colors,
    fusion_palette,
    selection_fill,
)
from gridplayer.utils.darkmode import is_dark_mode


def test_current_colors_match_system_theme():
    colors = current_colors()
    expected = THEME_DARK if is_dark_mode() else THEME_LIGHT
    assert colors is expected
    assert colors["base"] != "#000000"
    assert colors["text"] != colors["base"]


def test_fusion_palette_has_readable_contrast():
    palette = fusion_palette()
    base = palette.color(QPalette.Base)
    text = palette.color(QPalette.Text)
    if is_dark_mode():
        assert base.lightness() > 40
        assert text.lightness() > 180
    else:
        assert base.lightness() > 200
        assert text.lightness() < 40


def test_selection_fill_matches_theme_highlight():
    assert selection_fill().name() == current_colors()["highlight"]


def test_combo_popup_stylesheet_uses_theme_base():
    style = combo_popup_stylesheet()
    colors = current_colors()
    assert colors["base"] in style
    assert colors["text"] in style
    assert "QComboBox QAbstractItemView" in style


def test_apply_theme_sets_app_palette():
    app = QApplication.instance() or QApplication([])
    from gridplayer.params.theme import apply_theme

    apply_theme(app)
    assert app.palette().color(QPalette.Base).name() == current_colors()["base"]
    assert "QComboBox QAbstractItemView" in app.styleSheet()
