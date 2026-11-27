"""SQLite knowledge base: rulings with FTS5 search, triage results, summaries, headlines and
feedback."""

import csv
import gzip
import io
import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

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
    reasoning_de TEXT NOT NULL,
    reasoning_fr TEXT,
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

# Created on connect like the rest of the schema, so databases from before it existed still load.
CLASSIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS classification (
    id INTEGER PRIMARY KEY,
    docket TEXT NOT NULL REFERENCES rulings(docket) ON DELETE CASCADE,
    branch TEXT NOT NULL,
    primary_category TEXT NOT NULL,
    secondary TEXT NOT NULL DEFAULT '[]',
    statutes TEXT NOT NULL DEFAULT '[]',
    precedents TEXT NOT NULL DEFAULT '[]',
    outcome TEXT,
    flags TEXT NOT NULL DEFAULT '[]',
    method TEXT NOT NULL CHECK (method IN ('llm', 'subject', 'rule')),
    rationale TEXT,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS classification_docket ON classification(docket);
"""

# One line per ruling and language saying what the Court decided, written with the summaries.
HEADLINES_SCHEMA = """
CREATE TABLE IF NOT EXISTS headlines (
    id INTEGER PRIMARY KEY,
    docket TEXT NOT NULL REFERENCES rulings(docket) ON DELETE CASCADE,
    lang TEXT NOT NULL CHECK (lang IN ('de', 'fr')),
    text TEXT NOT NULL,
    model TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS headlines_docket ON headlines(docket, lang);
"""

# LLM summaries of the experts' score corrections ("Anpassungen"), one per run and language;
# the page shows the newest. Input for a later step that feeds them back into the triage prompt.
ADJUSTMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS adjustment_summaries (
    id INTEGER PRIMARY KEY,
    lang TEXT NOT NULL CHECK (lang IN ('de', 'fr')),
    text TEXT NOT NULL,
    adjustment_count INTEGER NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# The agent side panel: one chat per browser, its messages (user turns, tool steps, answers)
# and the summary changes the agent proposed, which only take effect when the user applies them.
AGENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS chat_messages_chat ON chat_messages(chat_id, id);

CREATE TABLE IF NOT EXISTS summary_proposals (
    id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    docket TEXT NOT NULL REFERENCES rulings(docket) ON DELETE CASCADE,
    lang TEXT NOT NULL CHECK (lang IN ('de', 'fr')),
    text TEXT NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'applied', 'discarded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- The agent's knowledge (suva.agent.memory): one text, NULL for the default text.
CREATE TABLE IF NOT EXISTS agent_knowledge (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT,
    updated_by TEXT NOT NULL DEFAULT 'default' CHECK (updated_by IN ('default', 'user', 'agent')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# prompt_version of a summary a user edited by hand or applied from an agent proposal. The
# summary pipeline never overwrites these (see `dockets_to_summarize`).
EDITED_VERSION = "edited"

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

# Latest triage row per ruling; triage keeps history, newest id wins. Summaries keep one row per
# ruling and language (`save_summary` replaces).
# A score set by a legal expert (model EXPERT_MODEL) wins over every model result, also over
# later triage runs, until the expert resets it (`clear_expert_score`).
EXPERT_MODEL = "expert"
_TRIAGE_ORDER = f"ORDER BY (model = '{EXPERT_MODEL}') DESC, id DESC LIMIT 1"
_LATEST_TRIAGE = f"t.id = (SELECT id FROM triage WHERE docket = r.docket {_TRIAGE_ORDER})"
_HAS_SUMMARY = "(SELECT 1 FROM summaries s WHERE s.docket = r.docket)"
_LATEST_CLASSIFICATION = "c.id = (SELECT MAX(id) FROM classification WHERE docket = r.docket)"
_HEADLINE = (
    "(SELECT text FROM headlines h WHERE h.docket = r.docket AND h.lang = '{lang}' "
    "ORDER BY h.id DESC LIMIT 1) AS headline_{lang}"
)


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.executescript(CLASSIFICATION_SCHEMA)
    conn.executescript(AGENT_SCHEMA)
    conn.executescript(HEADLINES_SCHEMA)
    conn.executescript(ADJUSTMENTS_SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring databases created before the French triage explanation and the cited precedents up
    to the schema."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(triage)")}
    classification = {row["name"] for row in conn.execute("PRAGMA table_info(classification)")}
    with conn:
        if "reasoning" in columns:
            conn.execute("ALTER TABLE triage RENAME COLUMN reasoning TO reasoning_de")
        if "reasoning_fr" not in columns:
            conn.execute("ALTER TABLE triage ADD COLUMN reasoning_fr TEXT")
        if "precedents" not in classification:
            conn.execute(
                "ALTER TABLE classification ADD COLUMN precedents TEXT NOT NULL DEFAULT '[]'"
            )


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
                    "INSERT INTO triage (docket, score, label, reasoning_de, reasoning_fr, model, "
                    "prompt_version) VALUES (?, ?, ?, ?, ?, 'demo', 'demo')",
                    (
                        docket,
                        triage["score"],
                        triage["label"],
                        triage["reasoning_de"],
                        triage["reasoning_fr"],
                    ),
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


_DATE = "r.decision_date"
_FROM = (
    f"FROM rulings r LEFT JOIN triage t ON {_LATEST_TRIAGE} "
    f"LEFT JOIN classification c ON {_LATEST_CLASSIFICATION}"
)


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
    branch: str | None = None,
    category: str | None = None,
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
        ("c.branch = ?", branch),
    ]:
        if value is not None and value != "":
            where.append(clause)
            params.append(value)
    if has_summary is not None:
        where.append(f"{'' if has_summary else 'NOT '}EXISTS {_HAS_SUMMARY}")
    if category:
        where.append(
            "(c.primary_category = ? OR EXISTS (SELECT 1 FROM json_each(c.secondary) "
            "WHERE value = ?))"
        )
        params += [category, category]
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
    # Branch in the UI's fixed order (UV, IV, MV, ATSG, other), then category.
    "category": (
        "CASE c.branch WHEN 'uv' THEN 1 WHEN 'iv' THEN 2 WHEN 'mv' THEN 3 WHEN 'atsg' THEN 4 "
        "WHEN 'other' THEN 5 ELSE 6 END {d}, c.primary_category {d}, t.score DESC"
    ),
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
               r.title, r.url, t.score, t.label, t.reasoning_de, t.reasoning_fr,
               t.model = '{EXPERT_MODEL}' AS expert_score,
               {_HEADLINE.format(lang="de")}, {_HEADLINE.format(lang="fr")},
               EXISTS {_HAS_SUMMARY} AS has_summary,
               (SELECT verdict FROM feedback f WHERE f.docket = r.docket
                ORDER BY f.id DESC LIMIT 1) AS feedback_verdict,
               c.branch, c.primary_category, c.secondary, c.outcome, c.flags
        {_FROM} {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return total, [_list_item(dict(row)) for row in rows]


def _list_item(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("branch", "primary_category", "secondary", "outcome", "flags")
    branch, primary, secondary, outcome, flags = (row.pop(key) for key in keys)
    row["has_summary"] = bool(row["has_summary"])
    row["expert_score"] = bool(row["expert_score"])
    row["classification"] = (
        {
            "branch": branch,
            "primary": primary,
            "secondary": json.loads(secondary),
            "outcome": outcome,
            "flags": json.loads(flags),
        }
        if branch
        else None
    )
    return row


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

    date = "decision_date"
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
        "classification": classification_counts(conn),
    }


def classification_counts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Rulings per branch and per (branch, category), counting secondary categories too,
    over the latest classification of every ruling."""
    latest = f"FROM rulings r JOIN classification c ON {_LATEST_CLASSIFICATION}"
    branches = {
        row["branch"]: row["n"]
        for row in conn.execute(f"SELECT c.branch, COUNT(*) AS n {latest} GROUP BY c.branch")
    }
    categories: dict[str, dict[str, int]] = {}
    rows = conn.execute(
        f"""
        SELECT branch, category, COUNT(*) AS n FROM (
            SELECT c.branch, c.primary_category AS category {latest}
            UNION ALL
            SELECT c.branch, j.value AS category {latest}, json_each(c.secondary) j
        ) GROUP BY branch, category
        """
    )
    for row in rows:
        categories.setdefault(row["category"], {})[row["branch"]] = row["n"]
    return {"branches": branches, "categories": categories}


def get_ruling(conn: sqlite3.Connection, docket: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {', '.join(RULING_FIELDS)} FROM rulings WHERE docket = ?", (docket,)
    ).fetchone()
    return dict(row) if row else None


def get_ruling_detail(conn: sqlite3.Connection, docket: str) -> dict[str, Any] | None:
    ruling = get_ruling(conn, docket)
    if ruling is None:
        return None
    triage_cols = "score, label, reasoning_de, reasoning_fr, model, prompt_version, created_at"
    triage = conn.execute(
        f"SELECT {triage_cols} FROM triage WHERE docket = ? {_TRIAGE_ORDER}", (docket,)
    ).fetchone()
    # The model's own result, shown next to an expert's score.
    model_triage = conn.execute(
        f"SELECT {triage_cols} FROM triage WHERE docket = ? AND model IS NOT ? "
        "ORDER BY id DESC LIMIT 1",
        (docket, EXPERT_MODEL),
    ).fetchone()
    summaries = {
        row["lang"]: dict(row)
        for row in conn.execute(
            "SELECT lang, text, model, prompt_version, created_at FROM summaries "
            "WHERE docket = ? ORDER BY id",
            (docket,),
        )
    }
    headlines = {
        row["lang"]: row["text"]
        for row in conn.execute(
            "SELECT lang, text FROM headlines WHERE docket = ? ORDER BY id", (docket,)
        )
    }
    feedback = conn.execute(
        "SELECT verdict, corrected_score, comment, created_at FROM feedback "
        "WHERE docket = ? ORDER BY id DESC",
        (docket,),
    ).fetchall()
    return {
        **ruling,
        "headline_de": headlines.get("de"),
        "headline_fr": headlines.get("fr"),
        "triage": dict(triage) if triage else None,
        "model_triage": dict(model_triage) if model_triage else None,
        "summaries": {lang: summaries.get(lang) for lang in ("de", "fr")},
        "feedback": [dict(row) for row in feedback],
        "classification": get_classification(conn, docket),
    }


_JSON_COLUMNS = ("secondary", "statutes", "precedents", "flags")
CLASSIFICATION_FIELDS = (
    "docket",
    "branch",
    "primary",
    "secondary",
    "statutes",
    "precedents",
    "outcome",
    "flags",
    "method",
    "rationale",
    "model",
    "prompt_version",
    "created_at",
)


def _classification_columns(table: str) -> str:
    # "primary" is an SQL keyword, hence the column name primary_category.
    return ", ".join(
        f'{table}.primary_category AS "primary"' if f == "primary" else f"{table}.{f}"
        for f in CLASSIFICATION_FIELDS
    )


def _classification(row: sqlite3.Row) -> dict[str, Any]:
    return {k: json.loads(v) if k in _JSON_COLUMNS else v for k, v in dict(row).items()}


def get_classification(conn: sqlite3.Connection, docket: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {_classification_columns('classification')} FROM classification "
        "WHERE docket = ? ORDER BY id DESC LIMIT 1",
        (docket,),
    ).fetchone()
    return _classification(row) if row else None


def untriaged_dockets(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    prompt_version: str | None = None,
) -> list[str]:
    """Dockets in the date range without a triage result (of `prompt_version`, if given)."""
    where, params = ["NOT EXISTS (SELECT 1 FROM triage t WHERE t.docket = r.docket"], []
    if prompt_version is not None:
        where[0] += " AND t.prompt_version = ?"
        params.append(prompt_version)
    where[0] += ")"
    date = "r.decision_date"
    if date_from:
        where.append(f"{date} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date} <= ?")
        params.append(date_to)
    rows = conn.execute(
        f"SELECT docket FROM rulings r WHERE {' AND '.join(where)} ORDER BY docket", params
    )
    return [row["docket"] for row in rows]


def dockets_to_summarize(
    conn: sqlite3.Connection,
    *,
    min_score: int,
    prompt_version: str,
    date_from: str | None = None,
    date_to: str | None = None,
    table: Literal["summaries", "headlines"] = "summaries",
    limit: int | None = None,
) -> list[str]:
    """Rulings among the `limit` highest-scored with a latest triage score of at least
    `min_score` that have no summary (or headline) of `prompt_version` and no summary a user
    edited, highest score first. The top N are taken before the skip, so a rerun after a new
    triage only writes what the new top N lacks."""
    where = ["t.score >= ?"]
    params: list[Any] = [min_score]
    date = "r.decision_date"
    if date_from:
        where.append(f"{date} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date} <= ?")
        params.append(date_to)
    params += [-1 if limit is None else limit, prompt_version, EDITED_VERSION]
    rows = conn.execute(
        f"SELECT docket FROM (SELECT r.docket, t.score FROM rulings r JOIN triage t "
        f"ON {_LATEST_TRIAGE} WHERE {' AND '.join(where)} ORDER BY t.score DESC, r.docket "
        f"LIMIT ?) r WHERE NOT EXISTS (SELECT 1 FROM {table} s WHERE s.docket = r.docket "
        "AND s.prompt_version IN (?, ?)) ORDER BY score DESC, docket",
        params,
    )
    return [row["docket"] for row in rows]


def save_triage(
    conn: sqlite3.Connection,
    docket: str,
    *,
    score: int,
    label: str,
    reasoning_de: str,
    reasoning_fr: str | None,
    model: str | None,
    prompt_version: str | None,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO triage (docket, score, label, reasoning_de, reasoning_fr, model, "
            "prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (docket, score, label, reasoning_de, reasoning_fr, model, prompt_version),
        )


TRIAGE_FIELDS = (
    "docket",
    "score",
    "label",
    "reasoning_de",
    "reasoning_fr",
    "model",
    "prompt_version",
    "created_at",
)


def export_triage(
    conn: sqlite3.Connection,
    path: Path | str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    """Write the latest triage result per ruling in the date range as JSONL, best first."""
    where, params = [], []
    date = "r.decision_date"
    if date_from:
        where.append(f"{date} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date} <= ?")
        params.append(date_to)
    rows = conn.execute(
        f"SELECT {', '.join('t.' + f for f in TRIAGE_FIELDS)} "
        f"FROM rulings r JOIN triage t ON {_LATEST_TRIAGE} "
        f"{'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY t.score DESC, t.docket",
        params,
    ).fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return len(rows)


RELEVANT_FIELDS = ("docket", "decision_date", "publication_date", "score", "headline_de")


def export_relevant(
    conn: sqlite3.Connection,
    path: Path | str,
    *,
    min_score: int,
    date_from: str | None = None,
    date_to: str | None = None,
    by: Literal["decision_date", "publication_date"] = "decision_date",
) -> int:
    """Write the rulings with a latest triage score of at least `min_score` whose decision (or
    publication) date is in the range, highest score first and ties in docket order: as one
    comma-separated line of dockets to `path`.txt and as a table to `path`.csv."""
    where, params = ["t.score >= ?"], [min_score]
    if date_from:
        where.append(f"r.{by} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"r.{by} <= ?")
        params.append(date_to)
    rows = conn.execute(
        f"SELECT r.docket, r.decision_date, r.publication_date, t.score, "
        f"{_HEADLINE.format(lang='de')} FROM rulings r JOIN triage t ON {_LATEST_TRIAGE} "
        f"WHERE {' AND '.join(where)} ORDER BY t.score DESC, {_DOCKET_ORDER.format(d='')}",
        params,
    ).fetchall()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".txt").write_text(
        ", ".join(row["docket"] for row in rows) + "\n", encoding="utf-8"
    )
    with open(path.with_suffix(".csv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(RELEVANT_FIELDS)
        writer.writerows([row[field] for field in RELEVANT_FIELDS] for row in rows)
    return len(rows)


def import_triage(conn: sqlite3.Connection, path: Path | str) -> int:
    """Load results written by `export_triage`. Rows for unknown rulings, or rulings that
    already have a result of the same prompt version, are skipped. Files from before the French
    explanation carry the German one as `reasoning`."""
    count = 0
    with conn, open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            record.setdefault("reasoning_de", record.get("reasoning"))
            row = {field: record.get(field) for field in TRIAGE_FIELDS}
            cursor = conn.execute(
                f"INSERT INTO triage ({', '.join(TRIAGE_FIELDS)}) "
                "SELECT :docket, :score, :label, :reasoning_de, :reasoning_fr, :model, "
                ":prompt_version, "
                "COALESCE(:created_at, datetime('now')) "
                "WHERE EXISTS (SELECT 1 FROM rulings WHERE docket = :docket) "
                "AND NOT EXISTS (SELECT 1 FROM triage WHERE docket = :docket "
                "AND prompt_version IS :prompt_version)",
                row,
            )
            count += cursor.rowcount
    return count


def unclassified_dockets(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    prompt_version: str | None = None,
) -> list[str]:
    """Dockets in the date range without a classification (of `prompt_version`, if given)."""
    where, params = ["NOT EXISTS (SELECT 1 FROM classification c WHERE c.docket = r.docket"], []
    if prompt_version is not None:
        where[0] += " AND c.prompt_version = ?"
        params.append(prompt_version)
    where[0] += ")"
    date = "r.decision_date"
    if date_from:
        where.append(f"{date} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date} <= ?")
        params.append(date_to)
    rows = conn.execute(
        f"SELECT docket FROM rulings r WHERE {' AND '.join(where)} ORDER BY docket", params
    )
    return [row["docket"] for row in rows]


def save_classification(conn: sqlite3.Connection, docket: str, **values: Any) -> None:
    """Store a classification; `values` are the `CLASSIFICATION_FIELDS` except docket."""
    row = {f: values.get(f) for f in CLASSIFICATION_FIELDS if f != "created_at"}
    row["docket"] = docket
    for key in _JSON_COLUMNS:
        row[key] = json.dumps(row[key] or [], ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO classification (docket, branch, primary_category, secondary, statutes, "
            "precedents, outcome, flags, method, rationale, model, prompt_version) VALUES "
            "(:docket, :branch, :primary, :secondary, :statutes, :precedents, :outcome, :flags, "
            ":method, :rationale, :model, :prompt_version)",
            row,
        )


def export_classification(
    conn: sqlite3.Connection,
    path: Path | str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    """Write the latest classification per ruling in the date range as JSONL, by docket."""
    where, params = [], []
    date = "r.decision_date"
    if date_from:
        where.append(f"{date} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{date} <= ?")
        params.append(date_to)
    rows = conn.execute(
        f"SELECT {_classification_columns('c')} "
        f"FROM rulings r JOIN classification c ON {_LATEST_CLASSIFICATION} "
        f"{'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY {_DOCKET_ORDER.format(d='')}",
        params,
    ).fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_classification(row), ensure_ascii=False) + "\n")
    return len(rows)


def import_classification(conn: sqlite3.Connection, path: Path | str) -> int:
    """Load results written by `export_classification`. Rows for unknown rulings, or rulings
    that already have a classification of the same prompt version, are skipped."""
    count = 0
    with conn, open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = {field: json.loads(line).get(field) for field in CLASSIFICATION_FIELDS}
            for key in _JSON_COLUMNS:
                row[key] = json.dumps(row[key] or [], ensure_ascii=False)
            cursor = conn.execute(
                "INSERT INTO classification (docket, branch, primary_category, secondary, "
                "statutes, precedents, outcome, flags, method, rationale, model, prompt_version, "
                "created_at) SELECT :docket, :branch, :primary, :secondary, :statutes, "
                ":precedents, :outcome, :flags, :method, :rationale, :model, :prompt_version, "
                "COALESCE(:created_at, datetime('now')) "
                "WHERE EXISTS (SELECT 1 FROM rulings WHERE docket = :docket) "
                "AND NOT EXISTS (SELECT 1 FROM classification WHERE docket = :docket "
                "AND prompt_version IS :prompt_version)",
                row,
            )
            count += cursor.rowcount
    return count


def save_summary(
    conn: sqlite3.Connection,
    docket: str,
    *,
    lang: str,
    text: str,
    model: str | None,
    prompt_version: str | None,
) -> None:
    """Store the summary of `docket` in `lang`, replacing the previous one (no history)."""
    with conn:
        conn.execute("DELETE FROM summaries WHERE docket = ? AND lang = ?", (docket, lang))
        conn.execute(
            "INSERT INTO summaries (docket, lang, text, model, prompt_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (docket, lang, text, model, prompt_version),
        )


def save_headline(
    conn: sqlite3.Connection,
    docket: str,
    *,
    lang: str,
    text: str,
    model: str | None,
    prompt_version: str | None,
) -> None:
    """Store the headline of `docket` in `lang`, replacing the previous one."""
    with conn:
        conn.execute("DELETE FROM headlines WHERE docket = ? AND lang = ?", (docket, lang))
        conn.execute(
            "INSERT INTO headlines (docket, lang, text, model, prompt_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (docket, lang, text, model, prompt_version),
        )


_TEXT_FIELDS = ("text", "model", "prompt_version", "created_at")


def export_summaries(
    conn: sqlite3.Connection,
    path: Path | str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    """Write the latest summary and headline per language of every ruling in the date range
    that has one as JSONL, one ruling per line, best triage score first."""
    where = [
        "(EXISTS (SELECT 1 FROM summaries WHERE docket = r.docket) "
        "OR EXISTS (SELECT 1 FROM headlines WHERE docket = r.docket))"
    ]
    params: list[Any] = []
    if date_from:
        where.append(f"{_DATE} >= ?")
        params.append(date_from)
    if date_to:
        where.append(f"{_DATE} <= ?")
        params.append(date_to)
    dockets = [
        row["docket"]
        for row in conn.execute(
            f"SELECT r.docket FROM rulings r LEFT JOIN triage t ON {_LATEST_TRIAGE} "
            f"WHERE {' AND '.join(where)} ORDER BY t.score IS NULL, t.score DESC, r.docket",
            params,
        )
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for docket in dockets:
            record: dict[str, Any] = {"docket": docket}
            for table in ("summaries", "headlines"):
                rows = conn.execute(
                    f"SELECT lang, {', '.join(_TEXT_FIELDS)} FROM {table} WHERE docket = ? "
                    "ORDER BY id",
                    (docket,),
                )
                record[table] = {row["lang"]: {k: row[k] for k in _TEXT_FIELDS} for row in rows}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(dockets)


def import_summaries(conn: sqlite3.Connection, path: Path | str) -> int:
    """Load summaries and headlines written by `export_summaries`, replacing older ones; returns
    the number of texts stored. Texts for unknown rulings, or for a ruling and language that
    already have one of the same prompt version or one a user edited, are skipped."""
    count = 0
    with conn, open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if get_ruling(conn, record["docket"]) is None:
                continue
            for table in ("summaries", "headlines"):
                for lang, text in record.get(table, {}).items():
                    row = {field: text.get(field) for field in _TEXT_FIELDS}
                    row |= {"docket": record["docket"], "lang": lang, "edited": EDITED_VERSION}
                    kept = conn.execute(
                        f"SELECT 1 FROM {table} WHERE docket = :docket AND lang = :lang "
                        "AND prompt_version IN (:prompt_version, :edited)",
                        row,
                    ).fetchone()
                    if kept:
                        continue
                    conn.execute(
                        f"DELETE FROM {table} WHERE docket = :docket AND lang = :lang", row
                    )
                    conn.execute(
                        f"INSERT INTO {table} (docket, lang, {', '.join(_TEXT_FIELDS)}) VALUES "
                        "(:docket, :lang, :text, :model, :prompt_version, "
                        "COALESCE(:created_at, datetime('now')))",
                        row,
                    )
                    count += 1
    return count


def set_expert_score(
    conn: sqlite3.Connection, docket: str, *, score: int, label: str, comment: str | None = None
) -> None:
    """Store a legal expert's relevance score. It replaces an earlier expert score and takes
    precedence over the model's. The explanation is the expert's comment, or else the model's."""
    model = conn.execute(
        "SELECT reasoning_de, reasoning_fr FROM triage WHERE docket = ? AND model IS NOT ? "
        "ORDER BY id DESC LIMIT 1",
        (docket, EXPERT_MODEL),
    ).fetchone()
    reasoning_de = comment or (model["reasoning_de"] if model else "")
    reasoning_fr = comment or (model["reasoning_fr"] if model else None)
    with conn:
        conn.execute("DELETE FROM triage WHERE docket = ? AND model = ?", (docket, EXPERT_MODEL))
        conn.execute(
            "INSERT INTO triage (docket, score, label, reasoning_de, reasoning_fr, model, "
            "prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (docket, score, label, reasoning_de, reasoning_fr, EXPERT_MODEL, EXPERT_MODEL),
        )
        # Kept as a record of the correction, e.g. for evaluating the triage prompt.
        conn.execute(
            "INSERT INTO feedback (docket, verdict, corrected_score, comment) VALUES (?, ?, ?, ?)",
            (docket, label, score, comment),
        )


def list_adjustments(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every expert score in force, newest first, next to the model's own result. `comment` is
    the expert's reason (None when they gave none)."""
    rows = conn.execute(
        f"""
        SELECT r.docket, r.decision_date, r.title, r.language,
               {_HEADLINE.format(lang="de")}, {_HEADLINE.format(lang="fr")},
               e.score AS expert_score, e.label AS expert_label, e.created_at AS adjusted_at,
               m.score AS model_score, m.label AS model_label,
               m.reasoning_de AS model_reasoning_de, m.reasoning_fr AS model_reasoning_fr,
               (SELECT comment FROM feedback f WHERE f.docket = r.docket
                ORDER BY f.id DESC LIMIT 1) AS comment,
               c.branch, c.primary_category
        FROM triage e JOIN rulings r ON r.docket = e.docket
        LEFT JOIN triage m ON m.id = (SELECT id FROM triage WHERE docket = e.docket
                                      AND model IS NOT '{EXPERT_MODEL}' ORDER BY id DESC LIMIT 1)
        LEFT JOIN classification c ON {_LATEST_CLASSIFICATION}
        WHERE e.model = '{EXPERT_MODEL}'
        ORDER BY e.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def latest_adjustment_summary(conn: sqlite3.Connection, lang: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT lang, text, adjustment_count, model, created_at FROM adjustment_summaries "
        "WHERE lang = ? ORDER BY id DESC LIMIT 1",
        (lang,),
    ).fetchone()
    return dict(row) if row else None


def save_adjustment_summary(
    conn: sqlite3.Connection, *, lang: str, text: str, count: int, model: str | None
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO adjustment_summaries (lang, text, adjustment_count, model) "
            "VALUES (?, ?, ?, ?)",
            (lang, text, count, model),
        )


def clear_expert_score(conn: sqlite3.Connection, docket: str) -> None:
    """Back to the model's score."""
    with conn:
        conn.execute("DELETE FROM triage WHERE docket = ? AND model = ?", (docket, EXPERT_MODEL))


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


# ---------------------------------------------------------------- agent chats


def create_chat(conn: sqlite3.Connection, chat_id: str) -> None:
    with conn:
        conn.execute("INSERT INTO chats (id) VALUES (?)", (chat_id,))


def chat_exists(conn: sqlite3.Connection, chat_id: str) -> bool:
    return conn.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)).fetchone() is not None


def delete_chat(conn: sqlite3.Connection, chat_id: str) -> None:
    """Delete the chat with its messages and proposals."""
    with conn:
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def add_chat_message(
    conn: sqlite3.Connection, chat_id: str, role: str, content: str, data: dict[str, Any] | None
) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO chat_messages (chat_id, role, content, data) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, json.dumps(data or {}, ensure_ascii=False)),
        )
        conn.execute("UPDATE chats SET updated_at = datetime('now') WHERE id = ?", (chat_id,))
    return cursor.lastrowid


def get_chat_message(conn: sqlite3.Connection, message_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, role, content, data, created_at FROM chat_messages WHERE id = ?",
        (message_id,),
    ).fetchone()
    return {**dict(row), "data": json.loads(row["data"])}


def chat_messages(conn: sqlite3.Connection, chat_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, role, content, data, created_at FROM chat_messages WHERE chat_id = ? "
        "ORDER BY id",
        (chat_id,),
    )
    return [{**dict(row), "data": json.loads(row["data"])} for row in rows]


def add_proposal(
    conn: sqlite3.Connection, chat_id: str, docket: str, *, lang: str, text: str, rationale: str
) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO summary_proposals (chat_id, docket, lang, text, rationale) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, docket, lang, text, rationale),
        )
    return cursor.lastrowid


def get_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT p.id, p.chat_id, p.docket, p.lang, p.text, p.rationale, p.status, "
        "(SELECT s.text FROM summaries s WHERE s.docket = p.docket AND s.lang = p.lang "
        " ORDER BY s.id DESC LIMIT 1) AS current "
        "FROM summary_proposals p WHERE p.id = ?",
        (proposal_id,),
    ).fetchone()
    return dict(row) if row else None


def set_proposal_status(conn: sqlite3.Connection, proposal_id: int, status: str) -> None:
    with conn:
        conn.execute("UPDATE summary_proposals SET status = ? WHERE id = ?", (status, proposal_id))


def apply_proposal(conn: sqlite3.Connection, proposal_id: int) -> dict[str, Any]:
    """Make an open proposal the ruling's summary in its language, replacing the old one."""
    proposal = get_proposal(conn, proposal_id)
    if proposal is None or proposal["status"] != "open":
        raise ValueError(f"proposal {proposal_id} is not open")
    save_summary(
        conn,
        proposal["docket"],
        lang=proposal["lang"],
        text=proposal["text"],
        model="agent",
        prompt_version=EDITED_VERSION,
    )
    set_proposal_status(conn, proposal_id, "applied")
    return {**proposal, "status": "applied"}


# ---------------------------------------------------------------- agent knowledge


def get_knowledge(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT content, updated_by, updated_at FROM agent_knowledge WHERE id = 1"
    ).fetchone()
    return dict(row) if row else None


def save_knowledge(conn: sqlite3.Connection, content: str | None, *, updated_by: str) -> None:
    """Store the agent's knowledge text; None means the default text."""
    with conn:
        conn.execute(
            "INSERT INTO agent_knowledge (id, content, updated_by) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET content = excluded.content, "
            "updated_by = excluded.updated_by, updated_at = datetime('now')",
            (content, updated_by),
        )
