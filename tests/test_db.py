import sqlite3

import pytest

from suva import db
from tests.conftest import CORPUS


def dockets(items):
    return [item["docket"] for item in items]


def test_load_corpus_is_idempotent(conn):
    assert db.load_corpus(conn, CORPUS) == 3
    total, _ = db.list_rulings(conn)
    assert total == 3
    assert db.get_ruling(conn, "8C_135/2025")["language"] == "fr"


def test_load_gzipped_corpus(tmp_path):
    gz = tmp_path / "rulings.jsonl.gz"
    with db.open_corpus(gz, "w") as f:
        f.write(CORPUS.read_text(encoding="utf-8"))
    conn = db.connect(tmp_path / "gz.db")
    assert db.load_corpus(conn, gz) == 3
    assert db.get_ruling(conn, "8C_135/2025")["language"] == "fr"
    conn.close()


def test_full_text_search(conn):
    _, items = db.list_rulings(conn, q="Kausalzusammenhang")
    assert dockets(items) == ["8C_129/2025"]
    # Diacritics are folded, and every term has to match.
    _, items = db.list_rulings(conn, q="invalidite Suva")
    assert dockets(items) == ["8C_135/2025"]
    _, items = db.list_rulings(conn, q="Suva")
    assert set(dockets(items)) == {"8C_129/2025", "8C_135/2025"}
    # FTS syntax characters in user input must not raise.
    _, items = db.list_rulings(conn, q='8C_129/2025 "unclosed')
    assert items == []


def test_search_reflects_updated_text(conn):
    db.upsert_ruling(conn, {"docket": "4A_106/2025", "text": "Nun geht es um die Suva."})
    _, items = db.list_rulings(conn, q="Kündigung")
    assert items == []
    _, items = db.list_rulings(conn, q="Suva")
    assert "4A_106/2025" in dockets(items)


def test_sort_and_filter_by_latest_triage(conn):
    triage = dict(reasoning_de="r", reasoning_fr="r", model="m", prompt_version="v")
    db.save_triage(conn, "8C_129/2025", score=40, label="not_relevant", **triage)
    db.save_triage(conn, "8C_129/2025", score=90, label="relevant", **triage)
    db.save_triage(conn, "8C_135/2025", score=70, label="relevant", **triage)

    _, items = db.list_rulings(conn, sort="score")
    assert dockets(items) == ["8C_129/2025", "8C_135/2025", "4A_106/2025"]
    assert items[0]["score"] == 90

    _, items = db.list_rulings(conn, min_score=80)
    assert dockets(items) == ["8C_129/2025"]

    _, items = db.list_rulings(conn, date_from="2025-10-01", date_to="2025-10-31")
    assert dockets(items) == ["8C_129/2025"]


def test_load_demo(tmp_path, conn):
    demo = db.connect(tmp_path / "demo.db")
    count = db.load_demo(demo)
    assert count == db.load_demo(demo)
    total, items = db.list_rulings(demo, limit=count)
    assert total == count
    assert all(item["score"] is not None for item in items)
    assert any(item["has_summary"] for item in items)
    assert db.facets(demo)["demo"] is True
    assert all(item["reasoning_de"] and item["reasoning_fr"] for item in items)
    with pytest.raises(ValueError):
        db.load_demo(conn)


def test_database_from_before_the_french_explanation_still_loads(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE rulings (id INTEGER PRIMARY KEY, docket TEXT NOT NULL UNIQUE, "
        "decision_date TEXT, publication_date TEXT, division TEXT, language TEXT, title TEXT, "
        "url TEXT, text TEXT NOT NULL DEFAULT '', source TEXT, "
        "ingested_at TEXT NOT NULL DEFAULT (datetime('now')));"
        "CREATE TABLE triage (id INTEGER PRIMARY KEY, docket TEXT NOT NULL, score INTEGER NOT "
        "NULL, label TEXT NOT NULL, reasoning TEXT NOT NULL, model TEXT, prompt_version TEXT, "
        "created_at TEXT NOT NULL DEFAULT (datetime('now')));"
        "INSERT INTO rulings (docket, text) VALUES ('8C_1/2026', 'Unfall');"
        "INSERT INTO triage (docket, score, label, reasoning) "
        "VALUES ('8C_1/2026', 80, 'relevant', 'Alt.');"
    )
    old.close()

    conn = db.connect(path)
    _, items = db.list_rulings(conn)
    assert (items[0]["reasoning_de"], items[0]["reasoning_fr"]) == ("Alt.", None)
    db.save_triage(
        conn,
        "8C_1/2026",
        score=90,
        label="relevant",
        reasoning_de="Neu.",
        reasoning_fr="Nouveau.",
        model="m",
        prompt_version="v4",
    )
    assert db.get_ruling_detail(conn, "8C_1/2026")["triage"]["reasoning_fr"] == "Nouveau."
    conn.close()
    assert db.connect(path).execute("SELECT COUNT(*) FROM triage").fetchone()[0] == 2
