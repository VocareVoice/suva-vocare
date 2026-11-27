"""python -m suva.fetch --from 2026-04-01 --to 2026-06-30

Downloads every ruling decided in the date range (cached under --raw-dir, so
re-runs and interrupted crawls never fetch a file twice) and merges them into
the corpus file, replacing any records already there for that date range.
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from suva.config import get_settings
from suva.db import open_corpus
from suva.fetch.entscheidsuche import Client, Entry, pick_duplicates
from suva.fetch.parse import build_record


def load_existing(path: Path, start: date, end: date) -> list[dict]:
    if not path.exists():
        return []
    with open_corpus(path) as f:
        records = [json.loads(line) for line in f if line.strip()]
    return [r for r in records if not start <= date.fromisoformat(r["decision_date"]) <= end]


def write_corpus(path: Path, records: list[dict]) -> None:
    records.sort(key=lambda r: (r["decision_date"], r["docket"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".part-{path.name}")
    with open_corpus(tmp, "w") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m suva.fetch", description=__doc__)
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, default=get_settings().corpus_path)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--refresh-index",
        action="store_true",
        help="re-download the mirror's directory listing to pick up new rulings",
    )
    args = parser.parse_args(argv)

    client = Client(args.raw_dir)
    try:
        entries = client.list_entries(args.start, args.end, args.refresh_index)
        print(f"{len(entries)} files listed for {args.start}..{args.end}", file=sys.stderr)

        done = Counter()

        def fetch(entry: Entry) -> None:
            client.fetch(entry, "json")
            client.fetch(entry, "html")
            done["n"] += 1
            if done["n"] % 250 == 0:
                print(f"  fetched {done['n']}/{len(entries)}", file=sys.stderr)

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            list(pool.map(fetch, entries))

        records = [
            build_record(entry, meta, client.fetch(entry, "html").decode("utf-8"))
            for entry, meta in pick_duplicates(client, entries)
        ]
    finally:
        client.close()

    write_corpus(args.out, load_existing(args.out, args.start, args.end) + records)
    print(f"{len(records)} rulings written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
