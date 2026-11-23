"""Fill the languages' missing strings with AI translations.

The strings to do are batched once for all the languages in the run. With
several, each batch goes to one language first, which puts it in the
provider's cache, then to the others, which read it from there; a free
worker starts the next batch meanwhile.

Each answer goes into its language's file as soon as it comes, so a run
that stops (a quota, Ctrl+C) loses nothing: the next one, with any
provider, starts from what is still missing.

Then the strings that say one thing twice are made to agree: a menu item
and its setting ("Crop Limit", "Crop limit") in the same words, a tooltip
naming an option the way the option is translated. What disagrees is asked
again once, with the other string's translation.
"""

from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

from scripts.translations.pipeline import context, merge, prompt, qa, ts_file
from scripts.translations.pipeline.providers import Provider, ProviderError

RETRY_BATCH = 10
# requests failing one after another before the run gives up
GIVE_UP_AFTER = 3


@dataclass
class Job:
    code: str
    language_name: str
    lang_path: Path
    suggestions: dict | None = None


@dataclass
class AiReport:
    translated: int = 0
    aligned: int = 0
    failed: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    languages: dict[str, AiReport] = field(default_factory=dict)
    requests: int = 0
    stopped: str = ""


@dataclass
class Common:
    source: ts_file.TsFile
    app_dir: Path
    glossary: str  # prompt.glossary_part


@dataclass
class _Language:
    job: Job
    ts: ts_file.TsFile
    by_key: dict  # key -> the language's live Message
    todo: set  # keys to translate
    memory: str
    vanished: dict  # context -> vanished hints
    done: set = field(default_factory=set)  # keys translated in this run


@dataclass
class _Task:
    lang: _Language
    wanted: list  # [(Item, Hints)]
    glossary: str
    strings: str
    many: bool

    def parts(self) -> tuple[str, str]:
        """(fixed, varying), made only when asked: a run has hundreds."""
        ask = prompt.ask_part(self.lang.job.language_name, self.wanted)
        return prompt.request(
            self.glossary, self.strings, self.lang.memory, ask, self.many
        )


def translate(
    jobs: list[Job],
    common: Common,
    provider: Provider,
    batch_size: int,
    parallel: int,
    limit: int = 0,
    retranslate_ai: bool = False,
    fix_consistency: bool = False,
    dry_run_dir: Path | None = None,
    log=print,
) -> RunReport:
    """fix_consistency: also make the AI strings of earlier runs agree."""

    report = RunReport()
    link = context.links(common.source)
    all_items = {i.key: i for i in context.items(common.source, link)}

    langs = []
    for job in jobs:
        ts = ts_file.read(job.lang_path)
        todo = merge.todo(ts, retranslate_ai=retranslate_ai)
        if limit:
            todo = todo[:limit]
        report.languages[job.code] = AiReport()
        memory = prompt.memory_part(job.language_name, context.memory(ts))
        langs.append(
            _Language(
                job,
                ts,
                ts.by_key(live=True),
                {m.key for m in todo},
                memory,
                context.vanished_by_context(ts),
            )
        )

    working = [lang for lang in langs if lang.todo]
    many = len(working) > 1
    glossary = common.glossary
    keys = {key for lang in working for key in lang.todo}
    batches = context.batches(
        [i for k, i in all_items.items() if k in keys], batch_size
    )

    groups = []
    for batch in batches:
        strings = prompt.strings_part(
            batch, context.code_excerpts(batch, common.app_dir)
        )
        group = []
        for lang in working:
            wanted = [
                (item, _hints(lang, item.key, link))
                for item in batch
                if item.key in lang.todo
            ]
            if wanted:
                group.append(_Task(lang, wanted, glossary, strings, many))
        groups.append(group)

    total = sum(len(g) for g in groups)
    if keys:
        log(
            f"{len(keys)} strings, {len(working)} languages: "
            f"{len(batches)} batches, {total} requests"
        )

    if dry_run_dir is not None:
        _write_prompts(dry_run_dir, groups)
        return report

    marker = provider.stamp
    retry = _run(groups, provider, parallel, marker, report, log, warm_up=many)

    if not report.stopped:
        pending = {(id(lang), item.key) for lang, item, _ in retry}
        apart = _disagreeing(langs, link, all_items, fix_consistency, pending)
        for lang, _, _ in apart:
            report.languages[lang.job.code].aligned += 1
        if apart:
            log(f"{len(apart)} disagree with the strings they go with")
        retry += apart

    if retry and not report.stopped:
        log(f"trying {len(retry)} again")
        groups = []
        for lang, wanted in _by_language(retry):
            for i in range(0, len(wanted), RETRY_BATCH):
                part = wanted[i : i + RETRY_BATCH]
                batch = [item for item, _ in part]
                strings = prompt.strings_part(
                    batch, context.code_excerpts(batch, common.app_dir)
                )
                groups.append([_Task(lang, part, glossary, strings, False)])
        retry = _run(groups, provider, parallel, marker, report, log, warm_up=False)

    for lang, item, hints in retry:
        if not lang.by_key[item.key].translation:
            report.languages[lang.job.code].failed.append(
                f"{item.msg.source!r}: {hints.problem}"
            )

    return report


