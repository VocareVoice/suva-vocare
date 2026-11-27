"""python -m suva.fetch.published --until 2026-07-03

Adds the date bger.ch published each ruling to the corpus records (`publication_date`).

bger.ch lists the rulings it publishes each day ("Liste der am ... neu aufgenommenen
Entscheide"), but serves the lists only behind an hCaptcha (www.bger.ch) or on a host whose
robots.txt disallows crawling (relevancy.bger.ch). The entscheidsuche.ch mirror reads each day's
list in its crawl of the next evening and logs every crawl job: an `Index_*.json` of the files
the job added, until June 2026, and after that only full `Job_*.json` snapshots, in which the
files the job added have status `neu` and no `quelle`. A ruling's publication date is the day
before the first job that added it. On bger.ch's list of 15 April 2026 this matches 49 of 49
rulings; when the mirror skips a day, the date comes out a day or two late.

Snapshots are about 50 MB each, so they are read only up to `--until`; rulings the mirror added
later keep `publication_date` empty. Downloads are cached under `--raw-dir`.
"""

import argparse
import json
import re
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from suva.config import get_settings
from suva.db import open_corpus
from suva.fetch.__main__ import write_corpus
from suva.fetch.entscheidsuche import Client

DOCS_URL = "https://entscheidsuche.ch/docs/"
JOB_RE = re.compile(r"(?:Index|Job)_(\d{4}-\d\d-\d\d)_(\d\d:\d\d:\d\d)_446973-45-(\d+)\.json")
LISTED_RE = re.compile(rf'href="\./({JOB_RE.pattern})"')
ARCHIVE_RE = re.compile(r'href="(\d{4})\.zip"')
FILE_RE = re.compile(r"CH_BGer_\d{3}_(\d+[A-Z]+)-(\d+)-(\d{4})_(\d{4}-\d\d-\d\d)\.json$")
SPACING = 2  # seconds between downloads

Key = tuple[str, str]  # (docket, decision date)


def _key(name: str) -> Key | None:
    match = FILE_RE.search(name)
    if match is None:
        return None
    prefix, number, year, decided = match.groups()
    return f"{prefix}_{number}/{year}", decided


class Mirror:
    def __init__(self, raw_dir: Path):
        self.client = Client(raw_dir)
        self.cache = raw_dir / "entscheidsuche"

    def get(self, path: str) -> bytes:
        """A file under docs/, cached."""
        cache_path = self.cache / path
        fresh = not cache_path.exists()
        body = self.client.get(DOCS_URL + path, cache_path)
        if fresh:
            time.sleep(SPACING)
        return body

    def listing(self, folder: str) -> str:
        """The directory listing of docs/`folder`/, always downloaded again."""
        body = self.client.get(DOCS_URL + folder + "/", self.cache / folder / "listing.html", True)
        time.sleep(SPACING)
        return body.decode("utf-8")

    def jobs(self, folder: str) -> list[tuple[str, datetime, int]]:
        """(file name, start time, job number) of every job file in docs/`folder`/CH_BGer/,
        oldest first."""
        names = {match[0] for match in LISTED_RE.findall(self.listing(folder + "/CH_BGer"))}
        return sorted(((name, *_job(name)) for name in names), key=lambda job: job[1])


def first_seen(mirror: Mirror, since: int, until: date) -> dict[Key, datetime]:
    """When the mirror first added each ruling decided in year `since` or later."""
    seen: dict[Key, datetime] = {}

    def add(names, when: datetime) -> None:
        for name in names:
            key = _key(name)
            if key and key[1][:4] >= str(since) and (key not in seen or when < seen[key]):
                seen[key] = when

    archive = mirror.listing("Index/CH_BGer/Archiv")
    for year in sorted({int(y) for y in ARCHIVE_RE.findall(archive) if int(y) >= since}):
        mirror.get(f"Index/CH_BGer/Archiv/{year}.zip")
        with zipfile.ZipFile(mirror.cache / f"Index/CH_BGer/Archiv/{year}.zip") as zf:
            for member in zf.namelist():
                if JOB_RE.fullmatch(member):
                    actions = json.loads(zf.read(member))["actions"]
                    add((n for n, a in actions.items() if a == "new"), _job(member)[0])

    indexed = mirror.jobs("Index")
    for name, start, _ in indexed:
        actions = json.loads(mirror.get(f"Index/CH_BGer/{name}"))["actions"]
        add((n for n, a in actions.items() if a == "new"), start)

    last_indexed = max((number for *_, number in indexed), default=0)
    for name, start, number in mirror.jobs("Jobs"):
        if number <= last_indexed or start.date() > until:
            continue
        print(f"reading snapshot {name}", file=sys.stderr)
        files = json.loads(mirror.get(f"Jobs/CH_BGer/{name}"))["dateien"]
        add((n for n, f in files.items() if f.get("status") == "neu" and "quelle" not in f), start)
    return seen


def _job(name: str) -> tuple[datetime, int]:
    """Start time and number of a job from its file name."""
    day, clock, number = JOB_RE.fullmatch(name).groups()
    return datetime.fromisoformat(f"{day}T{clock}"), int(number)


def publication_date(added: datetime) -> str:
    return (added.date() - timedelta(days=1)).isoformat()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m suva.fetch.published", description=__doc__)
    parser.add_argument(
        "--until",
        type=date.fromisoformat,
        required=True,
        help="last day whose crawl snapshot is read (about 50 MB per day)",
    )
    parser.add_argument("--corpus", type=Path, default=get_settings().corpus_path)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)

    with open_corpus(args.corpus) as f:
        records = [json.loads(line) for line in f if line.strip()]
    since = min(int(r["decision_date"][:4]) for r in records)
    mirror = Mirror(args.raw_dir)
    try:
        seen = first_seen(mirror, since, args.until)
    finally:
        mirror.client.close()

    dated = 0
    for record in records:
        added = seen.get((record["docket"], record["decision_date"]))
        record["publication_date"] = publication_date(added) if added else None
        dated += added is not None
    write_corpus(args.corpus, records)
    print(f"{dated} of {len(records)} rulings have a publication date", file=sys.stderr)


if __name__ == "__main__":
    main()
