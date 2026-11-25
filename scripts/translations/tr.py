"""The translations pipeline. Run only when updating translations is the job.

    uv run scripts/translations/tr.py merge        # languages against en_US.ts
    uv run scripts/translations/tr.py ai [--provider codex] [--lang de_DE]
    uv run scripts/translations/tr.py check        # QA, report in build/translations
    uv run scripts/translations/tr.py stats        # languages_progress.py

What ships for a string: its approved human translation, else the AI's, else
the English. See docs/TRANSLATIONS.md.
"""

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.translations.pipeline import (  # noqa: E402
    ai,
    config,
    context,
    merge,
    prompt,
    qa,
    review,
    stats,
    sync,
    ts_file,
)
from scripts.translations.pipeline.providers import make  # noqa: E402


def cmd_merge(cfg: config.Config, args) -> int:
    source = ts_file.read(config.SOURCE)

    for lang in cfg.pick(args.lang):
        current = ts_file.read(lang.path) if lang.path.exists() else None
        approved = load_approved(lang)
        merged, report = merge.merge(source, current, approved, lang.crowdin)
        if args.prune:
            merge.prune_vanished(merged)
        ts_file.write(merged, lang.path)

        pulled = "" if approved is not None else " (not pulled: human kept as is)"
        print(
            f"{lang.code}: {report.human} human, {report.ai_kept} AI, "
            f"{report.missing} missing, {report.vanished} vanished hints{pulled}"
        )
        if report.ai_replaced_by_human:
            print(
                f"  {report.ai_replaced_by_human} AI translations approved or replaced"
            )
        for key in report.dropped_human:
            print(f"  approval withdrawn: {key[0]}: {key[1]!r}")
    return 0


def read_lang(lang: config.Language) -> ts_file.TsFile:
    """A language added to config.toml has no file until merged."""
    if lang.path.exists():
        return ts_file.read(lang.path)
    return ts_file.TsFile(language=lang.crowdin, sourcelanguage="en")


def load_approved(lang: config.Language) -> dict | None:
    return _load_keyed(lang.approved_path)


def load_suggestions(lang: config.Language) -> dict | None:
    return _load_keyed(lang.suggestions_path)


def _load_keyed(path: Path) -> dict | None:
    if not path.exists():
        return None
    return {
        tuple(item["key"]): item["value"]
        for item in json.loads(path.read_text("utf-8"))
    }


def _save_keyed(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"key": list(k), "value": v} for k, v in data.items()]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def _crowdin():
    from scripts.translations.pipeline.crowdin_api import Crowdin  # noqa: PLC0415

    client = Crowdin.from_identity(config.LOCAL / "crowdin.yml")
    file_id = client.source_file_id()
    strings = client.strings(file_id)

    local = {m.key for m in ts_file.read(config.SOURCE).live()}
    remote = {s.key for s in strings}
    if missing := len(local - remote):
        print(
            f"Crowdin lacks {missing} of en_US.ts's {len(local)} strings: "
            "upload the sources first (just translations-upload)."
        )
    return client, file_id, strings


def cmd_pull(cfg: config.Config, args) -> int:
    client, file_id, strings = _crowdin()

    for lang in cfg.pick(args.lang):
        ts = read_lang(lang)
        pulled = sync.pull(client, file_id, strings, lang.crowdin, ts)
        _save_keyed(lang.approved_path, pulled.approved)
        _save_keyed(lang.suggestions_path, pulled.suggestions)
        if pulled.rejected:
            ts_file.write(ts, lang.path)
        print(
            f"{lang.code}: {len(pulled.approved)} approved, "
            f"{len(pulled.suggestions)} suggestions, {len(pulled.rejected)} AI taken down"
        )
        for key in pulled.rejected:
            print(f"  taken down: {key[0]}: {key[1]!r}")
    return 0


def cmd_push(cfg: config.Config, args) -> int:
    client, file_id, strings = _crowdin()

    for lang in cfg.pick(args.lang):
        ts = read_lang(lang)
        todo = sync.to_push(client, file_id, strings, lang.crowdin, ts)
        if args.limit:
            todo = todo[: args.limit]
        print(f"{lang.code}: {len(todo)} AI translations to send")
        if args.dry_run or not todo:
            continue

        sent = 0
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    pool.submit(
                        client.add_ai_translation, sid, lang.crowdin, msg.translation
                    ): msg
                    for msg, sid in todo
                }
                for future in as_completed(futures):
                    msg = futures[future]
                    try:
                        sync.set_crowdin_id(msg, future.result())
                        sent += 1
                    except Exception as e:  # noqa: BLE001 - the others go on
                        print(f"  {msg.source!r}: {e}")
        finally:
            ts_file.write(ts, lang.path)
            print(f"  {sent} sent")
    return 0


