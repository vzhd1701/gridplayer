import sys
from typing import NamedTuple

from pydantic.version import VERSION as PYDANTIC_VERSION
from PyQt5.Qt import PYQT_VERSION_STR
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog

from gridplayer import params_env
from gridplayer.dialogs.about_dialog_ui import Ui_AboutDialog
from gridplayer.version import (
    __app_bugtracker_url__,
    __app_license_url__,
    __app_url__,
    __display_name__,
    __version__,
)


class Attribution(NamedTuple):
    title: str
    version: str
    author: str
    license: str
    url: str


def generate_attributions(attributions):
    attributions_txt = []
    for a in attributions:
        version = f" {a.version}" if a.version else ""

        attributions_txt.append(
            f"<p><b>{a.title}{version}</b>"
            f' by <a href="{a.url}">{a.author}</a><br>'
            f"<i>Licensed under {a.license}</i></p>"
        )

    return "\n".join(attributions_txt)


class AboutDialog(QDialog, Ui_AboutDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setupUi(self)

        self.logo.setPixmap(QIcon(":/icons/main_ico_big.svg").pixmap(self.logo.size()))

        self.name.setText(__display_name__)
        self.version.setText(f"version {__version__}")

        about_info = self.info.text()
        about_info = about_info.replace("{APP_URL}", __app_url__)
        about_info = about_info.replace("{APP_BUGTRACKER_URL}", __app_bugtracker_url__)
        about_info = about_info.replace("{APP_LICENSE_URL}", __app_license_url__)
        self.info.setText(about_info)

        attributions_general = [
            Attribution(
                "Python",
                sys.version.split(" ")[0],
                "Python Software Foundation",
                "Python Software Foundation License",
                "https://www.python.org/",
            ),
            Attribution(
                "Qt",
                QT_VERSION_STR,
                "Qt Project",
                "GPL 2.0, GPL 3.0, and LGPL 3.0",
                "https://www.qt.io/",
            ),
            Attribution(
                "VLC",
                None,
                "VideoLAN",
                "GPL 2.0 or later",
                "https://www.videolan.org/",
            ),
        ]

        attributions_python = [
            Attribution(
                "PyQt",
                PYQT_VERSION_STR,
                "Riverbank Computing",
                "Riverbank Commercial License and GPL v3",
                "https://riverbankcomputing.com/",
            ),
            Attribution(
                "python-vlc",
                params_env.VLC_PYTHON_VERSION,
                "Olivier Aubert",
                "GPL 2.0 and LGPL 2.1",
                "https://github.com/oaubert/python-vlc",
            ),
            Attribution(
                "pydantic",
                PYDANTIC_VERSION,
                "Samuel Colvin",
                "MIT License",
                "https://github.com/samuelcolvin/pydantic",
            ),
        ]

        attributions_gui = [
            Attribution(
                "Hack Font",
                "3.003",
                "Source Foundry",
                "MIT License",
                "http://sourcefoundry.org/hack/",
            ),
            Attribution(
                "Basic Icons",
                None,
                "Icongeek26",
                "Flaticon License",
                "https://www.flaticon.com/authors/icongeek26",
            ),
            Attribution(
                "Suru Icons",
                None,
                "Sam Hewitt",
                "Creative Commons Attribution-Share Alike 4.0",
                "https://snwh.org/",
            ),
        ]

        attributions_txt = [
            "<style>p, h3 {text-align: center;}</style>",
            generate_attributions(attributions_general),
            "<h3>Python packages</h3>",
            generate_attributions(attributions_python),
            "<h3>Graphics</h3>",
            generate_attributions(attributions_gui),
        ]

        self.attributionsBox.setText("\n".join(attributions_txt))
