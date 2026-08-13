from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu, QProxyStyle, QStyle

from gridplayer.params.theme import current_colors

ICON_SIZE = 24

MENU_STYLE = """
QMenu {
    background-color: {background};
    color: {text};
    border: 1px solid {border};
    margin: 0;
    menu-scrollable: 1;
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
QMenu::item:disabled { color: {text_disabled}; }
"""


class CustomMenu(QMenu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Do not pass qApp.style() into QProxyStyle — that transfers ownership of the
        # *application* style to the proxy. When the menu is destroyed, Qt deletes the
        # app style and the process later dies with ACCESS_VIOLATION (0xC0000005).
        # Default-constructed QProxyStyle uses the app style without taking ownership.
        style = BigMenuIcons()
        style.setParent(self)
        self.setStyle(style)
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
    colors = current_colors()
    style = MENU_STYLE

    for c_key, c_value in colors.items():
        style = style.replace(f"{{{c_key}}}", c_value)

    return style.replace("{icon_size}", str(ICON_SIZE))