def cmd_ai(cfg: config.Config, args) -> int:
    provider = make(args.provider or cfg.provider, cfg.providers)
    jobs = []
    for lang in cfg.pick(args.lang):
        if lang.path.exists():
            jobs.append(ai.Job(lang.code, lang.name, lang.path, load_suggestions(lang)))
        else:
            print(f"{lang.code}: no file yet, run translations-merge first")
    common = ai.Common(
        source=ts_file.read(config.SOURCE),
        app_dir=config.APP_DIR,
        glossary=prompt.glossary_part(cfg.glossary_terms, cfg.glossary_keep),
    )
    dry_run_dir = config.PROMPTS_DIR if args.dry_run else None

    print(f"AI: {provider.marker}")
    report = ai.translate(
        jobs,
        common,
        provider,
        batch_size=args.batch_size or cfg.batch_size,
        parallel=args.parallel or cfg.parallel,
        limit=args.limit,
        retranslate_ai=args.retranslate_ai,
        fix_consistency=args.fix_consistency,
        dry_run_dir=dry_run_dir,
    )

    for code, lang_report in report.languages.items():
        print(
            f"{code}: {lang_report.translated} translated, "
            f"{lang_report.aligned} asked again to agree, "
            f"{len(lang_report.failed)} left English"
        )
        for line in lang_report.failed:
            print(f"    {line}")
    if dry_run_dir:
        print(f"Prompts in {dry_run_dir}")
    else:
        _print_usage(provider, f"{report.requests} requests; ")
    if report.stopped:
        print(f"Stopped: {report.stopped}. Run again, or with another --provider.")
        return 1
    return 0


def _print_usage(provider, prefix: str = "") -> None:
    if used := provider.usage_total():
        print(
            f"{prefix}tokens: {used.get('input', 0)} in, "
            f"{used.get('cache_write', 0)} written to cache, "
            f"{used.get('cache_read', 0)} read from it, {used.get('output', 0)} out; "
            f"${used.get('cost_usd', 0):.2f} at API prices"
        )


def cmd_review(cfg: config.Config, args) -> int:
    provider = make(args.provider or cfg.provider, cfg.providers)
    glossary = prompt.glossary_part(cfg.glossary_terms, cfg.glossary_keep)
    out = ["# Translations review", ""]
    failed = False
    print(f"Review: {provider.marker}")

    todo = []
    for lang in cfg.pick(args.lang):
        ts = read_lang(lang)
        wanted = review.targets(ts, again=args.again)
        if not wanted:
            print(f"{lang.code}: nothing new to review")
        elif args.dry_run:
            path = config.PROMPTS_DIR / f"review-{lang.code}.txt"
            fixed, varying, _ = review.request(ts, wanted, lang.name, glossary)
            prompt.dump(path, fixed, varying)
            print(f"{lang.code}: {len(wanted)} to review, prompt in {path}")
        else:
            todo.append((lang, ts, wanted))

    def run(lang, ts, wanted):
        started = time.monotonic()
        result = review.review(
            ts, wanted, lang.name, glossary, provider, apply=not args.report_only
        )
        return result, time.monotonic() - started

    # the languages' requests side by side, their files written here
    with ThreadPoolExecutor(max_workers=cfg.parallel) as pool:
        running = [(lang, ts, pool.submit(run, lang, ts, w)) for lang, ts, w in todo]
        for lang, ts, future in running:
            result, took = future.result()
            _review_done(lang, ts, result, took, args, out)
            failed |= bool(result.error)

    config.WORK.mkdir(parents=True, exist_ok=True)
    report_path = config.WORK / "review.md"
    report_path.write_text("\n".join(out), encoding="utf-8")
    _print_usage(provider)
    print(f"Report in {report_path}")
    return 1 if failed else 0


