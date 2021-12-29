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


class AboutDialog(QDialog, Ui_AboutDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.setupUi(self)

        self.logo.setPixmap(QIcon(":/icons/main_ico_big.svg").pixmap(self.logo.size()))

        self.name.setText(__display_name__)
        self.version.setText(
            self.tr("version {APP_VERSION}").replace("{APP_VERSION}", __version__)
        )

        about_info = [
            self.tr(
                "<p>This software is licensed under "
                '<a href="{APP_LICENSE_URL}">GNU GPL</a> version 3.</p>'
            ),
            self.tr(
                '<p>Source code is available on <a href="{APP_URL}">GitHub</a>.<br/>'
            ),
            self.tr(
                "Please send any suggestions and bug reports "
                '<a href="{APP_BUGTRACKER_URL}">here</a>.</p>'
            ),
        ]
        about_info = "".join(about_info)
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
            self.generate_attributions(attributions_general),
            "<h3>{0}</h3>".format(self.tr("Python packages")),
            self.generate_attributions(attributions_python),
            "<h3>{0}</h3>".format(self.tr("Graphics")),
            self.generate_attributions(attributions_gui),
        ]

        self.attributionsBox.setText("\n".join(attributions_txt))

    def generate_attributions(self, attributions):
        attributions_txt = []
        for a in attributions:
            app_title = "{0} {1}".format(a.title, a.version or "").strip()
            app_url = f'<a href="{a.url}">{a.author}</a>'

            attribution_txt = self.tr(
                "<p><b>{APP_TITLE}</b> by {APP_URL}<br>"
                "<i>Licensed under {APP_LICENSE}</i></p>"
            )

            attribution_txt = attribution_txt.replace("{APP_TITLE}", app_title)
            attribution_txt = attribution_txt.replace("{APP_URL}", app_url)
            attribution_txt = attribution_txt.replace("{APP_LICENSE}", a.license)

            attributions_txt.append(attribution_txt)

        return "\n".join(attributions_txt)
