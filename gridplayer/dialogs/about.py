import sys
from typing import NamedTuple

from pydantic.version import VERSION as PYDANTIC_VERSION
from PyQt5.Qt import PYQT_VERSION_STR
from PyQt5.QtCore import QT_VERSION_STR
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog
from streamlink import __version__ as STREAMLINK_VERSION
from yt_dlp.version import __version__ as YT_DLP_VERSION

from gridplayer.dialogs.about_dialog_ui import Ui_AboutDialog
from gridplayer.params import env
from gridplayer.params.languages import LANGUAGES
from gridplayer.version import (
    __app_bugtracker_url__,
    __app_license_url__,
    __app_url__,
    __display_name__,
    __version__,
)

PYTHON_VERSION = sys.version.split(" ")[0]


class Attribution(NamedTuple):
    title: str
    version: str | None
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

        attributions = {
            "core": [
                Attribution(
                    "Python",
                    PYTHON_VERSION,
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
                    env.VLC_VERSION,
                    "VideoLAN",
                    "GPL 2.0 or later",
                    "https://www.videolan.org/",
                ),
            ],
            "python": [
                Attribution(
                    "PyQt",
                    PYQT_VERSION_STR,
                    "Riverbank Computing",
                    "Riverbank Commercial License and GPL v3",
                    "https://riverbankcomputing.com/",
                ),
                Attribution(
                    "python-vlc",
                    env.VLC_PYTHON_VERSION,
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
                Attribution(
                    "streamlink",
                    STREAMLINK_VERSION,
                    "Christopher Rosell, Streamlink Team",
                    "BSD-2-Clause License",
                    "https://github.com/streamlink/streamlink",
                ),
                Attribution(
                    "yt-dlp",
                    YT_DLP_VERSION,
                    "Contributors",
                    "Unlicense License",
                    "https://github.com/yt-dlp/yt-dlp",
                ),
            ],
            "gui": [
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
                Attribution(
                    "Flag Icons",
                    None,
                    "Panayiotis Lipiridis",
                    "MIT License",
                    "https://github.com/lipis/flag-icons",
                ),
            ],
        }

        attributions_txt = [
            "<style>p, h3 {text-align: center;}</style>",
            f"<h3>{self.tr('Core')}</h3>",
            self.generate_attributions(attributions["core"]),
            f"<h3>{self.tr('Python packages')}</h3>",
            self.generate_attributions(attributions["python"]),
            f"<h3>{self.tr('Graphics')}</h3>",
            self.generate_attributions(attributions["gui"]),
            f"<h3>{self.tr('Translations')}</h3>",
            self.generate_attributions_translations(),
        ]

        self.attributionsBox.setText("\n".join(attributions_txt))

    def generate_attributions(self, attributions: list[Attribution]):
        attributions_txt = []
        for a in attributions:
            app_title = f"{a.title} {a.version or ''}".strip()
            app_url = f'<a href="{a.url}">{a.author}</a>'

            attribution_txt = (
                '<p style="line-height: 130%"><b>{APP_TITLE}</b><br>{APP_URL}<br>'
                "<i>{LICENSED_UNDER}<br>{APP_LICENSE}</i></p>"
            )

            attribution_txt = attribution_txt.replace(
                "{LICENSED_UNDER}", self.tr("Licensed under")
            )
            attribution_txt = attribution_txt.replace("{APP_TITLE}", app_title)
            attribution_txt = attribution_txt.replace("{APP_URL}", app_url)
            attribution_txt = attribution_txt.replace("{APP_LICENSE}", a.license)

            attributions_txt.append(attribution_txt)

        return "\n".join(attributions_txt)

    def generate_attributions_translations(self):
        attributions_txt = []

        for language in LANGUAGES:
            if not language.authors:
                continue

            attribution_txt = (
                '<p style="line-height: 130%">'
                "<b>{language}<br>({country})</b><br>{authors}</p>".format(
                    language=language.title_native,
                    country=language.country_native,
                    authors="<br/>".join(language.author_links),
                )
            )
            attributions_txt.append(attribution_txt)

        return "\n".join(attributions_txt)
