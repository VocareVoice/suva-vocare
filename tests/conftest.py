from pathlib import Path

import pytest

from suva import db

CORPUS = Path(__file__).parent / "data" / "rulings.jsonl"


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.load_corpus(conn, CORPUS)
    yield conn
    conn.close()
