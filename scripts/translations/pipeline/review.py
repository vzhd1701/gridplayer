"""A second look at a language's AI translations, with the whole file in view.

The AI step translates in batches, which can't see each other; a reader of
the whole file sees what they miss: a word taken in the wrong sense ("seek"
as "search"), a form that doesn't agree, one thing said two ways, one
English string standing for two things the language must tell apart. The
review reports only such errors, with the corrected text, and leaves
wording it would merely prefer alone.

One request a language. A fix that passes QA replaces the AI text, still an
AI draft for Crowdin's reviewers; approved translations are never touched.
Each reviewed string is marked (`<extra-gp-reviewed>`), so a later review
asks only about strings that are new or changed since. Strings already on
Crowdin are left out: a changed text would not get there.
"""

import json
from dataclasses import dataclass, field

from scripts.translations.pipeline import qa, sync, ts_file
from scripts.translations.pipeline.prompt import APP
from scripts.translations.pipeline.providers import Provider, ProviderError
from scripts.translations.pipeline.ts_file import AI, HUMAN, REVIEWED_EXTRA

KINDS = ["meaning", "grammar", "consistency", "english"]

SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["id", "kind", "problem", "fix"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}

SYSTEM = f"""\
You review a translation of the user interface of {APP}

You get a glossary, then every string of the app with its translation, one \
per line as JSON: an id, the Qt context (the window, menu or setting it \
belongs to), the English, "meaning" or "note" when the developer gave one, \
and the translation. Lines with "approved": true were made and checked by \
people: take them as right, and as the way this language says things. The \
others are AI drafts. You are told which ids to review.

Report only errors a native speaker would fix before release:
- "meaning": the translation says something other than the English means \
here, such as a word taken in the wrong sense ("seek" in a video player is \
moving in time, not searching; a "gap" between tiles is not a text space).
- "grammar": a wrong form, agreement, case or word order; a sentence that \
doesn't read.
- "consistency": one thing said two ways: a term, an option's name quoted \
in a tooltip, a menu item and the same setting, a pair of words like on/off; \
or not the way the approved translations and the glossary say it.
- "english": one English string used for two things that this language \
must say differently (an adjective for nouns of two genders, a verb and a \
noun); the code needs to split it. Say which two.

Do not report style or taste. A correct, plain translation stays even if \
you would word it otherwise. Finding nothing is a good answer.

For each error: the id, the kind, the problem in a few English words, and \
"fix": the whole corrected translation, keeping {{placeholders}}, %1 %n %v, \
HTML, line breaks, leading and trailing spaces and & shortcuts exactly as \
the English has them, and the glossary's "keep" names as they are. For \
"english", the fix for this string's use, or "" if it is right for one of \
the two. When two strings disagree, fix the wrong one; if both read right, \
fix the one that is not approved, and of two drafts the later.
"""


@dataclass
class Finding:
    msg: ts_file.Message
    kind: str
    problem: str
    before: str
    fix: str
    applied: bool
    refused: str = ""


@dataclass
class ReviewReport:
    reviewed: int = 0
    findings: list[Finding] = field(default_factory=list)
    error: str = ""


def targets(ts: ts_file.TsFile, again: bool = False) -> list[ts_file.Message]:
    """The AI strings to review: not on Crowdin yet, and not reviewed since
    they last changed, unless again."""
    return [
        m
        for m in ts.live()
        if m.origin == AI
        and sync.crowdin_id(m) is None
        and (again or REVIEWED_EXTRA not in m.extras)
    ]


def request(
    ts: ts_file.TsFile,
    wanted: list[ts_file.Message],
    language_name: str,
    glossary: str,
) -> tuple[str, str, dict[str, ts_file.Message]]:
    """(fixed, varying, id -> message)."""
    ids = {}
    lines = []
    wanted_keys = {m.key for m in wanted}
    for n, m in enumerate(ts.live(), 1):
        if m.origin not in (AI, HUMAN):
            continue
        sid = f"r{n}"
        line = {"id": sid, "qt_context": m.context, "en": m.source}
        if m.comment:
            line["meaning"] = m.comment
        if m.extracomment:
            line["note"] = m.extracomment
        line["tr"] = m.translation
        if m.origin == HUMAN:
            line["approved"] = True
        lines.append(json.dumps(line, ensure_ascii=False))
        if m.key in wanted_keys:
            ids[sid] = m

    fixed = (
        f"{SYSTEM}\n{glossary}\n"
        f"The strings in {language_name} ({len(lines)}):\n" + "\n".join(lines) + "\n"
    )
    if len(ids) == len([m for m in ts.live() if m.origin == AI]):
        ask = f"Review all the {len(ids)} AI drafts (the lines not approved).\n"
    else:
        ask = f"Review only these ids: {', '.join(ids)}\n"
    return fixed, ask, ids


def review(
    ts: ts_file.TsFile,
    wanted: list[ts_file.Message],
    language_name: str,
    glossary: str,
    provider: Provider,
    apply: bool = True,
) -> ReviewReport:
    report = ReviewReport()
    if not wanted:
        return report

    fixed, varying, ids = request(ts, wanted, language_name, glossary)
    try:
        answer = provider.run(fixed, varying, SCHEMA)
    except ProviderError as e:
        report.error = str(e)
        return report

    marker = provider.stamp
    for f in answer:
        if not isinstance(f, dict) or f.get("id") not in ids:
            continue
        msg = ids[f["id"]]
        fix = f.get("fix") or ""
        finding = Finding(
            msg, f.get("kind", ""), f.get("problem", ""), msg.translation, fix, False
        )
        if fix and fix != msg.translation:
            errors = qa.errors(qa.check(msg.source, fix, msg.context))
            if errors:
                finding.refused = qa.describe(errors)
            elif apply:
                msg.translation = fix
                finding.applied = True
        report.findings.append(finding)

    if apply:
        for msg in ids.values():
            msg.extras[REVIEWED_EXTRA] = marker
    report.reviewed = len(ids)
    return report


def render(code: str, report: ReviewReport) -> str:
    lines = [f"## {code}: {report.reviewed} reviewed, {len(report.findings)} found"]
    if report.error:
        lines.append(f"Failed: {report.error}")
    by_kind = {}
    for f in report.findings:
        by_kind.setdefault(f.kind, []).append(f)
    for kind in KINDS:
        found = by_kind.get(kind, [])
        if not found:
            continue
        lines.append(f"\n### {kind} ({len(found)})")
        for f in found:
            if f.applied:
                state = "fixed"
            elif f.refused:
                state = f"refused: {f.refused}"
            else:
                state = "not applied"
            lines.append(
                f"- `{f.msg.context}` `{f.msg.source}`: {f.problem}\n"
                f"  `{f.before}` → `{f.fix}` ({state})"
            )
    return "\n".join(lines) + "\n"
