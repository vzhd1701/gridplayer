import sys

from pydantic.version import VERSION as PYDANTIC_VERSION
from PyQt5.Qt import PYQT_VERSION_STR
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.QtWidgets import QDialog

from gridplayer import params_vlc
from gridplayer.dialogs.about_ui import Ui_AboutDialog
from gridplayer.resources import ICONS
from gridplayer.version import (
    __app_bugtracker_url__,
    __app_license_url__,
    __app_url__,
    __display_name__,
    __version__,
)


def generate_attributions(attributions):
    attributions_txt = []
    for name, version, author, license, url in attributions:
        title = name
        if version:
            title += f" {version}"

        line = f'<p><b>{title}</b> by <a href="{url}">{author}</a>'

        if license:
            line += f"<br><i>Licensed under {license}</i></p>"

        attributions_txt.append(line)

    return "\n".join(attributions_txt)


class AboutDialog(QDialog, Ui_AboutDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setupUi(self)

        self.logo.setPixmap(ICONS["main/svg/big"].pixmap(self.logo.size()))

        self.name.setText(__display_name__)
        self.version.setText(f"version {__version__}")

        info = self.info.text()
        info = info.replace("{APP_URL}", __app_url__)
        info = info.replace("{APP_BUGTRACKER_URL}", __app_bugtracker_url__)
        info = info.replace("{APP_LICENSE_URL}", __app_license_url__)
        self.info.setText(info)

        attributions = [
            (
                "Python",
                sys.version.split(" ")[0],
                "Python Software Foundation",
                "Python Software Foundation License",
                "https://www.python.org/",
            ),
            (
                "Qt",
                QT_VERSION_STR,
                "Qt Project",
                "GPL 2.0, GPL 3.0, and LGPL 3.0",
                "https://www.qt.io/",
            ),
            ("VLC", None, "VideoLAN", "GPL 2.0 or later", "https://www.videolan.org/",),
        ]

        attributions_python = [
            (
                "PyQt",
                PYQT_VERSION_STR,
                "Riverbank Computing",
                "Riverbank Commercial License and GPL v3",
                "https://riverbankcomputing.com/",
            ),
            (
                "python-vlc",
                params_vlc.VLC_PYTHON_VERSION,
                "Olivier Aubert",
                "GPL 2.0 and LGPL 2.1",
                "https://github.com/oaubert/python-vlc",
            ),
            (
                "pydantic",
                PYDANTIC_VERSION,
                "Samuel Colvin",
                "MIT License",
                "https://github.com/samuelcolvin/pydantic",
            ),
        ]

        attributions_gui = [
            (
                "Hack Font",
                "3.003",
                "Source Foundry",
                "MIT License",
                "http://sourcefoundry.org/hack/",
            ),
            (
                "Basic Icons",
                None,
                "Icongeek26",
                "Flaticon License",
                "https://www.flaticon.com/authors/icongeek26",
            ),
            (
                "Suru Icons",
                None,
                "Sam Hewitt",
                "Creative Commons Attribution-Share Alike 4.0",
                "https://snwh.org/",
            ),
        ]

        attributions_txt = generate_attributions(attributions)
        attributions_python_txt = "<h3>Python packages</h3>" + generate_attributions(
            attributions_python
        )
        attributions_gui_txt = "<h3>Graphics</h3>" + generate_attributions(
            attributions_gui
        )

        meta = "<style>p, h3 {text-align: center;}</style>"
        self.attributionsBox.setText(
            meta + attributions_txt + attributions_python_txt + attributions_gui_txt
        )
