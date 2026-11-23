"""Where things are, and scripts/translations/config.toml."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# GP_TRANSLATIONS_ROOT: a copy of the checkout to try the pipeline on
ROOT = Path(
    os.environ.get("GP_TRANSLATIONS_ROOT") or Path(__file__).resolve().parents[3]
)

TR_DIR = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "resources" / "translations"
SOURCE = TRANSLATIONS / "en_US.ts"
APP_DIR = ROOT / "gridplayer"
WORK = ROOT / "build" / "translations"
APPROVED_DIR = WORK / "approved"
SUGGESTIONS_DIR = WORK / "suggestions"
PROMPTS_DIR = WORK / "prompts"
REPORT = WORK / "report.md"
# credentials stay in the real checkout
LOCAL = Path(__file__).resolve().parents[3] / ".local"


@dataclass(frozen=True)
class Language:
    code: str
    crowdin: str
    name: str

    @property
    def path(self) -> Path:
        return TRANSLATIONS / f"{self.code}.ts"

    @property
    def approved_path(self) -> Path:
        return APPROVED_DIR / f"{self.code}.json"

    @property
    def suggestions_path(self) -> Path:
        return SUGGESTIONS_DIR / f"{self.code}.json"


@dataclass
class Config:
    provider: str
    batch_size: int
    parallel: int
    providers: dict[str, dict]
    languages: dict[str, Language]
    glossary_terms: dict[str, str] = field(default_factory=dict)
    glossary_keep: list[str] = field(default_factory=list)

    def pick(self, codes: list[str] | None) -> list[Language]:
        if not codes:
            return list(self.languages.values())
        unknown = [c for c in codes if c not in self.languages]
        if unknown:
            raise SystemExit(f"Not in config.toml: {', '.join(unknown)}")
        return [self.languages[c] for c in codes]


def load() -> Config:
    with (TR_DIR / "config.toml").open("rb") as f:
        raw = tomllib.load(f)
    with (TR_DIR / "glossary.toml").open("rb") as f:
        glossary = tomllib.load(f)

    return Config(
        provider=raw["ai"]["provider"],
        batch_size=raw["ai"]["batch_size"],
        parallel=raw["ai"]["parallel"],
        providers=raw["providers"],
        languages={
            code: Language(code, lang["crowdin"], lang["name"])
            for code, lang in raw["languages"].items()
        },
        glossary_terms=glossary.get("terms", {}),
        glossary_keep=glossary.get("keep", []),
    )
