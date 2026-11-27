"""SQLite knowledge base: rulings with FTS5 search, triage results, summaries and feedback."""

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


def load_corpus(conn: sqlite3.Connection, path: Path | str) -> int:
    """Upsert every ruling from a JSONL corpus file; returns the number of rulings read."""
    count = 0
    with conn, open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                upsert_ruling(conn, json.loads(line))
                count += 1
    return count


def fts_query(text: str) -> str:
    """Turn free user input into a safe FTS5 query: every token must match, as a phrase."""
    tokens = text.split()
    return " ".join('"' + token.replace('"', '""') + '"' for token in tokens)


def list_rulings(
    conn: sqlite3.Connection,
    *,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_score: int | None = None,
    label: str | None = None,
    sort: str = "score",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    where, params = [], []
    if q and q.strip():
        where.append("r.id IN (SELECT rowid FROM rulings_fts WHERE rulings_fts MATCH ?)")
        params.append(fts_query(q))
    date = "COALESCE(r.publication_date, r.decision_date)"
    if date_from:
        where.append(f"{date} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date} <= ?")
        params.append(date_to)
    if min_score is not None:
        where.append("t.score >= ?")
        params.append(min_score)
    if label:
        where.append("t.label = ?")
        params.append(label)

    order = {
        "score": "t.score IS NULL, t.score DESC, r.decision_date DESC",
        "date": f"{date} DESC, r.docket",
    }[sort]
    base = f"""
        FROM rulings r
        LEFT JOIN triage t ON {_LATEST_TRIAGE}
        {"WHERE " + " AND ".join(where) if where else ""}
    """
    total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT r.docket, r.decision_date, r.publication_date, r.division, r.language,
               r.title, r.url, t.score, t.label,
               EXISTS (SELECT 1 FROM summaries s WHERE s.docket = r.docket) AS has_summary
        {base}
        ORDER BY {order}
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return total, [{**dict(row), "has_summary": bool(row["has_summary"])} for row in rows]


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
