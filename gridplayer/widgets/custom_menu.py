from types import MappingProxyType

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu, QProxyStyle, QStyle

from gridplayer.utils.darkmode import is_dark_mode

ICON_SIZE = 24

COLORS_LIGHT = MappingProxyType(
    {
        "background": "#eee",
        "background_selected": "#aaa",
        "background_checked": "#888",
        "text": "#000",
        "border": "#aaa",
    }
)

COLORS_DARK = MappingProxyType(
    {
        "background": "#444",
        "background_selected": "#888",
        "background_checked": "#666",
        "text": "#eee",
        "border": "#888",
    }
)

MENU_STYLE = """
QMenu {
    background-color: {background};
    color: {text};
    border: 1px solid {border};
    margin: 0;
    menu-scrollable: 0;
}
QMenu::icon { margin-left: 5px;}
QMenu::item {
    height:{icon_size}px;
    margin: 0;
    padding: 1px 15px 1px 5px;
    background: transparent;
    border: 0 solid transparent;
}
QMenu::separator { height: 1px; margin: 2px 3px; background: {border}; }
QMenu::item:selected { background-color: {background_selected}; }
QMenu::item:checked { background-color: {background_checked}; }
QMenu::item:checked:selected  { background-color: {background_selected}; }
"""


class CustomMenu(QMenu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.setStyle(BigMenuIcons())
        self.setStyleSheet(_get_theme_style())

        self.setWindowFlags(
            self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )


class BigMenuIcons(QProxyStyle):
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_SmallIconSize:
            return ICON_SIZE
        return super().pixelMetric(metric, option, widget)


def _get_theme_style():
    colors = COLORS_DARK if is_dark_mode() else COLORS_LIGHT
    style = MENU_STYLE

    for c_key, c_value in colors.items():
        style = style.replace(f"{{{c_key}}}", c_value)

    return style.replace("{icon_size}", str(ICON_SIZE))
