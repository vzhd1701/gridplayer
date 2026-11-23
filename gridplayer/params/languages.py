from typing import NamedTuple

from PyQt6.QtCore import QLocale

from gridplayer.params import env
from gridplayer.params.languages_contrib import LANGUAGES_CONTRIB
from gridplayer.params.languages_progress import LANGUAGES_PROGRESS


class LanguageAuthor(NamedTuple):
    name: str
    url: str


class Language(NamedTuple):
    code: str
    authors: list[LanguageAuthor]
    # shares of the strings: approved by people on Crowdin, translated by AI
    checked: int = 100
    ai: int = 0

    @property
    def author_names(self):
        return [author.name for author in self.authors]

    @property
    def author_links(self):
        return [f'<a href="{a.url}">{a.name}</a>' for a in self.authors]

    @property
    def title_native(self) -> str:
        return QLocale(self.code).nativeLanguageName().title()

    @property
    def country_native(self) -> str:
        return QLocale(self.code).nativeCountryName().title()

    @property
    def icon_path(self):
        icons_dir = env.RESOURCES_DIR / "icons"
        return str(icons_dir / f"flag_{self.code}.svg")


def get_system_language() -> str:
    local_language_code = QLocale().system().name()

    language_codes = {lang.code for lang in LANGUAGES}

    if local_language_code in language_codes:
        return local_language_code

    return "en_US"


LANGUAGES = (
    Language(
        code=lang_id,
        authors=[
            LanguageAuthor(user["full_name"], user["profile_url"])
            for user in LANGUAGES_CONTRIB.get(lang_id, {}).get("authors", [])
        ],
        checked=progress["checked"],
        ai=progress["ai"],
    )
    for lang_id, progress in LANGUAGES_PROGRESS.items()
)

LANGUAGES = tuple(sorted(LANGUAGES, key=lambda lng: lng.code))