def _review_done(lang, ts, result, took, args, out) -> None:
    if not args.report_only and not result.error:
        ts_file.write(ts, lang.path)
    applied = sum(f.applied for f in result.findings)
    print(
        f"{lang.code}: {result.reviewed} reviewed, {len(result.findings)} found, "
        f"{applied} fixed, {took:.0f} s"
        + (f"; failed: {result.error}" if result.error else "")
    )
    out.append(review.render(lang.code, result))


def cmd_check(cfg: config.Config, args) -> int:
    lines = ["# Translations check", ""]
    failing = 0
    source = ts_file.read(config.SOURCE)
    link = context.links(source)

    for lang in cfg.pick(args.lang):
        ts = read_lang(lang)
        p = stats.progress(ts, source)
        lines.append(
            f"## {lang.code}: {p.checked_pct}% checked, {p.ai_pct}% AI, "
            f"{p.total - p.human - p.ai} missing"
        )
        by_key = ts.by_key(live=True)
        for m in ts.live():
            if not m.translation:
                continue
            if args.warnings:
                for code, other in qa.disagreements(m, by_key, link):
                    # a pair once, from its second
                    if code == "differs" and link.later(other.key, m.key):
                        continue
                    lines.append(
                        f"- {m.origin} warning: {code}: `{m.source}` → "
                        f"`{m.translation}`; `{other.source}` → `{other.translation}`"
                    )
            for issue in qa.check(m.source, m.translation, m.context):
                if issue.level == qa.WARNING and not args.warnings:
                    continue
                breaks = issue.code == qa.CRASH or (
                    m.origin == ts_file.AI and issue.level == qa.ERROR
                )
                failing += breaks
                lines.append(
                    f"- {'**must fix** ' if breaks else ''}{m.origin} {issue}: "
                    f"`{m.source}` → `{m.translation}`"
                )
        lines.append("")

    config.REPORT.parent.mkdir(parents=True, exist_ok=True)
    config.REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{failing} must be fixed; report in {config.REPORT}")
    return 1 if failing else 0


def cmd_stats(cfg: config.Config, args) -> int:
    source = ts_file.read(config.SOURCE)
    per_language = {
        lang.code: stats.progress(read_lang(lang), source) for lang in cfg.pick(None)
    }
    out = config.ROOT / stats.PROGRESS_FILE
    out.write_text(stats.render_progress(per_language), encoding="utf-8", newline="\n")
    for code, p in per_language.items():
        print(f"{code}: {p.checked_pct}% checked, {p.ai_pct}% AI")
    print(f"Written {stats.PROGRESS_FILE}")
    return 0


