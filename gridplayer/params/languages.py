from typing import NamedTuple

from PyQt5.QtCore import QLocale

from gridplayer.params.languages_contrib import LANGUAGES_CONTRIB


class LanguageAuthor(NamedTuple):
    name: str
    url: str


class Language(NamedTuple):
    code: str
    completion: int
    authors: list[LanguageAuthor]

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
        return f":/icons/flag_{self.code}.svg"


def get_system_language() -> str:
    local_language_code = QLocale().system().name()

    language_codes = {lang.code for lang in LANGUAGES}

    if local_language_code in language_codes:
        return local_language_code

    return "en_US"


LANGUAGES = (
    Language(
        code=lang_id,
        completion=lang["completion"],
        authors=[
            LanguageAuthor(user["full_name"], user["profile_url"])
            for user in lang["authors"]
        ],
    )
    for lang_id, lang in LANGUAGES_CONTRIB.items()
)

LANGUAGES = tuple(sorted(LANGUAGES, key=lambda lng: lng.code))
