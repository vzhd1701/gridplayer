from typing import NamedTuple

from PyQt5.QtCore import QLocale


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
        code="ja_JP",
        completion=100,
        authors=[
            LanguageAuthor(
                "七篠孝志", "https://crowdin.com/profile/japanese.john.doe.774"
            )
        ],
    ),
    Language(
        code="ko_KR",
        completion=100,
        authors=[LanguageAuthor("VenusGirl", "https://venusgirls.tistory.com/")],
    ),
    Language(
        code="nl_NL",
        completion=100,
        authors=[
            LanguageAuthor("Heimen Stoffels", "https://crowdin.com/profile/vistaus")
        ],
    ),
    Language(
        code="pl_PL",
        completion=100,
        authors=[
            LanguageAuthor("rafal132", "https://crowdin.com/profile/fifi132"),
            LanguageAuthor(
                "Sebastian Jasiński", "https://crowdin.com/profile/princenorris"
            ),
        ],
    ),
    Language(
        code="pt_BR",
        completion=100,
        authors=[
            LanguageAuthor("GBS ~ TECH", "https://crowdin.com/profile/gabriel-bs1")
        ],
    ),
    Language(
        code="ru_RU",
        completion=100,
        authors=[],
    ),
    Language(
        code="zh_CN",
        completion=100,
        authors=[
            LanguageAuthor("Yagang Wang", "https://crowdin.com/profile/wyg945"),
            LanguageAuthor("1017346", "https://crowdin.com/profile/1017346"),
            LanguageAuthor("焦新营", "https://crowdin.com/profile/j149697726"),
            LanguageAuthor("loser7788", "https://crowdin.com/profile/loser7788"),
            LanguageAuthor("李凡", "https://crowdin.com/profile/lif86060"),
        ],
    ),
)

LANGUAGES = tuple(sorted(LANGUAGES, key=lambda lng: lng.code))
