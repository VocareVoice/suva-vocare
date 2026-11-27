"""Add one ruling by its number: fetch it from entscheidsuche.ch, store it, classify and triage it.

The same steps as `python -m suva.fetch` + `suva load` + `suva classify` + `suva triage`, for a
single docket. Summaries stay on demand (the ruling page's button), as for every other ruling.
"""

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from suva import classify, db, triage
from suva.fetch.entscheidsuche import Client, pick_duplicates
from suva.fetch.parse import build_record
from suva.llm import LLMClient

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")  # same cache as `python -m suva.fetch`
# 8C_129/2025; also accepted: 8c 129/2025, 8C-129-2025, 8C.129/2025
DOCKET_RE = re.compile(r"^\s*(\d{1,2}[A-Z]{1,2})[\s_.-]*(\d{1,5})\s*[/-]\s*(\d{4})\s*$", re.I)


class NotFound(LookupError):
    """entscheidsuche.ch has no Federal Supreme Court ruling with this number."""


@dataclass
class Added:
    docket: str
    created: bool  # False: it was in the database already, nothing was done
    errors: list[str] = field(default_factory=list)  # pipeline steps that failed


def normalise(raw: str) -> str | None:
    """`8c 129/2025` -> `8C_129/2025`; None when it is not a ruling number."""
    match = DOCKET_RE.match(raw)
    if match is None:
        return None
    division, number, year = match.groups()
    return f"{division.upper()}_{int(number)}/{year}"


def add_ruling(
    conn: sqlite3.Connection, docket: str, llm: LLMClient, raw_dir: Path = RAW_DIR
) -> Added:
    """Store ruling `docket` (normalised) and run classification and triage on it. The ruling
    is kept when a model step fails; the step can be rerun with `suva classify` / `suva triage`."""
    if db.get_ruling(conn, docket) is not None:
        return Added(docket, created=False)

    client = Client(raw_dir)
    try:
        entries = client.find(docket)
        if not entries:
            raise NotFound(docket)
        picked = pick_duplicates(client, entries)
        # The same number twice with different dates would be two decisions; take the newest.
        entry, meta = max(picked, key=lambda pair: pair[0].decision_date)
        record = build_record(entry, meta, client.fetch(entry, "html").decode("utf-8"))
    finally:
        client.close()
    with conn:
        db.upsert_ruling(conn, record)

    added = Added(docket, created=True)
    for name, run, save in (
        ("classification", classify.classify, classify.save),
        ("triage", triage.triage, triage.save),
    ):
        try:
            save(conn, docket, run(conn, docket, llm))
        except Exception as exc:  # noqa: BLE001 - keep the ruling, report the failed step
            logger.exception("%s of %s failed", name, docket)
            added.errors.append(f"{name}: {exc}")
    return added
