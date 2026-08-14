from types import MappingProxyType

from PyQt5.QtGui import QColor, QPalette, QTextCursor
from PyQt5.QtWidgets import QApplication, QLabel, QTextEdit

from gridplayer.main.init_icons import switch_icon_theme
from gridplayer.params.static import ColorScheme
from gridplayer.settings import Settings
from gridplayer.utils.darkmode import is_dark_mode

THEME_LIGHT = MappingProxyType(
    {
        "window": "#eeeeee",
        "base": "#ffffff",
        "alternate": "#f5f5f5",
        "text": "#000000",
        "text_disabled": "#888888",
        "button": "#eeeeee",
        "button_text": "#000000",
        "highlight": "#bbbbbb",
        "highlighted_text": "#000000",
        "tooltip_base": "#ffffdc",
        "tooltip_text": "#000000",
        "link": "#0066cc",
        "border": "#aaaaaa",
        "background": "#eeeeee",
        "background_selected": "#aaaaaa",
        "background_checked": "#888888",
    }
)

THEME_DARK = MappingProxyType(
    {
        "window": "#444444",
        "base": "#3a3a3a",
        "alternate": "#4a4a4a",
        "text": "#eeeeee",
        "text_disabled": "#888888",
        "button": "#444444",
        "button_text": "#eeeeee",
        "highlight": "#666666",
        "highlighted_text": "#ffffff",
        "tooltip_base": "#444444",
        "tooltip_text": "#eeeeee",
        "link": "#6ab0ff",
        "border": "#888888",
        "background": "#444444",
        "background_selected": "#888888",
        "background_checked": "#666666",
    }
)

_applying_theme = False


def current_colors():
    return THEME_DARK if is_dark_mode() else THEME_LIGHT


def fusion_palette() -> QPalette:
    colors = current_colors()
    palette = QPalette()

    def color(key: str) -> QColor:
        return QColor(colors[key])

    palette.setColor(QPalette.Window, color("window"))
    palette.setColor(QPalette.WindowText, color("text"))
    palette.setColor(QPalette.Base, color("base"))
    palette.setColor(QPalette.AlternateBase, color("alternate"))
    palette.setColor(QPalette.ToolTipBase, color("tooltip_base"))
    palette.setColor(QPalette.ToolTipText, color("tooltip_text"))
    palette.setColor(QPalette.Text, color("text"))
    palette.setColor(QPalette.Button, color("button"))
    palette.setColor(QPalette.ButtonText, color("button_text"))
    palette.setColor(QPalette.BrightText, QColor("#ff4444"))
    palette.setColor(QPalette.Link, color("link"))
    palette.setColor(QPalette.Highlight, color("highlight"))
    palette.setColor(QPalette.HighlightedText, color("highlighted_text"))
    palette.setColor(QPalette.PlaceholderText, color("text_disabled"))

    disabled_text = color("text_disabled")
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, disabled_text)
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#666666"))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled_text)

    return palette


def selection_fill() -> QColor:
    """Same color Fusion lists/combos use. Do not read item-widget palettes."""
    return QColor(current_colors()["highlight"])


def combo_popup_stylesheet() -> str:
    colors = current_colors()
    return (
        "QComboBox QAbstractItemView {"
        f"background-color: {colors['base']};"
        f"color: {colors['text']};"
        f"selection-background-color: {colors['highlight']};"
        f"selection-color: {colors['highlighted_text']};"
        f"border: 1px solid {colors['border']};"
        "outline: 0;"
        "}"
        "QListWidget#section_index::item:disabled {"
        f"color: {colors['text']};"
        "background: transparent;"
        "outline: 0;"
        "}"
    )


def on_system_theme_changed(app=None) -> None:
    """Re-apply theme only when the user is following the OS."""
    try:
        scheme = Settings().get("player/color_scheme")
    except RuntimeError:
        return

    if scheme != ColorScheme.SYSTEM:
        return

    apply_theme(app)


def _recolor_document_anchors(document, color: QColor) -> None:
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            fmt = fragment.charFormat()
            if fmt.isAnchor():
                fmt.setForeground(color)
                cursor = QTextCursor(document)
                cursor.setPosition(fragment.position())
                cursor.setPosition(
                    fragment.position() + fragment.length(),
                    QTextCursor.KeepAnchor,
                )
                cursor.mergeCharFormat(fmt)
            iterator += 1
        block = block.next()


_LINK_SRC_PROP = "gp_html_src"


def _label_html_source(widget: QLabel) -> str | None:
    stored = widget.property(_LINK_SRC_PROP)
    if stored:
        return stored

    text = widget.text()
    if "<a" not in text.lower():
        return None
    # QLabel.text() after setText() is Qt's exported document, not the source.
    if "qrichtext" in text.lower() or text.lstrip().lower().startswith("<!doctype"):
        return None

    widget.setProperty(_LINK_SRC_PROP, text)
    return text


def _html_with_link_color(html: str, color: QColor) -> str:
    return f"<style>a{{color:{color.name()}}}</style>{html}"


def _refresh_html_links(app) -> None:
    """HTML link color is baked into the document; palette Link is not enough."""
    link = QColor(current_colors()["link"])
    css = f"a {{ color: {link.name()}; }}"

    for widget in app.allWidgets():
        if isinstance(widget, QLabel):
            source = _label_html_source(widget)
            if source:
                widget.setText(_html_with_link_color(source, link))
        elif isinstance(widget, QTextEdit):
            widget.document().setDefaultStyleSheet(css)
            _recolor_document_anchors(widget.document(), link)


def apply_theme(app=None) -> None:
    """Apply Fusion palette, combo popup colors, and symbolic icon theme."""
    global _applying_theme
    if _applying_theme:
        return

    app = app or QApplication.instance()
    if app is None:
        return

    _applying_theme = True
    try:
        switch_icon_theme()
        app.setPalette(fusion_palette())
        app.setStyleSheet(combo_popup_stylesheet())
        _refresh_html_links(app)
    finally:
        _applying_theme = False
