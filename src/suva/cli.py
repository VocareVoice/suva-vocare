import argparse
import json
from pathlib import Path

from suva import classify, db, feedback, summarize, triage
from suva.config import get_settings
from suva.llm import LLMClient


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="suva")
    commands = parser.add_subparsers(dest="command", required=True)

    load = commands.add_parser("load", help="ingest a rulings.jsonl corpus into the database")
    load.add_argument("path", nargs="?", type=Path, default=settings.corpus_path)
    load.add_argument(
        "--demo",
        action="store_true",
        help="load the bundled demo seed instead of a corpus: 14 real rulings with "
        "hand-written triage and Suva reference summaries (refuses a database with real data)",
    )

    tri = commands.add_parser(
        "triage", help="score every ruling without a result of the current prompt version"
    )
    tri.add_argument("--from", dest="date_from", help="first decision date, YYYY-MM-DD")
    tri.add_argument("--to", dest="date_to", help="last decision date, YYYY-MM-DD")
    tri.add_argument("--workers", type=int, default=8, help="parallel LLM calls")

    export = commands.add_parser("export-triage", help="write the latest triage results as JSONL")
    export.add_argument("path", type=Path)
    export.add_argument("--from", dest="date_from")
    export.add_argument("--to", dest="date_to")

    export_rel = commands.add_parser(
        "export-relevant",
        help="write the rulings with a triage score of at least --min-score, highest score "
        "first, as one comma-separated line of dockets (PATH.txt) and as a table (PATH.csv)",
    )
    export_rel.add_argument("path", type=Path, help="output path; .txt and .csv are added")
    export_rel.add_argument("--min-score", type=int, default=triage.RELEVANCE_THRESHOLD)
    export_rel.add_argument("--from", dest="date_from", help="first date, YYYY-MM-DD")
    export_rel.add_argument("--to", dest="date_to", help="last date, YYYY-MM-DD")
    export_rel.add_argument(
        "--by",
        choices=("decision", "publication"),
        default="decision",
        help="date that --from and --to apply to (publication: python -m suva.fetch.published)",
    )

    imp = commands.add_parser("import-triage", help="load triage results from export-triage")
    imp.add_argument("path", type=Path)

    cls = commands.add_parser(
        "classify",
        help="classify every ruling without a result of the current prompt version: Apertus "
        "for rulings of the social-law divisions (8x, 9x), branch 'other' for the rest",
    )
    cls.add_argument("--from", dest="date_from", help="first decision date, YYYY-MM-DD")
    cls.add_argument("--to", dest="date_to", help="last decision date, YYYY-MM-DD")
    cls.add_argument("--workers", type=int, default=8, help="parallel LLM calls")

    export_cls = commands.add_parser(
        "export-classification", help="write the latest classifications as JSONL"
    )
    export_cls.add_argument("path", type=Path)
    export_cls.add_argument("--from", dest="date_from")
    export_cls.add_argument("--to", dest="date_to")

    imp_cls = commands.add_parser(
        "import-classification", help="load classifications from export-classification"
    )
    imp_cls.add_argument("path", type=Path)

    summ = commands.add_parser(
        "summarize", help="summarise one ruling in German and French, with headlines"
    )
    summ.add_argument("docket")

    summ_all = commands.add_parser(
        "summarize-relevant",
        help="summarise (with headlines) every ruling with a triage score of at least "
        "--min-score that has no summary of the current prompt version, highest score first",
    )
    heads = commands.add_parser(
        "headline-relevant",
        help="write only the German and French headlines of every ruling with a triage score of "
        "at least --min-score that has no headline of the current prompt version, highest "
        "score first (about a tenth of the calls of a summary)",
    )
    for sub in (summ_all, heads):
        sub.add_argument("--min-score", type=int, default=triage.RELEVANCE_THRESHOLD)
        sub.add_argument(
            "--limit", type=int, help="only the top N rulings, skipping those already done"
        )
        sub.add_argument("--from", dest="date_from", help="first decision date, YYYY-MM-DD")
        sub.add_argument("--to", dest="date_to", help="last decision date, YYYY-MM-DD")
        sub.add_argument("--workers", type=int, default=4, help="rulings in parallel")

    export_summ = commands.add_parser(
        "export-summaries", help="write the latest summaries and headlines as JSONL"
    )
    export_summ.add_argument("path", type=Path)
    export_summ.add_argument("--from", dest="date_from")
    export_summ.add_argument("--to", dest="date_to")

    export_files = commands.add_parser(
        "export-summary-files",
        help="write the latest summary of every ruling with a triage score of at least "
        "--min-score as one Markdown file per ruling and language, plus index.md",
    )
    export_files.add_argument("--out", type=Path, required=True, help="output directory")
    export_files.add_argument("--min-score", type=int, default=triage.RELEVANCE_THRESHOLD)
    export_files.add_argument("--from", dest="date_from", help="first decision date, YYYY-MM-DD")
    export_files.add_argument("--to", dest="date_to", help="last decision date, YYYY-MM-DD")

    imp_summ = commands.add_parser(
        "import-summaries", help="load summaries and headlines from export-summaries"
    )
    imp_summ.add_argument("path", type=Path)

    fb = commands.add_parser(
        "feedback-export",
        help="write the experts' score corrections, feedback and edited summaries (next to the "
        "generated text they replaced) as JSON, for the feedback-review skill (no LLM)",
    )
    fb.add_argument("--out", type=Path, required=True)
    fb.add_argument(
        "--generated",
        type=Path,
        nargs="*",
        help="export-summaries files holding the generated summaries that edits replaced "
        f"(default: {feedback.RESULTS_DIR}/{feedback.GENERATED_GLOB})",
    )

    serve = commands.add_parser("serve", help="run the API and web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    conn = db.connect(settings.db_path)

    if args.command == "load" and args.demo:
        try:
            print(f"Loaded {db.load_demo(conn)} demo rulings into {settings.db_path}")
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "load":
        print(f"Loaded {db.load_corpus(conn, args.path)} rulings into {settings.db_path}")
    elif args.command == "triage":
        llm = LLMClient(settings)
        dockets = db.untriaged_dockets(
            conn,
            date_from=args.date_from,
            date_to=args.date_to,
            prompt_version=triage.PROMPT_VERSION,
        )
        print(f"Triaging {len(dockets)} rulings with {llm.model}")
        failed = 0
        for docket, result in triage.triage_batch(conn, dockets, llm, workers=args.workers):
            if isinstance(result, Exception):
                failed += 1
                print(f"{docket}: failed ({result!r})")
                continue
            triage.save(conn, docket, result)
            print(f"{docket}: {result.score} {result.label}")
        if failed:
            raise SystemExit(f"{failed} rulings failed; run triage again to retry them")
    elif args.command == "export-triage":
        count = db.export_triage(conn, args.path, date_from=args.date_from, date_to=args.date_to)
        print(f"Wrote {count} triage results to {args.path}")
    elif args.command == "export-relevant":
        count = db.export_relevant(
            conn,
            args.path,
            min_score=args.min_score,
            date_from=args.date_from,
            date_to=args.date_to,
            by=f"{args.by}_date",
        )
        print(f"Wrote {count} rulings to {args.path.with_suffix('.txt')} and .csv")
    elif args.command == "import-triage":
        print(f"Loaded {db.import_triage(conn, args.path)} triage results from {args.path}")
    elif args.command == "classify":
        llm = LLMClient(settings)
        dockets = db.unclassified_dockets(
            conn,
            date_from=args.date_from,
            date_to=args.date_to,
            prompt_version=classify.VERSION,
        )
        print(f"Classifying {len(dockets)} rulings with {llm.model}")
        failed = 0
        for docket, result in classify.classify_batch(conn, dockets, llm, workers=args.workers):
            if isinstance(result, Exception):
                failed += 1
                print(f"{docket}: failed ({result!r})")
                continue
            classify.save(conn, docket, result)
            labels = " ".join([result.branch, result.primary, *result.secondary])
            print(f"{docket}: {labels} ({result.method})")
        if failed:
            raise SystemExit(f"{failed} rulings failed; run classify again to retry them")
    elif args.command == "export-classification":
        count = db.export_classification(
            conn, args.path, date_from=args.date_from, date_to=args.date_to
        )
        print(f"Wrote {count} classifications to {args.path}")
    elif args.command == "import-classification":
        count = db.import_classification(conn, args.path)
        print(f"Loaded {count} classifications from {args.path}")
    elif args.command == "summarize":
        llm = LLMClient(settings)
        result = summarize.summarize(conn, args.docket, llm)
        summarize.save(conn, args.docket, result, llm.model)
        for lang in summarize.LANGUAGES:
            print(f"--- {lang} ---\n{result.headlines.get(lang)}\n\n{result.summaries[lang]}\n")
    elif args.command in ("summarize-relevant", "headline-relevant"):
        headlines_only = args.command == "headline-relevant"
        version = summarize.HEADLINE_VERSION if headlines_only else summarize.PROMPT_VERSION
        llm = LLMClient(settings)
        dockets = db.dockets_to_summarize(
            conn,
            min_score=args.min_score,
            prompt_version=version,
            date_from=args.date_from,
            date_to=args.date_to,
            table="headlines" if headlines_only else "summaries",
            limit=args.limit,
        )
        task = "Writing headlines for" if headlines_only else "Summarising"
        print(f"{task} {len(dockets)} rulings with {llm.model}")
        failed = 0
        for docket, result in summarize.summarize_batch(
            conn, dockets, llm, workers=args.workers, headlines_only=headlines_only
        ):
            if isinstance(result, Exception):
                failed += 1
                print(f"{docket}: failed ({result!r})")
                continue
            summarize.save(conn, docket, result, llm.model)
            words = " / ".join(str(len(t.split())) for t in result.summaries.values())
            print(f"{docket}: {words + ' words; ' if words else ''}{result.headlines}")
        if failed:
            raise SystemExit(f"{failed} rulings failed; run {args.command} again to retry them")
    elif args.command == "export-summaries":
        count = db.export_summaries(conn, args.path, date_from=args.date_from, date_to=args.date_to)
        print(f"Wrote summaries and headlines of {count} rulings to {args.path}")
    elif args.command == "export-summary-files":
        rulings, files = db.export_summary_files(
            conn,
            args.out,
            min_score=args.min_score,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        print(f"Wrote {files} summary files of {rulings} rulings and index.md to {args.out}")
    elif args.command == "import-summaries":
        count = db.import_summaries(conn, args.path)
        print(f"Loaded {count} summaries and headlines from {args.path}")
    elif args.command == "feedback-export":
        generated = args.generated
        if generated is None:
            generated = sorted(feedback.RESULTS_DIR.glob(feedback.GENERATED_GLOB))
        data = feedback.export(conn, generated)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        counts = data["counts"]
        print(
            f"Wrote {counts['score_corrections']} score corrections, {counts['feedback_rows']} "
            f"feedback rows and {counts['edited_summaries']} edited summaries to {args.out}"
        )
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("suva.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
