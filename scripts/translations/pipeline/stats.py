"""How much of a language people checked, and how much is the AI's."""

from dataclasses import dataclass
from pathlib import Path

from scripts.translations.pipeline.ts_file import AI, HUMAN, TsFile

PROGRESS_FILE = Path("gridplayer/params/languages_progress.py")


@dataclass(frozen=True)
class Progress:
    total: int
    human: int
    ai: int

    @property
    def checked_pct(self) -> int:
        if not self.total:
            return 100
        return self.human * 100 // self.total

    @property
    def ai_pct(self) -> int:
        """Rounded down with what's checked, so the two never pass 100;
        a single AI string still shows."""
        if not self.total or not self.ai:
            return 0
        share = (self.human + self.ai) * 100 // self.total - self.checked_pct
        return max(share, 1)

    def as_dict(self) -> dict:
        return {"checked": self.checked_pct, "ai": self.ai_pct}


def progress(ts: TsFile, source: TsFile) -> Progress:
    """Of the strings en_US.ts has now: a file not merged since it
    changed holds fewer, and some that are gone."""
    keys = {m.key for m in source.live()}
    live = [m for m in ts.live() if m.key in keys]
    return Progress(
        total=len(keys),
        human=sum(m.origin == HUMAN for m in live),
        ai=sum(m.origin == AI for m in live),
    )


def render_progress(per_language: dict[str, Progress]) -> str:
    data = {"en_US": {"checked": 100, "ai": 0}}
    data.update({code: p.as_dict() for code, p in per_language.items()})

    rows = "".join(
        f'    "{code}": {{"checked": {d["checked"]}, "ai": {d["ai"]}}},\n'
        for code, d in sorted(data.items())
    )
    return (
        '"""Made by `tr.py stats`: the share of each language people checked\n'
        'on Crowdin, and the share the AI translated."""\n\n'
        f"LANGUAGES_PROGRESS = {{\n{rows}}}\n"
    )