def cmd_screenshots(cfg: config.Config, args) -> int:
    import subprocess  # noqa: PLC0415

    from scripts.translations.pipeline import shots  # noqa: PLC0415

    out = config.WORK / "screenshots"
    scenario = config.TR_DIR / "screenshots" / "scenario.py"
    if not args.no_run:
        # a screen no longer made would otherwise stay in the folder
        for old in out.glob("gp-*.png"):
            old.unlink()
        run = [
            sys.executable,
            "-m",
            "tests.real_app.run",
            str(scenario),
            "--out",
            str(out),
        ]
        if subprocess.run(run, cwd=config.ROOT, check=False).returncode != 0:
            print("The screenshots run failed: see its report.json and app.log")
            return 1

    tags = json.loads((out / "tags.json").read_text(encoding="utf-8"))
    keys = [m.key for m in ts_file.read(config.SOURCE).live()]
    found, uncovered = shots.match(out, tags, keys)
    # a screen showing nothing to translate (translators' names) is no
    # help on Crowdin: not sent, and taken down if it was
    untagged = [s.path.name for s in found if not s.tags]
    found = [s for s in found if s.tags]

    print(
        f"{len(found)} screens, {sum(len(s.tags) for s in found)} tags, "
        f"{len(keys) - len(uncovered)} of {len(keys)} strings shown"
    )
    if untagged:
        print(f"Left out, nothing to translate on them: {', '.join(untagged)}")
    (config.WORK / "not_in_screenshots.txt").write_text(
        "\n".join(f"{k[0]}: {k[1]}" for k in sorted(uncovered)), encoding="utf-8"
    )
    if not args.upload:
        print("Not uploaded: --upload sends them to Crowdin")
        return 0

    client, _, strings = _crowdin()
    id_of = {s.key: s.id for s in strings}
    existing = client.screenshots()

    # what was sent last time: a screen the same as then is left as it is
    sent_path = config.WORK / "screenshots_sent.json"
    sent = json.loads(sent_path.read_text("utf-8")) if sent_path.exists() else {}
    counts = {"sent": 0, "tagged": 0, "same": 0}
    started = time.monotonic()

    for shot in found:
        name = shot.path.name
        tags = sorted((id_of[k], r) for k, r in shot.tags if k in id_of)
        image_hash = hashlib.sha256(shot.path.read_bytes()).hexdigest()
        tags_hash = hashlib.sha256(json.dumps(tags).encode()).hexdigest()
        last = sent.get(name, {})
        sid = existing.get(name)

        if (
            sid is not None
            and last.get("id") == sid
            and last.get("image") == image_hash
        ):
            if last.get("tags") == tags_hash:
                counts["same"] += 1
                continue
            client.replace_tags(sid, tags)
            counts["tagged"] += 1
        else:
            sid = client.put_screenshot(name, client.upload_storage(shot.path), sid)
            client.replace_tags(sid, tags)
            counts["sent"] += 1
            print(f"  {name}: {len(tags)} tags")

        sent[name] = {"id": sid, "image": image_hash, "tags": tags_hash}
        sent_path.write_text(json.dumps(sent, indent=1), encoding="utf-8")

    print(
        f"{counts['sent']} sent, {counts['tagged']} only tags changed, "
        f"{counts['same']} unchanged, in {time.monotonic() - started:.0f} s"
    )

    # only once every new one is up
    made = {s.path.name for s in found}
    for name, sid in existing.items():
        if name in made:
            continue
        if name.startswith("gp-"):
            client.delete_screenshot(sid)
            print(f"  {name}: deleted, no longer made")
        elif args.delete_others:
            client.delete_screenshot(sid)
            print(f"  {name}: deleted, put up by hand")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    langs = argparse.ArgumentParser(add_help=False)
    langs.add_argument("--lang", nargs="*", help="language codes, all if none")

    p = sub.add_parser(
        "pull",
        parents=[langs],
        help="approved translations and suggestions from Crowdin",
    )
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser(
        "push", parents=[langs], help="send AI translations to Crowdin for review"
    )
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true", help="count, send nothing")
    p.set_defaults(func=cmd_push)

    p = sub.add_parser(
        "merge", parents=[langs], help="rebuild the languages against en_US.ts"
    )
    p.add_argument("--prune", action="store_true", help="drop the vanished hints")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("ai", parents=[langs], help="AI-translate what is missing")
    p.add_argument("--provider", help="claude, codex, openrouter (or fake)")
    p.add_argument(
        "--limit", type=int, default=0, help="at most this many strings a language"
    )
    p.add_argument("--batch-size", type=int)
    p.add_argument("--parallel", type=int)
    p.add_argument("--retranslate-ai", action="store_true", help="redo AI strings too")
    p.add_argument(
        "--fix-consistency",
        action="store_true",
        help="also ask again the AI strings of earlier runs that disagree "
        "with the strings they go with",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="write the prompts, ask no one"
    )
    p.set_defaults(func=cmd_ai)

    p = sub.add_parser(
        "review",
        parents=[langs],
        help="a second look at the AI translations, whole file in view",
    )
    p.add_argument("--provider", help="claude, codex, openrouter (or fake)")
    p.add_argument(
        "--again", action="store_true", help="also the strings reviewed before"
    )
    p.add_argument(
        "--report-only", action="store_true", help="change nothing, only report"
    )
    p.add_argument("--dry-run", action="store_true", help="write the prompt only")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("check", parents=[langs], help="QA every translation")
    p.add_argument("--warnings", action="store_true", help="list warnings too")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("screenshots", help="context screenshots for Crowdin")
    p.add_argument("--no-run", action="store_true", help="use the last run's pictures")
    p.add_argument("--upload", action="store_true", help="send them to Crowdin")
    p.add_argument(
        "--delete-others",
        action="store_true",
        help="with --upload: also delete the screenshots put up by hand",
    )
    p.set_defaults(func=cmd_screenshots)

    p = sub.add_parser("stats", help="write languages_progress.py")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    return args.func(config.load(), args)


if __name__ == "__main__":
    sys.exit(main())
