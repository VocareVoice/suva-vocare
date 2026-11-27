import argparse
from dataclasses import asdict
from pathlib import Path

from suva import classify, db, summarize, triage
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

    imp = commands.add_parser("import-triage", help="load triage results from export-triage")
    imp.add_argument("path", type=Path)

    cls = commands.add_parser(
        "classify",
        help="classify every ruling without a result of the current prompt version: Apertus "
        "for rulings that pass the triage pre-filter, the subject line for the rest",
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

    summ = commands.add_parser("summarize", help="summarise one ruling in German and French")
    summ.add_argument("docket")

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
            db.save_triage(
                conn,
                docket,
                score=result.score,
                label=result.label,
                reasoning=result.reasoning,
                model=result.model,
                prompt_version=triage.PROMPT_VERSION,
            )
            print(f"{docket}: {result.score} {result.label}")
        if failed:
            raise SystemExit(f"{failed} rulings failed; run triage again to retry them")
    elif args.command == "export-triage":
        count = db.export_triage(conn, args.path, date_from=args.date_from, date_to=args.date_to)
        print(f"Wrote {count} triage results to {args.path}")
    elif args.command == "import-triage":
        print(f"Loaded {db.import_triage(conn, args.path)} triage results from {args.path}")
    elif args.command == "classify":
        llm = LLMClient(settings)
        dockets = db.unclassified_dockets(
            conn,
            date_from=args.date_from,
            date_to=args.date_to,
            prompt_version=classify.PROMPT_VERSION,
        )
        print(f"Classifying {len(dockets)} rulings with {llm.model}")
        failed = 0
        for docket, result in classify.classify_batch(conn, dockets, llm, workers=args.workers):
            if isinstance(result, Exception):
                failed += 1
                print(f"{docket}: failed ({result!r})")
                continue
            db.save_classification(
                conn,
                docket,
                **asdict(result),
                prompt_version=classify.PROMPT_VERSION,
            )
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
        for lang, text in summarize.summarize(conn, args.docket, llm).items():
            db.save_summary(
                conn,
                args.docket,
                lang=lang,
                text=text,
                model=llm.model,
                prompt_version=summarize.PROMPT_VERSION,
            )
            print(f"--- {lang} ---\n{text}\n")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("suva.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
