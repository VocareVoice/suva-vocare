"""SQLite knowledge base: rulings with FTS5 search, triage results, summaries and feedback."""

import gzip
import io
import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS rulings (
    id INTEGER PRIMARY KEY,
    docket TEXT NOT NULL UNIQUE,
    decision_date TEXT,
    publication_date TEXT,
    division TEXT,
    language TEXT CHECK (language IN ('de', 'fr', 'it')),
    title TEXT,
    url TEXT,
    text TEXT NOT NULL DEFAULT '',
    source TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS rulings_fts USING fts5(
    docket, title, text,
    content='rulings', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS rulings_ai AFTER INSERT ON rulings BEGIN
    INSERT INTO rulings_fts(rowid, docket, title, text)
    VALUES (new.id, new.docket, new.title, new.text);
END;
CREATE TRIGGER IF NOT EXISTS rulings_ad AFTER DELETE ON rulings BEGIN
    INSERT INTO rulings_fts(rulings_fts, rowid, docket, title, text)
    VALUES ('delete', old.id, old.docket, old.title, old.text);
END;
CREATE TRIGGER IF NOT EXISTS rulings_au AFTER UPDATE ON rulings BEGIN
    INSERT INTO rulings_fts(rulings_fts, rowid, docket, title, text)
    VALUES ('delete', old.id, old.docket, old.title, old.text);
    INSERT INTO rulings_fts(rowid, docket, title, text)
    VALUES (new.id, new.docket, new.title, new.text);
END;

CREATE TABLE IF NOT EXISTS triage (
    id INTEGER PRIMARY KEY,
    docket TEXT NOT NULL REFERENCES rulings(docket) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    label TEXT NOT NULL CHECK (label IN ('relevant', 'not_relevant')),
    reasoning TEXT NOT NULL,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS triage_docket ON triage(docket);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY,
    docket TEXT NOT NULL REFERENCES rulings(docket) ON DELETE CASCADE,
    lang TEXT NOT NULL CHECK (lang IN ('de', 'fr')),
    text TEXT NOT NULL,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS summaries_docket ON summaries(docket, lang);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    docket TEXT NOT NULL REFERENCES rulings(docket) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK (verdict IN ('relevant', 'not_relevant')),
    corrected_score INTEGER CHECK (corrected_score BETWEEN 0 AND 100),
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS feedback_docket ON feedback(docket);
"""

RULING_FIELDS = (
    "docket",
    "decision_date",
    "publication_date",
    "division",
    "language",
    "title",
    "url",
    "text",
    "source",
)

# Latest triage row per ruling; triage and summaries keep history, newest id wins.
_LATEST_TRIAGE = "t.id = (SELECT MAX(id) FROM triage WHERE docket = r.docket)"
_HAS_SUMMARY = "(SELECT 1 FROM summaries s WHERE s.docket = r.docket)"


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_ruling(conn: sqlite3.Connection, ruling: dict[str, Any]) -> None:
    values = {field: ruling.get(field) for field in RULING_FIELDS}
    values["text"] = values["text"] or ""
    columns = ", ".join(RULING_FIELDS)
    placeholders = ", ".join(f":{f}" for f in RULING_FIELDS)
    updates = ", ".join(f"{f} = excluded.{f}" for f in RULING_FIELDS if f != "docket")
    conn.execute(
        f"INSERT INTO rulings ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(docket) DO UPDATE SET {updates}",
        values,
    )


def open_corpus(path: Path | str, mode: str = "r") -> io.TextIOBase:
    """Open a JSONL corpus as text, gzip-compressed when the name ends in `.gz`."""
    if str(path).endswith(".gz"):
        # mtime=0 keeps the compressed bytes stable when the content is unchanged.
        return io.TextIOWrapper(gzip.GzipFile(path, mode + "b", mtime=0), encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def load_corpus(conn: sqlite3.Connection, path: Path | str) -> int:
    """Upsert every ruling from a JSONL corpus file; returns the number of rulings read."""
    count = 0
    with conn, open_corpus(path) as f:
        for line in f:
            if line.strip():
                upsert_ruling(conn, json.loads(line))
                count += 1
    return count


DEMO_PATH = Path(__file__).parent / "demo" / "rulings.json"
DEMO_SOURCE = "demo"


def load_demo(conn: sqlite3.Connection, path: Path | str = DEMO_PATH) -> int:
    """(Re)load the demo seed: real rulings with hand-written triage and Suva's human
    reference summaries, all marked with source "demo". Refuses to mix with a real corpus."""
    real = conn.execute("SELECT COUNT(*) FROM rulings WHERE source IS NOT ?", (DEMO_SOURCE,))
    if real.fetchone()[0]:
        raise ValueError("database already holds non-demo rulings; use another DB_PATH")
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    with conn:
        conn.execute("DELETE FROM rulings")
        for record in records:
            upsert_ruling(conn, {**record, "source": DEMO_SOURCE})
            docket = record["docket"]
            if triage := record.get("triage"):
                conn.execute(
                    "INSERT INTO triage (docket, score, label, reasoning, model, prompt_version) "
                    "VALUES (?, ?, ?, ?, 'demo', 'demo')",
                    (docket, triage["score"], triage["label"], triage["reasoning"]),
                )
            for lang, text in record.get("summaries", {}).items():
                conn.execute(
                    "INSERT INTO summaries (docket, lang, text, model, prompt_version) "
                    "VALUES (?, ?, ?, 'Suva-Referenz (Demo)', 'demo')",
                    (docket, lang, text),
                )
    return len(records)


def fts_query(text: str) -> str:
    """Turn free user input into a safe FTS5 query: every token must match, as a phrase."""
    tokens = text.split()
    return " ".join('"' + token.replace('"', '""') + '"' for token in tokens)


_DATE = "COALESCE(r.publication_date, r.decision_date)"
_FROM = f"FROM rulings r LEFT JOIN triage t ON {_LATEST_TRIAGE}"


def _filters(
    *,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    label: str | None = None,
    division: str | None = None,
    language: str | None = None,
    has_summary: bool | None = None,
) -> tuple[str, list[Any]]:
    """WHERE clause (or "") and parameters for the list filters, over `_FROM`."""
    where, params = [], []
    if q and q.strip():
        where.append("r.id IN (SELECT rowid FROM rulings_fts WHERE rulings_fts MATCH ?)")
        params.append(fts_query(q))
    for clause, value in [
        (f"{_DATE} >= ?", date_from),
        (f"{_DATE} <= ?", date_to),
        ("t.score >= ?", min_score),
        ("t.score <= ?", max_score),
        ("t.label = ?", label),
        ("r.division = ?", division),
        ("r.language = ?", language),
    ]:
        if value is not None and value != "":
            where.append(clause)
            params.append(value)
    if has_summary is not None:
        where.append(f"{'' if has_summary else 'NOT '}EXISTS {_HAS_SUMMARY}")
    return ("WHERE " + " AND ".join(where) if where else ""), params


# Docket order: year, division prefix, then number (8C_9/2025 before 8C_129/2025).
_DOCKET_ORDER = (
    "substr(r.docket, instr(r.docket, '/') + 1) {d}, "
    "substr(r.docket, 1, instr(r.docket, '_') - 1) {d}, "
    "CAST(substr(r.docket, instr(r.docket, '_') + 1) AS INTEGER) {d}"
)
SORTS = {
    "score": "t.score IS NULL, t.score {d}, r.decision_date DESC",
    "date": f"{_DATE} {{d}}, r.docket",
    "docket": _DOCKET_ORDER,
    "title": "r.title IS NULL, r.title COLLATE NOCASE {d}, t.score DESC",
    "language": "r.language {d}, t.score DESC",
    "summary": f"EXISTS {_HAS_SUMMARY} {{d}}, t.score DESC",
}


def list_rulings(
    conn: sqlite3.Connection,
    *,
    sort: str = "score",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    **filters: Any,
) -> tuple[int, list[dict[str, Any]]]:
    """One page of rulings matching `filters` (see `_filters`), plus the total match count."""
    where, params = _filters(**filters)
    total = conn.execute(f"SELECT COUNT(*) {_FROM} {where}", params).fetchone()[0]
    order_by = SORTS[sort].format(d="ASC" if order == "asc" else "DESC")
    rows = conn.execute(
        f"""
        SELECT r.docket, r.decision_date, r.publication_date, r.division, r.language,
               r.title, r.url, t.score, t.label, t.reasoning,
               EXISTS {_HAS_SUMMARY} AS has_summary,
               (SELECT verdict FROM feedback f WHERE f.docket = r.docket
                ORDER BY f.id DESC LIMIT 1) AS feedback_verdict
        {_FROM} {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return total, [{**dict(row), "has_summary": bool(row["has_summary"])} for row in rows]


def list_stats(conn: sqlite3.Connection, **filters: Any) -> dict[str, int]:
    """Counts over every ruling matching `filters`, not just one page."""
    where, params = _filters(**filters)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(t.label = 'relevant'), 0) AS relevant,
               COALESCE(SUM(EXISTS {_HAS_SUMMARY}), 0) AS with_summary,
               COALESCE(SUM(t.label = 'relevant' AND NOT EXISTS {_HAS_SUMMARY}), 0)
                   AS relevant_without_summary
        {_FROM} {where}
        """,
        params,
    ).fetchone()
    return dict(row)


def facets(conn: sqlite3.Connection) -> dict[str, Any]:
    """Filter options for the UI: distinct divisions and languages with counts, date range."""

    def counts(column: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"SELECT {column} AS value, COUNT(*) AS count FROM rulings "
            f"WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY {column}"
        )
        return [dict(row) for row in rows]

    date = "COALESCE(publication_date, decision_date)"
    stats = conn.execute(
        f"SELECT COUNT(*) AS total, MIN({date}) AS date_min, MAX({date}) AS date_max, "
        "SUM(source = ?) > 0 AS demo FROM rulings",
        (DEMO_SOURCE,),
    ).fetchone()
    return {
        "total": stats["total"],
        "date_min": stats["date_min"],
        "date_max": stats["date_max"],
        "demo": bool(stats["demo"]),
        "divisions": counts("division"),
        "languages": counts("language"),
    }


def get_ruling(conn: sqlite3.Connection, docket: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {', '.join(RULING_FIELDS)} FROM rulings WHERE docket = ?", (docket,)
    ).fetchone()
    return dict(row) if row else None


def get_ruling_detail(conn: sqlite3.Connection, docket: str) -> dict[str, Any] | None:
    ruling = get_ruling(conn, docket)
    if ruling is None:
        return None
    triage = conn.execute(
        "SELECT score, label, reasoning, model, prompt_version, created_at FROM triage "
        "WHERE docket = ? ORDER BY id DESC LIMIT 1",
        (docket,),
    ).fetchone()
    summaries = {
        row["lang"]: dict(row)
        for row in conn.execute(
            "SELECT lang, text, model, prompt_version, created_at FROM summaries "
            "WHERE docket = ? ORDER BY id",
            (docket,),
        )
    }
    feedback = conn.execute(
        "SELECT verdict, corrected_score, comment, created_at FROM feedback "
        "WHERE docket = ? ORDER BY id DESC",
        (docket,),
    ).fetchall()
    return {
        **ruling,
        "triage": dict(triage) if triage else None,
        "summaries": {lang: summaries.get(lang) for lang in ("de", "fr")},
        "feedback": [dict(row) for row in feedback],
    }


def untriaged_dockets(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT docket FROM rulings r WHERE NOT EXISTS "
        "(SELECT 1 FROM triage t WHERE t.docket = r.docket) ORDER BY docket"
    )
    return [row["docket"] for row in rows]


def save_triage(
    conn: sqlite3.Connection,
    docket: str,
    *,
    score: int,
    label: str,
    reasoning: str,
    model: str | None,
    prompt_version: str | None,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO triage (docket, score, label, reasoning, model, prompt_version) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (docket, score, label, reasoning, model, prompt_version),
        )


def save_summary(
    conn: sqlite3.Connection,
    docket: str,
    *,
    lang: str,
    text: str,
    model: str | None,
    prompt_version: str | None,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO summaries (docket, lang, text, model, prompt_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (docket, lang, text, model, prompt_version),
        )


def save_feedback(
    conn: sqlite3.Connection,
    docket: str,
    *,
    verdict: str,
    corrected_score: int | None = None,
    comment: str | None = None,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO feedback (docket, verdict, corrected_score, comment) VALUES (?, ?, ?, ?)",
            (docket, verdict, corrected_score, comment),
        )