def _hints(lang: _Language, key, link) -> context.Hints:
    related = context.related_translations(key, link, lang.by_key, skip=lang.todo)
    return context.hints(lang.by_key[key], lang.vanished, lang.job.suggestions, related)


def _disagreeing(langs, link, all_items, everything: bool, pending) -> list:
    """(language, item, hints) of the AI strings to ask again because they
    say differently what another string says: those of this run, or with
    everything, all AI strings. Of two AI strings that differ, the later
    one in en_US.ts is asked; a person's translation is never touched."""

    found = []
    for lang in langs:
        if everything:
            ours = {
                k
                for k, m in lang.by_key.items()
                if m.origin == ts_file.AI
                # on Crowdin: the reviewers' to change (merge.todo)
                and ts_file.CROWDIN_EXTRA not in m.extras
            }
        else:
            ours = lang.done
        for key in sorted(ours, key=lambda k: link.order.get(k, 0)):
            msg = lang.by_key[key]
            if msg.origin != ts_file.AI or (id(lang), key) in pending:
                continue
            problems = [
                (code, other)
                for code, other in qa.disagreements(msg, lang.by_key, link)
                if code == "names"
                or other.key not in ours
                or link.later(key, other.key)
            ]
            if not problems:
                continue
            hints = context.hints(
                msg,
                lang.vanished,
                lang.job.suggestions,
                context.related_translations(key, link, lang.by_key),
            )
            hints.problem = "; ".join(
                qa.disagreement_text(code, other) for code, other in problems
            )
            found.append((lang, all_items[key], hints))
    return found


def _run(groups, provider, parallel, marker, report, log, warm_up) -> list:
    """Run the groups' tasks; with warm_up, a group's first task alone before
    the rest of it. Gives back (language, item, hints) to try again."""

    pending = deque(deque(g) for g in groups if g)
    ready: deque[_Task] = deque()
    active = {}
    retry = []
    failures_in_a_row = 0
    total = sum(len(g) for g in pending)
    done_count = 0

    def ask(task):
        answer = provider.run(*task.parts(), prompt.SCHEMA)
        return {a.get("id"): a.get("text") for a in answer if isinstance(a, dict)}

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        try:
            while True:
                while len(active) < parallel and not report.stopped:
                    if ready:
                        task, rest = ready.popleft(), None
                    elif pending:
                        group = pending.popleft()
                        task = group.popleft()
                        rest = group
                        if not warm_up:
                            ready.extend(rest)
                            rest = None
                    else:
                        break
                    active[pool.submit(ask, task)] = (task, rest)

                if not active:
                    break

                finished, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in finished:
                    task, rest = active.pop(future)
                    done_count += 1
                    report.requests += 1
                    if rest:
                        ready.extend(rest)
                    try:
                        answers = future.result()
                    except ProviderError as e:
                        failures_in_a_row += 1
                        log(f"  request {done_count}/{total} failed: {e}")
                        if failures_in_a_row >= GIVE_UP_AFTER:
                            report.stopped = f"{GIVE_UP_AFTER} requests failed in a row"
                        continue
                    failures_in_a_row = 0
                    retry.extend(_save(task, answers, marker, report))
                    log(f"  {task.lang.job.code}: request {done_count}/{total} done")
        except KeyboardInterrupt:
            report.stopped = "interrupted"
            for future in active:
                future.cancel()
            raise

    return retry


def _save(task: _Task, answers: dict, marker: str, report: RunReport) -> list:
    """Writes what passes QA; a string asked again keeps its last good
    translation meanwhile."""
    lang = task.lang
    again = []
    for item, hints in task.wanted:
        text = answers.get(item.id)
        if text is None:
            hints.problem = "no translation was given for this id"
            again.append((lang, item, hints))
            continue
        problems = qa.errors(qa.check(item.msg.source, text, item.msg.context))
        if problems:
            hints.problem = qa.describe(problems)
            again.append((lang, item, hints))
            continue
        merge.set_ai(lang.by_key[item.key], text, marker)
        if item.key in lang.todo and item.key not in lang.done:
            report.languages[lang.job.code].translated += 1
        lang.done.add(item.key)
    ts_file.write(lang.ts, lang.job.lang_path)
    return again


def _by_language(retry):
    by_lang = {}
    for lang, item, hints in retry:
        by_lang.setdefault(id(lang), (lang, []))[1].append((item, hints))
    return list(by_lang.values())


def _write_prompts(out_dir: Path, groups) -> None:
    for n, group in enumerate(groups, 1):
        for task in group:
            prompt.dump(
                out_dir / f"batch{n:03}-{task.lang.job.code}.txt", *task.parts()
            )
