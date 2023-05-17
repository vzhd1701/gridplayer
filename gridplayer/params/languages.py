from typing import List, NamedTuple

from PyQt5.QtCore import QLocale


class LanguageAuthor(NamedTuple):
    name: str
    url: str


class Language(NamedTuple):
    code: str
    completion: int
    authors: List[LanguageAuthor]

    @property
    def author_names(self):
        return [author.name for author in self.authors]

    @property
    def author_links(self):
        return ['<a href="{0}">{1}</a>'.format(a.url, a.name) for a in self.authors]

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
    Language(code="en_US", completion=100, authors=[]),
    Language(
        code="ar_SA",
        completion=100,
        authors=[LanguageAuthor("azoaz6001", "https://crowdin.com/profile/azoaz6001")],
    ),
    Language(
        code="de_DE",
        completion=100,
        authors=[
            LanguageAuthor("DominikPott", "https://crowdin.com/profile/dominikpott")
        ],
    ),
    Language(
        code="es_ES",
        completion=100,
        authors=[
            LanguageAuthor("Sergio Varela", "https://crowdin.com/profile/ingrownmink4"),
            LanguageAuthor("asolis2020", "https://crowdin.com/profile/asolis2020"),
        ],
    ),
    Language(
        code="fr_FR",
        completion=100,
        authors=[
            LanguageAuthor("Sylvain LOUIS", "https://crowdin.com/profile/louis_sylvain")
        ],
    ),
    Language(
        code="hu_HU",
        completion=52,
        authors=[LanguageAuthor("samu112", "https://crowdin.com/profile/samu112")],
    ),
    Language(
        code="it_IT",
        completion=100,
        authors=[
            LanguageAuthor("Davide V.", "https://crowdin.com/profile/davidev1"),
            LanguageAuthor("SolarCTP", "https://crowdin.com/profile/solarctp"),
        ],
    ),
    Language(
        code="ru_RU",
        completion=100,
        authors=[],
    ),
)

LANGUAGES = tuple(sorted(LANGUAGES, key=lambda lng: lng.code))
